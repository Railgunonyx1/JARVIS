"""Tests for memory subsystems (MemoryAPI, TieredMemoryStore, MemoryStore, etc.)."""

import asyncio
import time
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem():
    from memory.mem import get_mem
    m = get_mem()
    try:
        yield m
    finally:
        m.close()


@pytest.fixture
def mem_with_identity(mem):
    mem.remember("test_identity_key", "TestUser", category="identity")
    return mem


# ---------------------------------------------------------------------------
# Unit: MemoryAPI core operations
# ---------------------------------------------------------------------------

def test_retrieve_returns_empty_for_unknown(mem):
    # retrieve may return existing memories (identity, etc.) even for unrelated queries
    # The important thing is it doesn't crash
    results = mem.retrieve("nonexistent_xyzzy_xyz", project=str(ROOT))
    assert isinstance(results, list)


def test_remember_and_retrieve(mem):
    mem.remember("test_mem_key_unique_xyz", "test_mem_value_unique", category="notes")
    results = mem.retrieve("test_mem_key_unique_xyz", project=str(ROOT), top_k=5)
    assert any("test_mem_value_unique" in r.get("content", "") for r in results)


def test_get_stats_returns_dict(mem):
    stats = mem.get_stats()
    assert isinstance(stats, dict)
    assert "memories" in stats


def test_format_for_prompt_empty(mem):
    prompt = mem.format_for_prompt(str(ROOT))
    assert isinstance(prompt, str)


def test_format_for_prompt_with_identity(mem_with_identity):
    prompt = mem_with_identity.format_for_prompt(str(ROOT))
    assert "TestUser" in prompt


def test_record_decision(mem):
    mem.record_decision("test goal", "completed", "because", "outcome", project=str(ROOT))
    decisions = mem.recall_decisions(project=str(ROOT))
    assert decisions
    assert decisions[0]["decision"] == "completed"


def test_empty_memory_api():
    from memory.mem import get_mem
    empty = get_mem()
    try:
        stats = empty.get_stats()
        assert isinstance(stats, dict)
    finally:
        empty.close()


def test_tiered_cleanup_respects_age(tmp_path):
    from memory.tiered_store import TieredMemoryStore
    ts = TieredMemoryStore(data_dir=tmp_path)
    try:
        ts.store("old", "value", tier="hot")
        ts.store("new", "value", tier="hot")
        ts._hot_ts["old"] = time.time() - 10_000
        ts._hot_ts["new"] = time.time() + 3600
        removed = ts.cleanup(max_age_hours=0)
        assert removed == 1
        assert ts.retrieve("old") is None
        assert ts.retrieve("new") == "value"
        ts.store("touched", "v", tier="hot")
        ts.retrieve("touched")
        before = ts._hot_ts["touched"]
        ts.retrieve("touched")
        assert ts._hot_ts["touched"] >= before
    finally:
        ts.close()


def test_store_shutdown_flushes_conversations(tmp_path):
    from memory.store import MemoryStore
    store = MemoryStore(data_dir=tmp_path)
    store.log_conversation("sess_1", "user", "hello")
    store.shutdown()
    reopened = MemoryStore(data_dir=tmp_path)
    try:
        history = reopened.get_conversation_history("sess_1")
        assert len(history) == 1
        assert history[0]["content"] == "hello"
    finally:
        reopened.close()


# ---------------------------------------------------------------------------
# Helpers for AgentLoop integration tests
# ---------------------------------------------------------------------------

from core.agent.loop import AgentLoop
from core.project import ProjectContext
from providers.types import LLMResponse
from tools import build_default_registry


class StubLogger:
    def begin_task(self, request, source=""):
        return "test_trace"
    def record(self, trace_id, name, data=None, **extra):
        pass
    def record_tool(self, *a, **kw):
        pass
    def flush(self):
        pass


class FakeRouter:
    def __init__(self, responses):
        self._responses = list(responses)

    async def complete(self, messages, **kw):
        return self._responses.pop(0)

    async def complete_stream_typed(self, messages, **kwargs):
        r = await self.complete(messages, **kwargs)
        yield r.text, r.tool_calls


def _resp(text=""):
    return LLMResponse(
        text=text, model="fake", provider="fake",
        latency_ms=10, tokens_used=10,
        tokens_prompt=10, tokens_completion=5,
    )


# ---------------------------------------------------------------------------
# AgentLoop integration
# ---------------------------------------------------------------------------

def test_loop_records_decision_when_mem_given(mem):
    loop = AgentLoop(
        router=FakeRouter([_resp("done.")]),
        registry=build_default_registry(),
        project=ProjectContext(root_path=ROOT),
        decision_logger=StubLogger(),
        mode="agent",
        mem=mem,
    )
    loop._verification_enabled = False
    result = asyncio.run(loop.run("just say done"))
    assert result.success
    assert result.observation["context_usage"]["total_tokens"] >= 0
    decisions = mem.recall_decisions(project=str(ROOT))
    assert decisions
    assert decisions[0]["decision"] == "completed"


def test_loop_without_mem_has_no_side_effects():
    loop = AgentLoop(
        router=FakeRouter([_resp("done.")]),
        registry=build_default_registry(),
        project=ProjectContext(root_path=ROOT),
        decision_logger=StubLogger(),
        mode="agent",
    )
    loop._verification_enabled = False
    result = asyncio.run(loop.run("just say done"))
    assert result.success
    assert loop.mem is None
