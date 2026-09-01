"""MemoryController — orchestration layer (Stage 1A).

Owns all memory backends and exposes a single way to store, retrieve, update
and delete memories. Nothing above this class touches SQLite, the vector
index, JSON, or decision tables directly.

Write path keeps the *fast* stores synchronous (KV, metadata, tiers) and
delegates the *expensive* work (embeddings, graph triples) to the background
worker so chat never blocks. The vector DB stays a pure similarity index;
scoring signals live in the metadata store.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from core.context.selector import score as _lexical_score
from memory.extractor import MemoryExtractor
from memory.graph import KnowledgeGraph
from memory.lifecycle import PRIORITY_LOW, MemoryLifecycle
from memory.metadata import MetadataStore
from memory.models import DECISION, KnowledgeTriple, MemoryItem
from memory.ranking import HybridRanker, ImportanceScorer, decay_importance
from memory.tiered_store import TieredMemoryStore

logger = logging.getLogger("jarvis.memory.controller")

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")
_TRIPLE_RE = re.compile(r"(\w+)\s+(?:is|has|has a|likes|works at|lives in|uses)\s+(\w[\w\s]*)", re.IGNORECASE)


def _make_key(item: MemoryItem) -> str:
    slug = _SLUG_RE.sub("_", item.content[:40].lower()).strip("_")
    return f"{item.type}:{slug or 'item'}"


class MemoryController:
    """Compose the memory backends behind one stable interface."""

    def __init__(
        self,
        kv=None,
        vector=None,
        decisions=None,
        knowledge=None,
        tiers=None,
        graph: KnowledgeGraph | None = None,
        metadata: MetadataStore | None = None,
        extractor: MemoryExtractor | None = None,
        scorer: ImportanceScorer | None = None,
        ranker: HybridRanker | None = None,
        lifecycle: MemoryLifecycle | None = None,
    ):
        self._kv = kv
        self._vector = vector
        self._decisions = decisions
        self._knowledge = knowledge

        self._data_dir: Path = getattr(kv, "_data_dir", None) or (Path.home() / ".jarvis" / "data")
        # Metadata / tiers / graph follow the primary store's data dir.
        self._metadata = metadata or (MetadataStore(self._data_dir) if kv is not None else None)
        self._tiers = tiers or (TieredMemoryStore(self._data_dir) if kv is not None else None)
        self._graph = graph or (KnowledgeGraph(path=self._data_dir / "knowledge_graph.json") if kv is not None else None)  # noqa: E501

        self._extractor = extractor or MemoryExtractor()
        self._scorer = scorer or ImportanceScorer()
        self._ranker = ranker or HybridRanker()
        self._lifecycle = lifecycle or MemoryLifecycle()

    # ── write path ────────────────────────────────────────────────────
    def store(self, item: MemoryItem, key: str | None = None) -> str:
        """Persist an item across backends. Returns the stable key."""
        item = _as_item(item)
        key = key or item.id or _make_key(item)
        item.id = key
        item.importance = max(0.0, min(1.0, item.importance))

        if self._kv is not None:
            self._kv.store(key, item.content, category=item.type, importance=item.importance)
        if self._metadata is not None:
            self._metadata.upsert(
                key, type=item.type, project=item.project,
                importance=item.importance, confidence=item.confidence, source=item.source,
            )
        if self._tiers is not None:
            self._tiers.store(key, item.content, tier="hot")

        # Expensive work → background worker (never on the chat path).
        if self._vector is not None:
            self._lifecycle.embed(self._embed_text, key, item)
        if self._graph is not None:
            self._lifecycle.graph_update(self._graph_add_from_item, item)

        if item.type == DECISION and self._decisions is not None:
            self._store_decision(item)
        return key

    def update(self, key: str, item: MemoryItem) -> str:
        """Overwrite an existing memory by key (same backends as store)."""
        item.id = key
        return self.store(item, key=key)

    def delete(self, key: str) -> bool:
        """Remove a memory by key from every backend that tracks it."""
        deleted = False
        if self._kv is not None:
            deleted = self._kv.delete(key) or deleted
        if self._metadata is not None:
            self._metadata.remove(key)
        if self._tiers is not None:
            self._tiers.delete(key)
        return deleted

    # ── retrieval ─────────────────────────────────────────────────────
    def retrieve_items(
        self,
        query: str,
        project: str = "",
        top_k: int = 3,
        min_score: float = 0.15,
    ) -> list[MemoryItem]:
        """Merged candidates from every source, hybrid-ranked, top_k returned."""
        candidates: list[MemoryItem] = []

        # Hot-tier fast path — point lookups by exact key are near-free.
        # Only useful when the caller already knows the key (e.g. follow-up
        # queries on a recently stored item), but costs almost nothing to try.
        if self._tiers is not None:
            hot = self._tiers.retrieve(query)
            if hot is not None:
                candidates.append(MemoryItem(
                    id=f"tier:{query}", content=str(hot),
                    type="hot", importance=0.8,
                    last_accessed=time.time(), access_count=1,
                ))
                candidates[-1]._signals = {"semantic": 0.5, "lexical": 0.5}

        if self._vector is not None:
            for hit in self._vector.search_similar(query, top_k=max(top_k * 3, 3), min_score=min_score):
                meta = self._metadata.get(str(hit["id"])) if self._metadata else None
                item = MemoryItem(
                    id=f"v:{hit['id']}",
                    content=hit["text"],
                    type=hit["category"],
                    importance=meta["importance"] if meta else 0.5,
                    last_accessed=meta["last_used"] if meta else hit.get("created_at", time.time()),
                    access_count=meta["access_count"] if meta else 0,
                    project=(meta or {}).get("project", ""),
                    created_at=hit.get("created_at", time.time()),
                )
                item._signals = {"semantic": hit["score"], "lexical": 0.0}
                candidates.append(item)

        if self._kv is not None:
            for row in self._kv.search_lexical(query, limit=max(top_k * 3, 3)):
                key = row["key"]
                meta = self._metadata.get(key) if self._metadata else None
                lexical = _lexical_score(f"{key.replace('_', ' ')} {row['value']}", query)
                item = MemoryItem(
                    id=f"kv:{key}",
                    content=row["value"],
                    type=row["category"],
                    importance=meta["importance"] if meta else 0.5,
                    last_accessed=meta["last_used"] if meta else time.time(),
                    access_count=meta["access_count"] if meta else 0,
                    project=(meta or {}).get("project", ""),
                    created_at=(meta or {}).get("created", time.time()),
                )
                item._signals = {"semantic": 0.0, "lexical": lexical}
                candidates.append(item)

        if self._decisions is not None:
            for row in self._decisions.recall(project=project, query=query, limit=max(top_k * 3, 3)):
                content = f"{row.get('goal')} — {row.get('decision')} ({row.get('rationale')})"
                item = MemoryItem(
                    id=f"d:{row['id']}",
                    content=content,
                    type=DECISION,
                    project=row.get("project", ""),
                    importance=0.7,
                    created_at=row.get("created_at", time.time()),
                    last_accessed=row.get("created_at", time.time()),
                    metadata={k: row.get(k) for k in ("goal", "decision", "rationale", "outcome")},
                )
                item._signals = {"semantic": 0.0, "lexical": _lexical_score(content, query)}
                candidates.append(item)

        if self._knowledge is not None:
            for row in self._knowledge.search(project, query=query, limit=max(top_k * 3, 3)):
                item = MemoryItem(
                    id=f"k:{row['key']}",
                    content=row["content"],
                    type=row.get("category", "project"),
                    project=project,
                    importance=0.6,
                )
                item._signals = {"semantic": 0.0, "lexical": _lexical_score(f"{row['key']} {row['content']}", query)}
                candidates.append(item)

        if self._lifecycle is not None:
            candidates.extend(self._lifecycle.recall_session(query, top_k=top_k))

        if not candidates:
            return []

        # Deduplicate by (id + normalized content) — the same fact stored
        # in KV and vector (or recalled from session) should appear only
        # once, but different keys with identical content are intentional.
        seen: set[str] = set()
        unique: list[MemoryItem] = []
        for item in candidates:
            norm = item.content.strip().lower()[:200]
            dedup_key = f"{item.id}|{norm}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            unique.append(item)
        candidates = unique

        now = time.time()
        ranked = []
        for item in candidates:
            signals = getattr(item, "_signals", {})
            score = self._ranker.score(
                item, query, query_project=project,
                semantic=signals.get("semantic", 0.0),
                lexical=signals.get("lexical", 0.0),
                now=now,
            )
            item._signals = {"score": score}
            ranked.append((score, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)

        top = [item for score, item in ranked[:top_k]]
        # Record usage for the memories we actually return (prior-usefulness signal).
        if self._metadata is not None:
            for item in top:
                logical = str(item.id)
                if logical.startswith("kv:"):
                    self._metadata.touch(logical[3:])
                elif logical.startswith("v:"):
                    self._metadata.touch(logical)
        return top

    def retrieve(
        self,
        query: str,
        project: str = "",
        top_k: int = 3,
        min_score: float = 0.15,
        use_llm_enhance: bool = True,
    ) -> list[dict[str, Any]]:
        """Legacy-shaped results for existing callers (CLI/cockpit/tests).

        When use_llm_enhance=True, uses the 1B model to reformulate the
        query and rerank results for better relevance.
        """
        _SOURCE_NAMES = {"v": "vector", "kv": "kv", "d": "decision", "k": "knowledge"}

        # Optional 1B enhancement: reformulate query before retrieval
        search_query = query
        if use_llm_enhance:
            try:
                from memory.llm_enhance import reformulate_query
                search_query = reformulate_query(query)
            except Exception:
                pass

        items = self.retrieve_items(search_query, project=project, top_k=top_k * 2, min_score=min_score)

        # Optional 1B reranking
        if use_llm_enhance and items:
            try:
                from memory.llm_enhance import rerank_memories
                item_dicts = [
                    {"content": i.content, "type": i.type, "score": getattr(i, "_signals", {}).get("score", 0.0)}
                    for i in items
                ]
                reranked = rerank_memories(query, item_dicts, max_results=top_k)
                # Map back to items (by content match)
                reranked_contents = {m["content"][:100] for m in reranked}
                items = [i for i in items if i.content[:100] in reranked_contents][:top_k]
            except Exception:
                items = items[:top_k]
        else:
            items = items[:top_k]

        out = []
        for item in items:
            prefix = str(item.id).split(":", 1)[0]
            out.append({
                "source": _SOURCE_NAMES.get(prefix, prefix),
                "key": str(item.id),
                "content": item.content,
                "category": item.type,
                "score": getattr(item, "_signals", {}).get("score", 0.0),
            })
        return out

    # ── decision / knowledge helpers ──────────────────────────────────
    def record_decision(self, item: MemoryItem) -> int | None:
        if self._decisions is None:
            return None
        return self._store_decision(item)

    def _store_decision(self, item: MemoryItem) -> int | None:
        meta = item.metadata or {}
        return self._decisions.record(
            goal=meta.get("goal") or item.content,
            decision=meta.get("decision") or "completed",
            rationale=meta.get("rationale", ""),
            outcome=meta.get("outcome", ""),
            project=item.project,
            metadata={
                k: meta.get(k) for k in ("alternatives", "impact", "related_files")
                if meta.get(k)
            },
        )

    # ── background tasks (run in the worker) ──────────────────────────
    def _embed_text(self, key: str, item: MemoryItem) -> None:
        if self._vector is None:
            return
        self._vector.store_vector(f"{item.type} | {item.content}", category=item.type)

    def _graph_add_from_item(self, item: MemoryItem) -> None:
        if self._graph is None:
            return
        for raw_subj, raw_obj in _TRIPLE_RE.findall(item.content):
            subject = raw_subj.strip().lower()
            obj = raw_obj.strip()
            if len(subject) > 2 and len(obj) > 1:
                self._graph.add_triple(KnowledgeTriple(
                    subject=subject.title(), relation="is", obj=obj,
                    confidence=item.importance, source=item.source,
                ))

    def decay_and_compact(self) -> None:
        """LOW-priority job: decay stale importance, clean the hot tier."""
        if self._metadata is not None:
            now = time.time()
            for row in self._metadata.list(limit=500):
                age_days = (now - row["last_used"]) / 86400.0
                if age_days > 14:
                    self._metadata.set_importance(row["memory_key"], decay_importance(row["importance"], age_days))
        if self._tiers is not None:
            self._tiers.cleanup(max_age_hours=72)

    def schedule_decay(self) -> None:
        self._lifecycle.enqueue(PRIORITY_LOW, self.decay_and_compact)

    # ── conversation pipeline ─────────────────────────────────────────
    def process_conversation(self, text: str, source: str = "", project: str = "") -> list[MemoryItem]:
        """Extract facts off the chat path, buffer as session memory, and
        promote important ones to long-term (HIGH queue)."""
        items = self._extractor.extract(text, source=source, project=project)
        for item in items:
            self._lifecycle.store_session(item, promote_fn=self.store)
        return items

    # ── stats / lifecycle ─────────────────────────────────────────────
    def get_stats(self) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        if self._kv is not None:
            kv_stats = self._kv.get_stats()
            stats["memories"] = kv_stats.get("memories", 0)
            stats["conversations"] = kv_stats.get("conversations", 0)
        if self._decisions is not None:
            stats["decisions"] = self._decisions.get_stats().get("decisions", 0)
        if self._knowledge is not None:
            stats["knowledge"] = self._knowledge.get_stats().get("knowledge", 0)
        if self._vector is not None:
            stats["vector"] = getattr(self._vector, "count", lambda: 0)()
        if self._metadata is not None:
            stats["metadata"] = self._metadata.count()
        if self._tiers is not None:
            stats["tiers"] = self._tiers.get_stats()
        if self._graph is not None:
            stats["triples"] = self._graph.size
        if self._lifecycle is not None and (self._kv or self._vector or self._decisions or self._knowledge):
            stats.update(self._lifecycle.get_stats())
        # Stable minimum so callers can always rely on these keys.
        stats.setdefault("memories", 0)
        stats.setdefault("decisions", 0)
        stats.setdefault("knowledge", 0)
        return stats

    def close(self) -> None:
        if self._lifecycle is not None:
            self._lifecycle.close()
        for backend in (self._kv, self._vector, self._decisions, self._knowledge,
                        self._metadata, self._tiers):
            if backend is not None and hasattr(backend, "close"):
                backend.close()


def _as_item(item: MemoryItem | str | dict[str, Any]) -> MemoryItem:
    if isinstance(item, MemoryItem):
        return item
    if isinstance(item, str):
        return MemoryItem(content=item)
    if isinstance(item, dict):
        return MemoryItem.from_dict(item)
    raise TypeError(f"Cannot store {type(item).__name__} as a memory")
