"""Tests for the three-layer memory architecture.

Layer 1: Core Memory — always injected (identity, preferences, priorities)
Layer 2: Retrieval Memory — on-demand via memory.retrieve tool
Layer 3: Session Memory — current conversation context

Also tests:
- Memory tools are registered and LLM-callable
- Intent classifier includes memory tools when relevant
- Interrupt lane allows memory tools
- format_for_prompt() guarantees core memory injection
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ── Layer 1: Core Memory Always Injected ────────────────────────────────


class TestCoreMemoryInjection:
    """Core memory (identity, preferences, priorities) must ALWAYS appear
    in format_for_prompt(), regardless of how many other memories exist."""

    def test_format_includes_identity(self):
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        store.store("user_name", "Aayan", category="identity", importance=0.9)
        store.store("user_role", "Software developer", category="identity", importance=0.9)

        api = MemoryAPI(kv=store)
        prompt = api.format_for_prompt("test_project")

        assert "user_name" in prompt
        assert "Aayan" in prompt
        assert "user_role" in prompt
        assert "[CORE MEMORY]" in prompt

    def test_format_includes_preferences(self):
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        store.store("ui_style", "Claude Code style", category="preferences", importance=0.9)
        store.store("platform", "Windows Terminal", category="preferences", importance=0.9)

        api = MemoryAPI(kv=store)
        prompt = api.format_for_prompt("test_project")

        assert "ui_style" in prompt
        assert "platform" in prompt
        assert "[CORE MEMORY]" in prompt

    def test_format_includes_priorities(self):
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        store.store("priority_1", "Work offline with Ollama", category="priorities", importance=0.9)

        api = MemoryAPI(kv=store)
        prompt = api.format_for_prompt("test_project")

        assert "priority_1" in prompt
        assert "Ollama" in prompt
        assert "[CORE MEMORY]" in prompt

    def test_core_memory_survives_many_writes(self):
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        store.store("user_name", "Aayan", category="identity", importance=0.9)
        store.store("ui_style", "Claude Code style", category="preferences", importance=0.9)

        for i in range(50):
            store.store(f"note_{i}", f"Note content {i}", category="notes", importance=0.3)

        api = MemoryAPI(kv=store)
        prompt = api.format_for_prompt("test_project")

        assert "user_name" in prompt
        assert "Aayan" in prompt
        assert "ui_style" in prompt
        assert "[CORE MEMORY]" in prompt

    def test_recent_memory_excludes_core_duplicates(self):
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        store.store("user_name", "Aayan", category="identity", importance=0.9)
        store.store("some_note", "Some note content", category="notes", importance=0.5)

        api = MemoryAPI(kv=store)
        prompt = api.format_for_prompt("test_project")

        core_section = prompt.split("[CORE MEMORY]")[1] if "[CORE MEMORY]" in prompt else ""
        recent_section = prompt.split("[RECENT MEMORY]")[1] if "[RECENT MEMORY]" in prompt else ""

        assert "user_name" in core_section
        if recent_section:
            assert "user_name" not in recent_section


# ── Layer 2: Memory Tools Registered ────────────────────────────────────


class TestMemoryToolsRegistered:
    """memory.retrieve, memory.remember, memory.forget must be in the default registry."""

    def test_memory_retrieve_registered(self):
        from tools import build_default_registry
        registry = build_default_registry()
        tool = registry.get("memory.retrieve")
        assert tool is not None
        assert tool.name == "memory.retrieve"

    def test_memory_remember_registered(self):
        from tools import build_default_registry
        registry = build_default_registry()
        tool = registry.get("memory.remember")
        assert tool is not None

    def test_memory_forget_registered(self):
        from tools import build_default_registry
        registry = build_default_registry()
        tool = registry.get("memory.forget")
        assert tool is not None

    def test_memory_tools_in_openai_format(self):
        from tools import build_default_registry
        registry = build_default_registry()
        tools = registry.to_openai_tools()
        names = {t["function"]["name"] for t in tools}
        assert "memory.retrieve" in names
        assert "memory.remember" in names

    def test_memory_tools_survive_intent_filtering(self):
        from core.agent.intent import IntentClassifier
        from tools import build_default_registry

        registry = build_default_registry()
        clf = IntentClassifier(registry)
        all_tools = registry.to_openai_tools()

        queries = [
            "what do you remember about the auth system",
            "search memory for sqlite-vec",
            "remember that I prefer dark mode",
            "what did we decide about the architecture",
            "recall our previous decision",
        ]
        for query in queries:
            filtered = clf.select_tools(query, all_tools)
            filtered_names = {t["function"]["name"] for t in filtered}
            has_memory_tool = bool(filtered_names & {"memory.retrieve", "memory.remember", "memory.forget"})
            assert has_memory_tool, f"Query '{query}' lost memory tools: {filtered_names}"


# ── Layer 3: Interrupt Lane ─────────────────────────────────────────────


class TestInterruptLaneMemory:
    """Memory tools must be allowed in the interrupt lane."""

    def test_memory_tools_in_interrupt_allowed(self):
        from core.agent.lanes import _INTERRUPT_ALLOWED_TOOLS
        assert "memory.retrieve" in _INTERRUPT_ALLOWED_TOOLS

    def test_memory_classified_as_interrupt(self):
        from core.agent.lanes import RequestClassifier, ExecutionLane

        clf = RequestClassifier()
        queries = [
            "what do you remember about the auth system",
            "search memory for sqlite-vec",
            "what is my name",
            "what did we decide about the architecture",
        ]
        for query in queries:
            c = clf.classify(query, active_task_id="task_123", active_task_status="executing")
            assert c.lane == ExecutionLane.INTERRUPT, (
                f"Query '{query}' should be interrupt, got {c.lane.value}"
            )

    def test_code_modify_goes_to_main(self):
        from core.agent.lanes import RequestClassifier, ExecutionLane

        clf = RequestClassifier()
        # Code modifications should always go to main lane
        for query in [
            "fix the authentication bug",
            "refactor the memory module",
            "deploy to production",
            "git commit the changes",
        ]:
            c = clf.classify(query, active_task_id="task_123", active_task_status="executing")
            assert c.lane == ExecutionLane.MAIN, f"'{query}' should be MAIN, got {c.lane.value}"


# ── Memory Store Category Support ───────────────────────────────────────


class TestMemoryStoreCategory:
    """MemoryStore.recent() must support category filtering."""

    def test_recent_with_category(self):
        from memory.store import MemoryStore

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        store.store("user_name", "Aayan", category="identity")
        store.store("note1", "some note", category="notes")
        store.store("ui_style", "Claude Code style", category="preferences")

        identity = store.recent(limit=10, category="identity")
        assert len(identity) == 1
        assert identity[0]["key"] == "user_name"

        prefs = store.recent(limit=10, category="preferences")
        assert len(prefs) == 1
        assert prefs[0]["key"] == "ui_style"

    def test_recent_without_category_returns_all(self):
        from memory.store import MemoryStore

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        store.store("user_name", "Aayan", category="identity")
        store.store("note1", "some note", category="notes")

        all_items = store.recent(limit=10)
        assert len(all_items) == 2


# ── Memory Manager Schema ───────────────────────────────────────────────


class TestMemoryManagerSchema:
    """_EMPTY schema must include priorities."""

    def test_empty_has_priorities(self):
        from memory.memory_manager import _EMPTY
        assert "priorities" in _EMPTY
        assert "identity" in _EMPTY
        assert "preferences" in _EMPTY
