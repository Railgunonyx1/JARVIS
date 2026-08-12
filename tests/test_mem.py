"""Tests for Mem (Claude Mem): decision memory, project knowledge,
semantic retrieval facade, and AgentLoop integration (temp dirs only)."""

import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agent.loop import AgentLoop
from core.project import ProjectContext
from memory.decision_memory import DecisionMemory
from memory.mem import Mem
from memory.project_knowledge import ProjectKnowledge
from memory.store import MemoryStore
from memory.vector_store import VectorMemoryStore
from providers.types import LLMResponse
from tools import build_default_registry

ROOT = Path(__file__).resolve().parents[1]


class StubLogger:
    def __init__(self):
        self.records = []

    def begin_task(self, request, source=""):
        return "test_trace"

    def record(self, trace_id, name, data=None, **extra):
        self.records.append((name, data))

    def record_tool(self, *args, **kwargs):
        pass

    def flush(self):
        pass


class FakeRouter:
    def __init__(self, responses):
        self._responses = list(responses)

    async def complete(self, messages, system_prompt=None, max_tokens=None,
                       temperature=None, tools=None, preferred_provider=None):
        return self._responses.pop(0)


def _resp(text="", *, tool_calls=None):
    return LLMResponse(
        text=text, model="fake-model", provider="fake",
        tokens_prompt=10, tokens_completion=5,
        tool_calls=tool_calls or [],
    )


@pytest.fixture()
def mem(tmp_path, monkeypatch):
    from memory import vector_store as vs
    monkeypatch.setattr(vs, "_embed_ready", True)
    monkeypatch.setattr(vs, "_embed_model", None)
    backend = Mem(
        kv=MemoryStore(data_dir=tmp_path),
        vector=VectorMemoryStore(db_path=tmp_path / "vec.db"),
        decisions=DecisionMemory(data_dir=tmp_path),
        knowledge=ProjectKnowledge(data_dir=tmp_path),
    )
    yield backend
    backend.close()


# ── decision memory ───────────────────────────────────────────────────────

def test_decision_memory_record_and_recall(tmp_path):
    dm = DecisionMemory(data_dir=tmp_path)
    dm.record("fix the flaky parser", "completed", rationale="added regex",
              outcome="green", project="/proj")
    dm.record("optimize startup", "failed", rationale="cold path not found",
              outcome="", project="/proj")
    hits = dm.recall(project="/proj", query="parser flaky", limit=5)
    assert hits
    assert hits[0]["decision"] == "completed"
    assert hits[0]["project"] == "/proj"
    assert len(dm.recent(project="/proj")) == 2
    assert dm.get_stats()["decisions"] == 2
    dm.close()


def test_decision_memory_project_scoping(tmp_path):
    dm = DecisionMemory(data_dir=tmp_path)
    dm.record("task a", "completed", project="/p1")
    dm.record("task b", "failed", project="/p2")
    assert len(dm.recall(project="/p1")) == 1
    dm.close()


# ── project knowledge ─────────────────────────────────────────────────────

def test_project_knowledge_crud_and_search(tmp_path):
    pk = ProjectKnowledge(data_dir=tmp_path)
    pk.set("/proj", "build", "run `python -m cli` to build", category="command")
    assert pk.get("/proj", "build").startswith("run")
    assert pk.search("/proj", "cli build")
    assert pk.forget("/proj", "build") is True
    assert pk.get("/proj", "build") is None
    pk.close()


def test_project_knowledge_import_docs(tmp_path):
    pk = ProjectKnowledge(data_dir=tmp_path)
    (tmp_path / "AGENTS.md").write_text("Work in core/ only.\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "CLAUDE.md").write_text("Keep the CLI thin.\n", encoding="utf-8")
    imported = pk.import_docs("/proj", tmp_path)
    assert imported == 2
    text = pk.format_for_prompt("/proj", max_tokens=50)
    assert "AGENTS.md" in text
    assert "CLAUDE.md" in text
    assert len(text) <= 50 * 4 + 10
    pk.close()


# ── Mem facade ────────────────────────────────────────────────────────────

def test_mem_retrieve_merges_sources(mem):
    mem._kv.store("config_dir", "C:\\Users\\aayan\\Desktop\\JARVIS\\config", category="project")
    mem.record_decision("set up project config", "completed", project="/proj")
    mem.set_knowledge("/proj", "build", "run cli to build")
    results = mem.retrieve("config build decision", project="/proj", top_k=5)
    sources = {r["source"] for r in results}
    assert "kv" in sources
    assert "knowledge" in sources
    assert "decision" in sources
    assert len(results) <= 5


def test_mem_format_for_prompt_respects_budget(mem):
    mem.set_knowledge("/proj", "notes", "important fact " * 50)
    mem.record_decision("long task", "completed", project="/proj")
    text = mem.format_for_prompt("/proj", max_tokens=100)
    assert "[PROJECT KNOWLEDGE]" in text or "[DECISION MEMORY]" in text
    assert len(text) <= 100 * 4 + 10


def test_mem_get_stats_and_remember(mem):
    mem.remember("tool_used", "filesystem.list", category="preferences")
    stats = mem.get_stats()
    assert "memories" in stats
    assert stats["decisions"] >= 0
    assert stats["knowledge"] >= 0


# ── Stage 0 stabilization ──────────────────────────────────────────────────

def test_remember_writes_kv_and_embeds_into_vector(mem):
    mem.remember("favorite_language", "python", category="preferences")
    mem.flush_async()
    stats = mem.get_stats()
    assert stats["memories"] >= 1
    hits = mem.retrieve("favorite language", top_k=5)
    sources = {h["source"] for h in hits}
    assert "kv" in sources
    assert "vector" in sources
    assert any("python" in h["content"] for h in hits)


def test_format_for_prompt_includes_recent_kv(mem):
    mem.remember("arch_choice", "use sqlite for memory", category="projects")
    text = mem.format_for_prompt("/proj", max_tokens=200)
    assert "[RECENT MEMORY]" in text
    assert "arch_choice" in text


def test_mem_none_backends_no_crash():
    from memory.mem import Mem
    empty = Mem()
    assert empty.retrieve("anything") == []
    assert empty.recall_decisions() == []
    assert empty.get_knowledge("/p", "k") is None
    assert empty.record_decision("g", "d") is None
    assert empty.format_for_prompt("/p") == ""
    assert empty.get_stats() == {"memories": 0, "decisions": 0, "knowledge": 0}
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


# ── AgentLoop integration ─────────────────────────────────────────────────

def test_loop_records_decision_when_mem_given(mem):
    loop = AgentLoop(
        router=FakeRouter([_resp("done.")]),
        registry=build_default_registry(),
        project=ProjectContext(root_path=ROOT),
        decision_logger=StubLogger(),
        mode="agent",
        mem=mem,
    )
    result = asyncio.run(loop.run("just say done"))
    assert result.success
    assert result.observation["context_usage"]["total_tokens"] >= 0
    decisions = mem.recall_decisions(project=str(ROOT))
    assert decisions
    assert decisions[0]["decision"] == "completed"


def test_loop_without_mem_has_no_side_effects(tmp_path):
    loop = AgentLoop(
        router=FakeRouter([_resp("done.")]),
        registry=build_default_registry(),
        project=ProjectContext(root_path=ROOT),
        decision_logger=StubLogger(),
        mode="agent",
    )
    result = asyncio.run(loop.run("just say done"))
    assert result.success
    assert loop.mem is None
