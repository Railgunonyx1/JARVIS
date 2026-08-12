"""Stage 1 memory architecture tests.

Covers the Stage 1 completion criteria:
  - every write goes through the unified API (store/retrieve/update/delete)
  - every memory has metadata
  - retrieval uses hybrid scoring (importance / recency / usefulness)
  - memory types exist (semantic / episodic / procedural / decision / project)
  - background processing exists (priority worker, deferred embeddings)
  - memory lifecycle (session → long-term) + tests cover the write/read loop
"""

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory.api import MemoryAPI
from memory.decision_memory import DecisionMemory
from memory.lifecycle import PRIORITY_HIGH, PRIORITY_LOW, MemoryWorker
from memory.models import EPISODIC, PROCEDURAL, PROJECT, SEMANTIC
from memory.project_knowledge import ProjectKnowledge
from memory.store import MemoryStore
from memory.vector_store import VectorMemoryStore


@pytest.fixture()
def api(tmp_path, monkeypatch):
    from memory import vector_store as vs
    monkeypatch.setattr(vs, "_embed_ready", True)
    monkeypatch.setattr(vs, "_embed_model", None)
    mem = MemoryAPI(
        kv=MemoryStore(data_dir=tmp_path),
        vector=VectorMemoryStore(db_path=tmp_path / "vec.db"),
        decisions=DecisionMemory(data_dir=tmp_path),
        knowledge=ProjectKnowledge(data_dir=tmp_path),
    )
    yield mem
    mem.close()


# ── 1A unified API write/read loop ───────────────────────────────────────

def test_unified_store_retrieve_update_delete(api):
    key = api.store("sqlite vec for embeddings", type=SEMANTIC, project="/p", importance=0.6)
    assert key.startswith(SEMANTIC)
    api.flush_async()

    hits = api.retrieve("sqlite embedding", project="/p", top_k=3)
    assert any("sqlite" in h["content"] for h in hits)

    api.update(key, content="sqlite vec + lexical for embeddings")
    api.flush_async()
    assert any("lexical" in h["content"] for h in api.retrieve("sqlite embedding", project="/p", top_k=3))

    assert api.delete(key) is True
    assert api._kv.recall(key) is None
    assert api.controller._metadata.get(key) is None


# ── 1D every memory has metadata ─────────────────────────────────────────

def test_every_memory_has_metadata(api):
    key = api.store("metadata fact alpha", type=SEMANTIC, project="/p",
                    importance=0.7, confidence=0.9, source="test")
    row = api.controller._metadata.get(key)
    assert row is not None
    assert row["type"] == SEMANTIC
    assert row["project"] == "/p"
    assert abs(row["importance"] - 0.7) < 0.01
    assert row["confidence"] == 0.9
    assert row["access_count"] == 0
    assert row["source"] == "test"


# ── 1E/1F hybrid ranking ─────────────────────────────────────────────────

def test_ranking_prefers_important_memory(api):
    api.store("shared phrase omega", key="low", importance=0.1)
    api.store("shared phrase omega", key="high", importance=0.9)
    items = api.retrieve_items("shared phrase omega", top_k=2)
    assert items[0].id == "kv:high"


def test_ranking_prefers_recent_memory(api):
    api.store("shared phrase beta", key="old", importance=0.5)
    api.store("shared phrase beta", key="new", importance=0.5)
    old_ts = time.time() - 40 * 86400
    with api.controller._metadata._conn:
        api.controller._metadata._conn.execute(
            "UPDATE memory_metadata SET last_used = ?, created = ? WHERE memory_key = ?",
            (old_ts, old_ts, "old"),
        )
    items = api.retrieve_items("shared phrase beta", top_k=2)
    assert items[0].id == "kv:new"


def test_ranking_prefers_prior_usefulness(api):
    api.store("shared phrase gamma", key="u1", importance=0.5)
    api.store("shared phrase gamma", key="u2", importance=0.5)
    api.controller._metadata.touch("u1")
    api.controller._metadata.touch("u1")
    items = api.retrieve_items("shared phrase gamma", top_k=2)
    assert items[0].id == "kv:u1"


def test_importance_engine_scores_explicit_vs_weak(api):
    low = api.store("tiny note")
    strong = api.store("i must remember that my name is Alex and I love Python deeply")
    low_row = api.controller._metadata.get(low)
    strong_row = api.controller._metadata.get(strong)
    assert strong_row["importance"] > low_row["importance"]


# ── 1C memory types ──────────────────────────────────────────────────────

def test_memory_types_store_and_retrieve(api):
    api.store_semantic("JARVIS uses sqlite-vec", project="/p")
    api.store_episodic("optimized the memory module", when="August 2026", project="/p")
    api.store_procedural("when auditing: read, benchmark, optimize", project="/p")
    api.store_project_item("/p", "architecture", "cache", "sqlite-vec for embeddings")
    api.flush_async()

    stats = api.get_stats()
    assert stats["memories"] >= 4

    items = api.retrieve_items("sqlite vector cache", project="/p", top_k=10)
    types = {i.type for i in items}
    assert {SEMANTIC, EPISODIC, PROCEDURAL, PROJECT} <= types


def test_decision_memory_upgraded_fields(api):
    api.store_decision(
        goal="fix flaky parser",
        decision="use a real grammar",
        rationale="regex was too greedy",
        alternatives=["stop testing", "more regex"],
        impact="tests went green",
        related_files=["parser.py", "tests/test_parser.py"],
        project="/p",
    )
    api.flush_async()
    rows = api.recall_decisions(project="/p")
    assert rows and rows[0]["goal"] == "fix flaky parser"
    meta = json.loads(rows[0]["metadata"])
    assert meta["alternatives"] == ["stop testing", "more regex"]
    assert meta["related_files"] == ["parser.py", "tests/test_parser.py"]

    hits = api.retrieve("flaky parser", project="/p", top_k=5)
    assert any(h["source"] == "decision" for h in hits)


# ── 1G background worker ─────────────────────────────────────────────────

def test_worker_runs_highest_priority_first():
    order = []
    w = MemoryWorker()
    w.enqueue(PRIORITY_LOW, order.append, "low")
    w.enqueue(PRIORITY_HIGH, order.append, "high")
    w.drain()
    assert order == ["high", "low"]
    w.close()


def test_embedding_is_deferred_to_background(api):
    api.store("background embed candidate zeta", type=SEMANTIC)
    # store() returns without embedding synchronously; draining guarantees it.
    api.flush_async()
    assert api.get_stats()["vector"] >= 1


def test_conversation_pipeline_saves_to_session_and_promotes(api):
    items = api.process_conversation("my name is Alice", source="sess_1")
    assert any(i.content.startswith("User name is") for i in items)
    assert api.recall_session("alice")
    api.flush_async()
    assert api.get_stats()["memories"] >= 1


# ── lifecycle / misc ─────────────────────────────────────────────────────

def test_get_stats_exposes_sources_and_lifecycle(api):
    api.store("alpha beta", type=SEMANTIC)
    stats = api.get_stats()
    assert stats["memories"] >= 1
    assert "decisions" in stats
    assert "knowledge" in stats
    assert "metadata" in stats
    assert "queue" in stats
    assert "session" in stats


def test_delete_cleans_all_backends(api):
    key = api.store("to be deleted delta", type=SEMANTIC, importance=0.5)
    api.flush_async()
    assert api.get_stats()["memories"] >= 1
    assert api.delete(key) is True
    assert api._kv.recall(key) is None
    assert api.controller._metadata.get(key) is None
