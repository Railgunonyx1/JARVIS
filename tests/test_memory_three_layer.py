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

import json
import tempfile
from pathlib import Path

import pytest


# ── Layer 1: Core Memory Always Injected ────────────────────────────────


class TestCoreMemoryInjection:
    """Core memory (identity, preferences, priorities) must ALWAYS appear
    in format_for_prompt(), regardless of how many other memories exist."""

    def test_format_includes_identity(self):
        """format_for_prompt() must include identity entries."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            store = MemoryStore(db_path)
            store.store("Aayan", key="user_name", category="identity", importance=0.9)
            store.store("Software developer", key="user_role", category="identity", importance=0.9)

            api = MemoryAPI(kv=store)
            prompt = api.format_for_prompt("test_project")

            assert "user_name" in prompt
            assert "Aayan" in prompt
            assert "user_role" in prompt
            assert "[CORE MEMORY]" in prompt
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_format_includes_preferences(self):
        """format_for_prompt() must include preference entries."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            store = MemoryStore(db_path)
            store.store("Claude Code style", key="ui_style", category="preferences", importance=0.9)
            store.store("Windows Terminal", key="platform", category="preferences", importance=0.9)

            api = MemoryAPI(kv=store)
            prompt = api.format_for_prompt("test_project")

            assert "ui_style" in prompt
            assert "platform" in prompt
            assert "[CORE MEMORY]" in prompt
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_format_includes_priorities(self):
        """format_for_prompt() must include priority entries."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            store = MemoryStore(db_path)
            store.store("Work offline with Ollama", key="priority_1", category="priorities", importance=0.9)

            api = MemoryAPI(kv=store)
            prompt = api.format_for_prompt("test_project")

            assert "priority_1" in prompt
            assert "Ollama" in prompt
            assert "[CORE MEMORY]" in prompt
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_core_memory_survives_many_writes(self):
        """Core memory must persist even after many other memories are written."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            store = MemoryStore(db_path)
            # Write core memory
            store.store("Aayan", key="user_name", category="identity", importance=0.9)
            store.store("Claude Code style", key="ui_style", category="preferences", importance=0.9)

            # Write 50 other memories to push core out of "recent 8"
            for i in range(50):
                store.store(f"note_{i}", key=f"note_{i}", category="notes", importance=0.3)

            api = MemoryAPI(kv=store)
            prompt = api.format_for_prompt("test_project")

            # Core memory MUST still be present despite 50 other entries
            assert "user_name" in prompt
            assert "Aayan" in prompt
            assert "ui_style" in prompt
            assert "[CORE MEMORY]" in prompt
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_recent_memory_excludes_core_duplicates(self):
        """RECENT MEMORY section should not duplicate items already in CORE MEMORY."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            store = MemoryStore(db_path)
            store.store("Aayan", key="user_name", category="identity", importance=0.9)
            store.store("some note", key="some_note", category="notes", importance=0.5)

            api = MemoryAPI(kv=store)
            prompt = api.format_for_prompt("test_project")

            # user_name should appear in CORE MEMORY, not duplicated in RECENT MEMORY
            core_section = prompt.split("[CORE MEMORY]")[1] if "[CORE MEMORY]" in prompt else ""
            recent_section = prompt.split("[RECENT MEMORY]")[1] if "[RECENT MEMORY]" in prompt else ""

            assert "user_name" in core_section
            # user_name should NOT appear in recent section
            if recent_section:
                assert "user_name" not in recent_section
        finally:
            Path(db_path).unlink(missing_ok=True)


# ── Layer 2: Memory Tools Registered ────────────────────────────────────


class TestMemoryToolsRegistered:
    """memory.retrieve, memory.remember, memory.forget must be in the default registry."""

    def test_memory_retrieve_registered(self):
        from tools import build_default_registry
        registry = build_default_registry()
        tool = registry.get("memory.retrieve")
        assert tool is not None
        assert tool.name == "memory.retrieve"
        assert "query" in str(tool.parameters)

    def test_memory_remember_registered(self):
        from tools import build_default_registry
        registry = build_default_registry()
        tool = registry.get("memory.remember")
        assert tool is not None
        assert tool.name == "memory.remember"

    def test_memory_forget_registered(self):
        from tools import build_default_registry
        registry = build_default_registry()
        tool = registry.get("memory.forget")
        assert tool is not None

    def test_memory_stats_registered(self):
        from tools import build_default_registry
        registry = build_default_registry()
        tool = registry.get("memory.stats")
        assert tool is not None

    def test_memory_tools_in_openai_format(self):
        """Memory tools must serialize to valid OpenAI tool definitions."""
        from tools import build_default_registry
        registry = build_default_registry()
        tools = registry.to_openai_tools()
        names = {t["function"]["name"] for t in tools}
        assert "memory.retrieve" in names
        assert "memory.remember" in names
        assert "memory.forget" in names

    def test_memory_tools_survive_intent_filtering(self):
        """Intent classifier must include memory tools when relevant."""
        from core.agent.intent import IntentClassifier
        from tools import build_default_registry

        registry = build_default_registry()
        clf = IntentClassifier(registry)
        all_tools = registry.to_openai_tools()

        # Memory-related queries should include memory tools
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
            # At least one memory tool should be present
            has_memory_tool = bool(filtered_names & {"memory.retrieve", "memory.remember", "memory.forget"})
            assert has_memory_tool, f"Query '{query}' lost memory tools: {filtered_names}"


# ── Layer 3: Interrupt Lane ─────────────────────────────────────────────


class TestInterruptLaneMemory:
    """Memory tools must be allowed in the interrupt lane."""

    def test_memory_tools_in_interrupt_allowed(self):
        from core.agent.lanes import _INTERRUPT_ALLOWED_TOOLS
        assert "memory.retrieve" in _INTERRUPT_ALLOWED_TOOLS

    def test_memory_classified_as_interrupt(self):
        """Memory queries should be classified as interrupts when a main task runs."""
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

    def test_memory_modify_goes_to_main(self):
        """Memory writes during active task should go to main lane (not interrupt)."""
        from core.agent.lanes import RequestClassifier, ExecutionLane

        clf = RequestClassifier()
        c = clf.classify(
            "remember that I prefer dark mode",
            active_task_id="task_123",
            active_task_status="executing",
        )
        # "remember this" matches modification pattern → main lane
        assert c.lane == ExecutionLane.MAIN


# ── Memory Store Category Support ───────────────────────────────────────


class TestMemoryStoreCategory:
    """MemoryStore.recent() must support category filtering."""

    def test_recent_with_category(self):
        from memory.store import MemoryStore

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            store = MemoryStore(db_path)
            store.store("Aayan", key="user_name", category="identity")
            store.store("some note", key="note1", category="notes")
            store.store("Claude Code style", key="ui_style", category="preferences")

            identity = store.recent(limit=10, category="identity")
            assert len(identity) == 1
            assert identity[0]["key"] == "user_name"

            prefs = store.recent(limit=10, category="preferences")
            assert len(prefs) == 1
            assert prefs[0]["key"] == "ui_style"

            notes = store.recent(limit=10, category="notes")
            assert len(notes) == 1
            assert notes[0]["key"] == "note1"
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_recent_without_category_returns_all(self):
        from memory.store import MemoryStore

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            store = MemoryStore(db_path)
            store.store("Aayan", key="user_name", category="identity")
            store.store("some note", key="note1", category="notes")

            all_items = store.recent(limit=10)
            assert len(all_items) == 2
        finally:
            Path(db_path).unlink(missing_ok=True)


# ── Memory Manager Schema ───────────────────────────────────────────────


class TestMemoryManagerSchema:
    """_EMPTY schema must include priorities."""

    def test_empty_has_priorities(self):
        from memory.memory_manager import _EMPTY
        assert "priorities" in _EMPTY
        assert "identity" in _EMPTY
        assert "preferences" in _EMPTY


# ── End-to-End Memory Path ──────────────────────────────────────────────


class TestMemoryEndToEnd:
    """Test the full path: store → format_for_prompt → LLM receives memory."""

    def test_full_memory_lifecycle(self):
        """Store identity → format for prompt → verify core memory is present."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            store = MemoryStore(db_path)
            api = MemoryAPI(kv=store)

            # Store core memories
            api.remember("user_name", "Aayan", category="identity")
            api.remember("ui_style", "Claude Code style", category="preferences")
            api.remember("priority_1", "Work offline with Ollama", category="priorities")

            # Store some other memories
            api.remember("some_note", "Important note about the project", category="notes")

            # Format for LLM prompt
            prompt = api.format_for_prompt("JARVIS")

            # Verify core memory is present
            assert "[CORE MEMORY]" in prompt
            assert "Aayan" in prompt
            assert "Claude Code style" in prompt
            assert "Ollama" in prompt

            # Verify recent memory section exists
            assert "[RECENT MEMORY]" in prompt
        finally:
            Path(db_path).unlink(missing_ok=True)
