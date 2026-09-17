"""Tests for memory write-time consolidation (mem0-style dedup) and the
vector-store delete path.

Research basis: mem0 (arXiv:2504.19413) — ADD/UPDATE/NO-OP decisions at
write time; Zep/Graphiti (arXiv:2501.13956) — fact invalidation semantics.
JARVIS adaptation: LLM-free Jaccard dedup, in-place UPDATE under a stable
key, episodic memories exempt (append-only), explicit-key writes
authoritative.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from memory.consolidation import find_duplicate, is_tombstone, jaccard
from memory.controller import MemoryController
from memory.metadata import MetadataStore
from memory.models import MemoryItem
from memory.tiered_store import TieredMemoryStore


class KVStub:
    """Minimal lexical KV matching the search_lexical contract."""

    def __init__(self):
        self._rows = {}
        self._data_dir = Path(tempfile.mkdtemp())

    def store(self, key, content, **kw):
        self._rows[key] = dict(value=content, **kw)

    def delete(self, key):
        return self._rows.pop(key, None) is not None

    def search_lexical(self, q, limit=10):
        ql = [w for w in q.lower().split() if len(w) > 2]
        out = []
        for k, v in self._rows.items():
            txt = f"{k.replace('_', ' ')} {v['value']}".lower()
            score = sum(1 for w in ql if w in txt) / max(len(ql), 1)
            if score > 0:
                out.append({
                    "key": k, "value": v["value"],
                    "category": v.get("category", "semantic"),
                })
        out.sort(key=lambda r: -sum(1 for w in ql if w in f"{r['key']} {r['value']}".lower()))
        return out[:limit]


@pytest.fixture
def ctl():
    kv = KVStub()
    tmp = kv._data_dir
    return MemoryController(kv=kv, metadata=MetadataStore(tmp), tiers=TieredMemoryStore(tmp)), kv


class TestJaccard:
    def test_identical(self):
        assert jaccard("user prefers dark mode", "user prefers dark mode") == 1.0

    def test_rephrase_high(self):
        assert jaccard(
            "User prefers dark mode",
            "The user prefers dark mode themes",
        ) >= 0.72

    def test_distinct_low(self):
        assert jaccard(
            "User prefers dark mode",
            "User works on the JARVIS browser project",
        ) < 0.5

    def test_empty_safe(self):
        assert jaccard("", "anything") == 0.0


class TestFindDuplicate:
    def test_skips_tombstoned(self):
        rows = [{"key": "a", "content": "x y", "superseded_by": "b"}]
        assert find_duplicate("x y", rows) is None

    def test_finds_match(self):
        rows = [{"key": "a", "content": "User prefers dark mode"}]
        assert find_duplicate("The user prefers dark mode", rows)["key"] == "a"


class TestConsolidation:
    def test_noop_identical(self, ctl):
        c, _ = ctl
        k1 = c.store(MemoryItem(content="User prefers dark mode", type="preference"))
        assert c.store(MemoryItem(content="User prefers dark mode", type="preference")) == k1

    def test_update_in_place_stable_key(self, ctl):
        c, kv = ctl
        k1 = c.store(MemoryItem(content="User prefers dark mode", type="preference"))
        k2 = c.store(MemoryItem(content="The user prefers dark mode themes", type="preference"))
        assert k2 == k1
        assert "themes" in kv._rows[k1]["value"]

    def test_distinct_facts_both_stored(self, ctl):
        c, _ = ctl
        k1 = c.store(MemoryItem(content="User prefers dark mode", type="preference"))
        k2 = c.store(MemoryItem(content="User works on the JARVIS browser project", type="semantic"))
        assert k1 != k2

    def test_episodic_append_only(self, ctl):
        c, _ = ctl
        e1 = c.store(MemoryItem(content="Visited the Paris office in 2024", type="episodic"))
        e2 = c.store(MemoryItem(content="Visited the Paris office in 2025", type="episodic"))
        assert e1 != e2

    def test_explicit_key_bypasses_consolidation(self, ctl):
        c, _ = ctl
        assert c.store(
            MemoryItem(content="Deploy target is Hetzner", type="semantic"), key="deploy",
        ) == "deploy"

    def test_retrieval_shows_updated_content(self, ctl):
        c, _ = ctl
        c.store(MemoryItem(content="User prefers dark mode", type="preference"))
        c.store(MemoryItem(content="The user prefers dark mode themes", type="preference"))
        contents = [h.content for h in c.retrieve_items("dark mode preference")]
        assert any("themes" in x for x in contents)
        assert not any(x == "User prefers dark mode" for x in contents)


class TestVectorDelete:
    def test_delete_removes_by_key(self):
        from memory.vector_store import VectorMemoryStore

        store = VectorMemoryStore(db_path=Path(tempfile.mkdtemp()) / "v.db")
        store.store_vector("semantic:my_test_key_123", category="semantic")
        assert store.delete("semantic:my_test_key_123") is True
        assert store.delete("semantic:my_test_key_123") is False

    def test_delete_unknown_key_is_noop(self):
        from memory.vector_store import VectorMemoryStore

        store = VectorMemoryStore(db_path=Path(tempfile.mkdtemp()) / "v.db")
        assert store.delete("nonexistent:key") is False
