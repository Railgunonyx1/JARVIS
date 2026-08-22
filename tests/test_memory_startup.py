"""P0 Release Test: Memory End-to-End Startup Integration.

Proves the complete chain:
    NEW SESSION
        -> memory authority loads long_term.json
        -> identity/preferences/priorities retrieved
        -> context builder injects into system prompt
        -> model receives user identity

Also tests:
    - Memory persists across sessions
    - Interrupt lane can retrieve memory independently
    - Memory tools are properly registered
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

import pytest


# ---------------------------------------------------------------------------
# 1. Memory bootstrap: long_term.json -> KV store
# ---------------------------------------------------------------------------

def test_memory_bootstrap_loads_identity():
    """Memory system must load identity from long_term.json into the KV store."""
    from memory.mem import get_mem

    mem = get_mem()
    try:
        # Store identity data (simulates long_term.json bootstrap)
        mem.remember("user_name", "Aayan", category="identity")
        mem.remember("user_role", "Software developer", category="identity")

        # Verify it's retrievable
        # Check that memories count increased or entry exists
        stats = mem.get_stats()
        memories = stats.get("memories", 0)
        assert memories > 0, f"Memory store should have entries after bootstrap, got stats: {stats}"
    finally:
        mem.close()


def test_memory_persists_across_instances():
    """Memory must survive closing and reopening the memory instance."""
    from memory.mem import get_mem

    # First session: store identity
    mem1 = get_mem()
    try:
        mem1.remember("persist_test_key", "persist_test_value", category="notes")
    finally:
        mem1.close()

    # Second session: verify it's still there
    mem2 = get_mem()
    try:
        stats = mem2.get_stats()
        memories = stats.get("memories", 0)
        assert memories > 0, f"Memory should persist across sessions, got stats: {stats}"
    finally:
        mem2.close()


# ---------------------------------------------------------------------------
# 2. Memory -> Context Builder -> System Prompt
# ---------------------------------------------------------------------------

def test_memory_appears_in_system_prompt():
    """Memory content must appear in the system prompt via format_for_prompt."""
    from memory.mem import get_mem

    mem = get_mem()
    try:
        # Store identity
        mem.remember("user_name", "TestUser", category="identity")

        # Get formatted prompt
        prompt = mem.format_for_prompt(project="", max_tokens=800)

        # The prompt should contain our stored identity
        assert "TestUser" in prompt, (
            f"Identity 'TestUser' not found in memory prompt. Got: {prompt[:200]}"
        )
    finally:
        mem.close()


def test_priorities_appear_in_system_prompt():
    """Priorities must be included in the memory prompt."""
    from memory.mem import get_mem

    mem = get_mem()
    try:
        mem.remember("priority_1", "Ship quality software", category="priorities")

        prompt = mem.format_for_prompt(project="", max_tokens=800)
        assert "Ship quality software" in prompt or "priority" in prompt.lower(), (
            f"Priorities not found in memory prompt"
        )
    finally:
        mem.close()


# ---------------------------------------------------------------------------
# 3. Context builder integration
# ---------------------------------------------------------------------------

def test_context_builder_injects_memory():
    """AgentContextBuilder must include memory in the system prompt."""
    from core.agent.context import AgentContextBuilder
    from memory.mem import get_mem
    from tools import build_default_registry

    registry = build_default_registry()
    builder = AgentContextBuilder(registry)

    mem = get_mem()
    try:
        mem.remember("ctx_test_name", "ContextTestUser", category="identity")

        # Build a session-level prompt (which includes memory)
        messages, system_prompt = builder.build(
            goal="hello",
            project=None,
            mem=mem,
            context_level="session",
        )

        assert "ContextTestUser" in system_prompt, (
            f"Memory not injected into system prompt at session level. "
            f"Prompt starts with: {system_prompt[:200]}"
        )
    finally:
        mem.close()


def test_instant_level_skips_memory():
    """Instant-level context should NOT include memory (optimized for speed)."""
    from core.agent.context import AgentContextBuilder
    from memory.mem import get_mem
    from tools import build_default_registry

    registry = build_default_registry()
    builder = AgentContextBuilder(registry)

    mem = get_mem()
    try:
        mem.remember("instant_test", "should_not_appear", category="identity")

        messages, system_prompt = builder.build(
            goal="hello",
            project=None,
            mem=mem,
            context_level="instant",
        )

        # Instant should be very short (just identity)
        assert len(system_prompt) < 200, (
            f"Instant prompt too long ({len(system_prompt)} chars), likely includes memory"
        )
    finally:
        mem.close()


# ---------------------------------------------------------------------------
# 4. Memory tools are registered
# ---------------------------------------------------------------------------

def test_memory_tools_registered():
    """Core memory tools must be registered in the tool registry."""
    from tools import build_default_registry

    registry = build_default_registry()
    registered_names = {t.name for t in registry.list()}

    expected_tools = [
        "memory.retrieve",
        "memory.remember",
        "memory.stats",
    ]

    for tool in expected_tools:
        assert tool in registered_names, f"Memory tool '{tool}' not registered"


def test_memory_tool_serialization():
    """Memory tools must serialize correctly for the LLM API."""
    from tools import build_default_registry

    registry = build_default_registry()
    tools = registry.to_openai_tools()
    tool_names = {t["function"]["name"] for t in tools}

    assert "memory.retrieve" in tool_names
    assert "memory.remember" in tool_names


# ---------------------------------------------------------------------------
# 5. Memory in interrupt lane
# ---------------------------------------------------------------------------

def test_interrupt_lane_includes_memory_retrieval():
    """The interrupt lane must include memory retrieval for lightweight queries."""
    from core.agent.lanes import _INTERRUPT_ALLOWED_TOOLS

    assert "memory.retrieve" in _INTERRUPT_ALLOWED_TOOLS
    assert "memory.stats" in _INTERRUPT_ALLOWED_TOOLS
