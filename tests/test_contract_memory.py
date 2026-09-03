"""Contract Tests — Memory System

These tests prove the memory pipeline works end-to-end, not just that
individual functions return correct values.

Contract: "A new conversation always receives core memory, and the LLM
can retrieve and store memories via tools."
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


class TestMemoryContractCoreMemory:
    """CONTRACT: Every new conversation MUST receive core memory."""

    def test_identity_always_injected(self):
        """After storing identity, format_for_prompt() always includes it."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        api = MemoryAPI(kv=store)

        api.remember("user_name", "Aayan", category="identity")
        api.remember("user_role", "Software developer", category="identity")

        # Simulate "new conversation" — format for prompt
        prompt = api.format_for_prompt("test_project")

        assert "user_name" in prompt
        assert "Aayan" in prompt
        assert "user_role" in prompt
        assert "[CORE MEMORY]" in prompt

    def test_preferences_always_injected(self):
        """Preferences survive even after many other memories are written."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        api = MemoryAPI(kv=store)

        api.remember("ui_style", "Claude Code style", category="preferences")
        api.remember("platform", "Windows Terminal", category="preferences")

        # Write 100 other memories
        for i in range(100):
            api.remember(f"note_{i}", f"Content {i}", category="notes")

        prompt = api.format_for_prompt("test_project")

        # Preferences MUST survive
        assert "ui_style" in prompt
        assert "Claude Code" in prompt
        assert "platform" in prompt

    def test_priorities_always_injected(self):
        """Priorities are always visible to the LLM."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        api = MemoryAPI(kv=store)

        api.remember("priority_1", "Work offline with Ollama", category="priorities")
        api.remember("priority_2", "Clean UI", category="priorities")

        prompt = api.format_for_prompt("test_project")

        assert "priority_1" in prompt
        assert "Ollama" in prompt
        assert "[CORE MEMORY]" in prompt


class TestMemoryContractRetrieval:
    """CONTRACT: LLM can retrieve memories via semantic search."""

    def test_retrieve_returns_relevant_results(self):
        """memory.retrieve() returns memories matching the query."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        api = MemoryAPI(kv=store)

        api.remember("auth_system", "The authentication uses JWT tokens", category="notes")
        api.remember("ui_framework", "Uses Rich for terminal rendering", category="notes")

        results = api.retrieve("authentication system")
        assert len(results) > 0
        # The auth memory should be more relevant than the UI one
        contents = [r.get("content", "") for r in results]
        assert any("auth" in c.lower() or "jwt" in c.lower() for c in contents)

    def test_retrieve_across_categories(self):
        """Retrieve searches across all memory categories."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()
        store = MemoryStore(Path(tmpdir))
        api = MemoryAPI(kv=store)

        api.remember("user_name", "Aayan", category="identity")
        api.remember("auth_note", "JWT tokens for auth", category="notes")

        results = api.retrieve("Aayan")
        assert len(results) > 0


class TestMemoryContractPersistence:
    """CONTRACT: Memory persists across sessions."""

    def test_memory_survives_reboot(self):
        """Memory stored in one session is visible in the next."""
        from memory.store import MemoryStore
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()

        # Session 1: store memory
        store1 = MemoryStore(Path(tmpdir))
        api1 = MemoryAPI(kv=store1)
        api1.remember("user_name", "Aayan", category="identity")
        api1.close()

        # Session 2: load from same directory
        store2 = MemoryStore(Path(tmpdir))
        api2 = MemoryAPI(kv=store2)

        prompt = api2.format_for_prompt("test_project")
        assert "user_name" in prompt
        assert "Aayan" in prompt

    def test_decisions_persist(self):
        """Decisions recorded in one session are retrievable in the next."""
        from memory.store import MemoryStore
        from memory.decision_memory import DecisionMemory
        from memory.api import MemoryAPI

        tmpdir = tempfile.mkdtemp()

        # Session 1
        store1 = MemoryStore(Path(tmpdir))
        decisions1 = DecisionMemory(data_dir=Path(tmpdir))
        api1 = MemoryAPI(kv=store1, decisions=decisions1)
        api1.record_decision(
            goal="Use Ollama as primary provider",
            decision="completed",
            rationale="Free, local, no API key needed",
        )
        api1.close()

        # Session 2
        store2 = MemoryStore(Path(tmpdir))
        decisions2 = DecisionMemory(data_dir=Path(tmpdir))
        api2 = MemoryAPI(kv=store2, decisions=decisions2)
        decisions = api2.recall_decisions(query="Ollama")
        assert len(decisions) > 0, f"Expected decisions, got: {decisions}"


class TestMemoryContractTools:
    """CONTRACT: Memory tools are registered and callable."""

    def test_memory_tools_registered(self):
        """memory.retrieve, memory.remember, memory.forget are in the registry."""
        from tools import build_default_registry

        registry = build_default_registry()
        for name in ["memory.retrieve", "memory.remember", "memory.forget", "memory.stats"]:
            tool = registry.get(name)
            assert tool is not None, f"{name} not registered"

    def test_memory_tools_in_openai_format(self):
        """Memory tools serialize to valid OpenAI tool definitions."""
        from tools import build_default_registry

        registry = build_default_registry()
        tools = registry.to_openai_tools()
        names = {t["function"]["name"] for t in tools}
        assert "memory.retrieve" in names
        assert "memory.remember" in names

    def test_memory_tools_survive_intent_filtering(self):
        """Intent classifier includes memory tools for memory-related queries."""
        from tools import build_default_registry
        from core.agent.intent import IntentClassifier

        registry = build_default_registry()
        clf = IntentClassifier(registry)
        all_tools = registry.to_openai_tools()

        queries = [
            "what do you remember about the auth system",
            "search memory for sqlite-vec",
            "remember that I prefer dark mode",
            "what did we decide about the architecture",
        ]
        for query in queries:
            filtered = clf.select_tools(query, all_tools)
            fnames = {t["function"]["name"] for t in filtered}
            has_mem = bool(fnames & {"memory.retrieve", "memory.remember", "memory.forget"})
            assert has_mem, f"Query '{query}' lost memory tools"

    def test_select_tools_baseline_fallback_when_no_keyword_match(self):
        """Goals with no keyword intent should get a curated core subset, not
        the entire ~76-tool catalog, while keeping general-purpose tools."""
        from core.agent.intent import IntentClassifier
        from tools import build_default_registry

        registry = build_default_registry()
        clf = IntentClassifier(registry)
        all_tools = registry.to_openai_tools()
        baseline = clf._BASELINE_TOOLS

        for goal in (
            "explain how the payment service works",
            "analyze the performance of the check worker",
            "compare two implementations",
        ):
            filtered = clf.select_tools(goal, all_tools)
            names = {t["function"]["name"] for t in filtered}
            assert len(filtered) < len(all_tools), f"goal '{goal}' sent full catalog"
            for tool in baseline:
                assert tool in names, f"baseline tool '{tool}' missing for '{goal}'"
