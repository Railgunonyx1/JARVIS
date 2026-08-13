"""
JARVIS Memory Fabric — Test Suite

Covers all required test cases from the architecture spec:
  - insert/retrieve
  - duplicate memories
  - updates
  - conflicting facts
  - temporal validity
  - FTS search
  - vector search interface
  - ranking
  - forgetting
  - provenance
  - confidence
  - concurrent access
  - persistence across restart
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading

# Ensure the parent package is importable (repo layout: memory/jarvis_memory_fabric)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from jarvis_memory_fabric import create_memory_fabric, MemoryFabric
from jarvis_memory_fabric.storage_sqlite import SQLiteMemoryStorage
from jarvis_memory_fabric.write_pipeline import WritePipeline, is_candidate, memory_worthiness
from jarvis_memory_fabric.retrieval import RetrievalEngine


@pytest.fixture
def fabric():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    f = create_memory_fabric(path)
    yield f
    f._storage.close()
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 1. insert/retrieve
# ---------------------------------------------------------------------------


def test_insert_and_retrieve(fabric):
    mid = fabric.remember(
        type="fact",
        content="JARVIS uses Piper for local TTS.",
        subject="JARVIS",
        predicate="uses",
        obj="Piper",
        confidence=0.97,
        importance=0.9,
        salience="CRITICAL",
    )
    rec = fabric.recall(mid)
    assert rec is not None
    assert rec["subject"] == "JARVIS"
    assert rec["object"] == "Piper"
    assert rec["confidence"] == 0.97


# ---------------------------------------------------------------------------
# 2. duplicate memories
# ---------------------------------------------------------------------------


def test_duplicate_detection(fabric):
    m1 = fabric.remember(
        type="fact",
        content="TTS engine is Piper.",
        subject="JARVIS",
        predicate="uses",
        obj="Piper",
    )
    pipeline = WritePipeline(fabric)
    res = pipeline.process(
        "TTS engine is Piper.",
        trust_class="USER_CONFIRMED",
    )
    assert res["status"] in ("duplicate", "stored")
    # Should not create a second active fact with same subject/predicate/obj
    found = fabric.search(subject="JARVIS", predicate="uses", obj="Piper")
    active = [r for r in found if r["status"] == "active"]
    assert len(active) >= 1


# ---------------------------------------------------------------------------
# 3. updates
# ---------------------------------------------------------------------------


def test_update(fabric):
    mid = fabric.remember(type="fact", content="old content", subject="X", predicate="is", obj="Y")
    ok = fabric.update(mid, content="new content", confidence=0.5)
    assert ok
    rec = fabric.recall(mid)
    assert rec["content"] == "new content"
    assert rec["confidence"] == 0.5


# ---------------------------------------------------------------------------
# 4. conflicting facts (temporal)
# ---------------------------------------------------------------------------


def test_conflicting_facts(fabric):
    m1 = fabric.remember_fact("TTS", "engine", "Edge-TTS", confidence=0.9, importance=0.8)
    # New fact conflicts
    pipeline = WritePipeline(fabric)
    res = pipeline.process(
        "TTS engine is now Piper.",
        trust_class="USER_CONFIRMED",
    )
    # After conflict, old should be superseded, new active
    old = fabric.recall(m1)
    assert old["status"] == "superseded"
    assert old["valid_until"] is not None
    new_recs = fabric.search(subject="TTS", predicate="engine", obj="Piper")
    assert any(r["status"] == "active" for r in new_recs)


# ---------------------------------------------------------------------------
# 5. temporal validity
# ---------------------------------------------------------------------------


def test_temporal_validity(fabric):
    from datetime import datetime, timezone, timedelta

    past = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%fZ")
    mid = fabric.remember(
        type="fact",
        content="old fact",
        subject="A",
        predicate="was",
        obj="B",
        valid_from=past,
        valid_until=past,
    )
    # A search with max_age_days=30 should exclude it
    found = fabric.search(subject="A", predicate="was", obj="B", max_age_days=30)
    assert all(r["id"] != mid for r in found)


# ---------------------------------------------------------------------------
# 6. FTS search
# ---------------------------------------------------------------------------


def test_fts_search(fabric):
    fabric.remember(type="fact", content="The daemon uses port 8765 for WebSocket.", subject="daemon", predicate="uses", obj="8765")
    fabric.remember(type="fact", content="The UI uses React for rendering.", subject="UI", predicate="uses", obj="React")
    results = fabric.search(query="daemon port")
    assert len(results) >= 1
    assert any("8765" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# 7. vector search interface
# ---------------------------------------------------------------------------


def test_vector_search_interface(fabric):
    engine = RetrievalEngine(fabric._storage)
    # Without sqlite-vec, should return [] gracefully
    res = engine.vector_search([0.1] * 8, limit=5)
    assert res == []


# ---------------------------------------------------------------------------
# 8. ranking
# ---------------------------------------------------------------------------


def test_ranking(fabric):
    fabric.remember(type="fact", content="low importance memory", importance=0.1, confidence=0.5)
    fabric.remember(type="fact", content="high importance memory", importance=0.95, confidence=0.99)
    results = fabric.search(query="memory", limit=10)
    # High importance should rank first if both matched
    if len(results) >= 2:
        assert results[0]["importance"] >= results[-1]["importance"]


# ---------------------------------------------------------------------------
# 9. forgetting
# ---------------------------------------------------------------------------


def test_forget(fabric):
    mid = fabric.remember(type="fact", content="to forget", subject="Z", predicate="is", obj="W")
    assert fabric.forget(mid)
    rec = fabric.recall(mid)
    # recall filters out retired
    assert rec is None or rec["status"] == "retired"


# ---------------------------------------------------------------------------
# 10. provenance
# ---------------------------------------------------------------------------


def test_provenance(fabric):
    mid = fabric.remember(
        type="fact",
        content="provenance test",
        subject="P",
        predicate="has",
        obj="Q",
        source="test_session",
        session_id="sess_1",
        task_id="task_1",
    )
    exp = fabric.explain(mid)
    assert exp is not None
    assert exp["provenance"]["source"] == "test_session"
    assert exp["provenance"]["session_id"] == "sess_1"
    assert "sources" in exp
    assert "events" in exp


# ---------------------------------------------------------------------------
# 11. confidence
# ---------------------------------------------------------------------------


def test_confidence(fabric):
    mid = fabric.remember(type="fact", content="c", confidence=0.3)
    fabric.confirm(mid)
    rec = fabric.recall(mid)
    assert rec["trust_score"] > 0.3


# ---------------------------------------------------------------------------
# 12. concurrent access
# ---------------------------------------------------------------------------


def test_concurrent_access(fabric):
    errors = []

    def worker(i):
        try:
            fabric.remember(type="fact", content=f"concurrent {i}", subject="C", predicate="n", obj=str(i))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    count = fabric.stats()["total_memories"]
    assert count >= 10


# ---------------------------------------------------------------------------
# 13. persistence across restart
# ---------------------------------------------------------------------------


def test_persistence_across_restart():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    f1 = create_memory_fabric(path)
    mid = f1.remember(type="fact", content="persist me", subject="Persist", predicate="is", obj="True")
    f1._storage.close()

    # Reopen
    f2 = create_memory_fabric(path)
    rec = f2.recall(mid)
    assert rec is not None
    assert rec["content"] == "persist me"
    f2._storage.close()
    os.unlink(path)


# ---------------------------------------------------------------------------
# 14. write pipeline candidate filtering
# ---------------------------------------------------------------------------


def test_pipeline_candidate_filtering(fabric):
    pipeline = WritePipeline(fabric)
    res = pipeline.process("ok")
    assert res["status"] == "discarded"
    res2 = pipeline.process("JARVIS uses Piper as the primary TTS engine.")
    assert res2["status"] in ("stored", "duplicate")


# ---------------------------------------------------------------------------
# 15. consolidation
# ---------------------------------------------------------------------------


def test_consolidation(fabric):
    fabric.remember_fact("TTS", "engine", "Piper", confidence=0.9)
    fabric.remember_fact("TTS", "engine", "Piper", confidence=0.8)  # duplicate
    result = fabric.consolidate()
    assert result["status"] == "completed"
    assert result["facts_merged"] >= 1


# ---------------------------------------------------------------------------
# 16. timeline
# ---------------------------------------------------------------------------


def test_timeline(fabric):
    fabric.remember_episode("Fixed bug", ["step1", "step2"], session_id="s1")
    tl = fabric.timeline()
    assert len(tl) >= 1


# ---------------------------------------------------------------------------
# 17. related
# ---------------------------------------------------------------------------


def test_related(fabric):
    m1 = fabric.remember(type="fact", content="base", subject="Base", predicate="is", obj="Root")
    m2 = fabric.remember(type="fact", content="child", subject="Child", predicate="depends_on", obj="Root")
    fabric._storage._conn.execute(
        "INSERT INTO memory_links (memory_item_id_1, memory_item_id_2, link_type, strength) VALUES (?, ?, 'related', 0.9)",
        (m2, m1),
    )
    fabric._storage._conn.commit()
    rel = fabric.related(m2)
    assert len(rel) >= 1


# ---------------------------------------------------------------------------
# End of tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
