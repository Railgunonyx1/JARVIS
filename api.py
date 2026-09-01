"""Memory API — the single entry point for the memory system (Stage 1A).

Everything goes through:

    memory.store()
    memory.retrieve()
    memory.update()
    memory.delete()

plus memory-type helpers (Stage 1C). ``get_mem()`` returns the process-wide
instance that the agent loop, CLI and cockpit already use, so the existing
``Mem`` surface keeps working while the internals are now a unified pipeline:

    API → Controller → KV / Vector / Decisions / Knowledge / Metadata / Tiers
                     ↘ Lifecycle worker (embeddings, extraction, graph, decay)

External code never touches the backends directly.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from memory.controller import MemoryController
from memory.models import (
    DECISION,
    EPISODIC,
    PROCEDURAL,
    PROJECT,
    PROJECT_SECTIONS,
    SEMANTIC,
    MemoryItem,
)

logger = logging.getLogger("jarvis.memory.api")

_instance: MemoryAPI | None = None
_instance_lock = threading.Lock()


class MemoryAPI:
    """Unified facade over MemoryController + background lifecycle."""

    def __init__(
        self,
        kv=None,
        vector=None,
        decisions=None,
        knowledge=None,
        mirror_json: bool = False,
    ):
        self._mirror_json = mirror_json
        self._controller = MemoryController(
            kv=kv, vector=vector, decisions=decisions, knowledge=knowledge,
        )

    @property
    def controller(self) -> MemoryController:
        return self._controller

    # Direct backend access — kept for legacy/tests. New code should use the
    # unified methods above, never these.
    @property
    def _kv(self):
        return self._controller._kv

    @property
    def _vector(self):
        return self._controller._vector

    @property
    def _decisions(self):
        return self._controller._decisions

    @property
    def _knowledge(self):
        return self._controller._knowledge

    # ── write path ────────────────────────────────────────────
    def store(
        self,
        content: str,
        key: str | None = None,
        type: str = SEMANTIC,
        project: str = "",
        tags: list[str] | None = None,
        importance: float | None = None,
        confidence: float = 1.0,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a memory; returns the stable key.

        When ``importance`` is omitted the ImportanceScorer estimates it.
        """
        if importance is None:
            importance = self._controller._scorer.score(content)
        item = MemoryItem(
            content=content, type=type, project=project,
            tags=list(tags or []), importance=importance, confidence=confidence,
            source=source, metadata=metadata or {},
        )
        key = key or item.id or self._controller._make_key(item)
        item.id = key
        self._controller.store(item, key=key)
        return key

    def update(self, key: str, item: MemoryItem) -> str:
        """Overwrite an existing memory by key."""
        item.id = key
        return self.store(item, key=key)

    def delete(self, key: str) -> bool:
        """Remove a memory by key from every backend that tracks it."""
        deleted = False
        if self._controller._kv is not None:
            deleted = self._controller._kv.delete(key) or deleted
        if self._controller._metadata is not None:
            self._controller._metadata.remove(key)
        if self._controller._tiers is not None:
            self._controller._tiers.delete(key)
        return deleted

    # ── retrieval ─────────────────────────────────────────────
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
        if self._controller._tiers is not None:
            hot = self._controller._tiers.retrieve(query)
            if hot is not None:
                candidates.append(MemoryItem(
                    id=f"tier:{query}", content=str(hot),
                    type="hot", importance=0.8,
                    last_accessed=time.time(), access_count=1,
                ))
                candidates[-1]._signals = {"semantic": 0.5, "lexical": 0.5}

        if self._controller._vector is not None:
            for hit in self._controller._vector.search_similar(query, top_k=max(top_k * 3, 3), min_score=min_score):
                meta = self._controller._metadata.get(str(hit["id"])) if self._controller._metadata else None
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

        if self._controller._kv is not None:
            for row in self._controller._kv.search_lexical(query, limit=max(top_k * 3, 3)):
                key = row["key"]
                meta = self._controller._metadata.get(key) if self._controller._metadata else None
                from core.context.selector import score as _lexical_score
                lexical = _lexical_score(f"{key.replace('_', ' ')} {row['value']}", query)
                item = MemoryItem(
                    id=f"kv:{key}", content=row["value"],
                    type=row["category"],
                    importance=meta["importance"] if meta else 0.5,
                    last_accessed=meta["last_used"] if meta else time.time(),
                    access_count=meta["access_count"] if meta else 0,
                    project=(meta or {}).get("project", ""),
                    created_at=(meta or {}).get("created", time.time()),
                )
                item._signals = {"semantic": 0.0, "lexical": lexical}
                candidates.append(item)

        if self._controller._decisions is not None:
            for row in self._controller._decisions.recall(project=project, query=query, limit=max(top_k * 3, 3)):
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

        if not candidates:
            return []

        # Deduplicate by (id + normalized content)
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
            score = self._controller._ranker.score(
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
        if self._controller._metadata is not None:
            for item in top:
                logical = str(item.id)
                if logical.startswith("kv:"):
                    self._controller._metadata.touch(logical[3:])
                elif logical.startswith("v:"):
                    self._controller._metadata.touch(logical)
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
        from memory.llm_enhance import reformulate_query, rerank_memories

        # Optional 1B enhancement: reformulate query before retrieval
        search_query = query
        if use_llm_enhance:
            try:
                search_query = reformulate_query(query)
            except Exception:
                pass

        items = self.retrieve_items(search_query, project=project, top_k=top_k * 2, min_score=min_score)

        # Optional 1B reranking
        if use_llm_enhance and items:
            try:
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
            source_names = {"v": "vector", "kv": "kv", "d": "decision", "k": "knowledge"}
            out.append({
                "source": source_names.get(prefix, prefix),
                "key": str(item.id),
                "content": item.content,
                "category": item.type,
                "score": getattr(item, "_signals", {}).get("score", 0.0),
            })
        return out

    # ── decision / knowledge helpers ────────────────────────────
    def record_decision(self, item: MemoryItem) -> int | None:
        if self._controller._decisions is None:
            return None
        return self._controller._store_decision(item)

    def _store_decision(self, item: MemoryItem) -> int | None:
        meta = item.metadata or {}
        return self._controller._decisions.record(
            goal=meta.get("goal") or item.content,
            decision=meta.get("decision") or "completed",
            rationale=meta.get("rationale", ""),
            outcome=meta.get("outcome", ""),
            project=item.project,
            metadata={k: meta.get(k) for k in ("alternatives", "impact", "related_files")
                      if meta.get(k)},
        )

    # ── background tasks (run in the worker) ────────────────────
    def _embed_text(self, key: str, item: MemoryItem) -> None:
        if self._controller._vector is None:
            return
        self._controller._vector.store_vector(f"{item.type} | {item.content}", category=item.type)

    def _graph_add_from_item(self, item: MemoryItem) -> None:
        if self._controller._graph is None:
            return
        import re
        _TRIPLE_RE = re.compile(r"(\w+)\s+(?:is|has|has a|likes|works at|lives in|uses)\s+(\w[\w\s]*)", re.IGNORECASE)
        for raw_subj, raw_obj in _TRIPLE_RE.findall(item.content):
            subject = raw_subj.strip().lower()
            obj = raw_obj.strip()
            if len(subject) > 2 and len(obj) > 1:
                self._controller._graph.add_triple(type('KnowledgeTriple', ('subject', 'relation', 'obj', 'confidence', 'source'), constraints={'subject': lambda s: len(s) > 2, 'obj': lambda o: len(o) > 1})(
                    subject=subject.title(), relation="is", obj=obj,
                    confidence=item.importance, source=item.source,
                ))

    def decay_and_compact(self) -> None:
        """LOW-priority job: decay stale importance, clean the hot tier."""
        if self._controller._metadata is not None:
            now = time.time()
            for row in self._controller._metadata.list(limit=500):
                age_days = (now - row["last_used"]) / 86400.0
                if age_days > 14:
                    self._controller._metadata.set_importance(row["memory_key"], max(0.0, min(1.0, row["importance"] * (0.95 ** age_days))))
        if self._controller._tiers is not None:
            self._controller._tiers.cleanup(max_age_hours=72)

    def schedule_decay(self) -> None:
        self._controller._lifecycle.enqueue(PRIORITY_LOW, self.decay_and_compact)

    # ── conversation pipeline ───────────────────────────────────
    def process_conversation(self, text: str, source: str = "", project: str = "") -> list[MemoryItem]:
        """Extract facts off the chat path, buffer as session memory, and
        promote important ones to long-term (HIGH queue)."""
        from memory.extractor import MemoryExtractor
        items = self._controller._extractor.extract(text, source=source, project=project)
        for item in items:
            self._controller._lifecycle.store_session(item, promote_fn=self.store)
        return items

    # ── stats / lifecycle ───────────────────────────────────────
    def get_stats(self) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        if self._controller._kv is not None:
            kv_stats = self._controller._kv.get_stats()
            stats["memories"] = kv_stats.get("memories", 0)
            stats["conversations"] = kv_stats.get("conversations", 0)
        if self._controller._decisions is not None:
            stats["decisions"] = self._controller._decisions.get_stats().get("decisions", 0)
        if self._controller._knowledge is not None:
            stats["knowledge"] = self._controller._knowledge.get_stats().get("knowledge", 0)
        if self._controller._vector is not None:
            stats["vector"] = getattr(self._controller._vector, "count", lambda: 0)()
        if self._controller._metadata is not None:
            stats["metadata"] = self._controller._metadata.count()
        if self._controller._tiers is not None:
            stats["tiers"] = self._controller._tiers.get_stats()
        if self._controller._graph is not None:
            stats["triples"] = self._controller._graph.size
        if self._controller._lifecycle is not None and (self._controller._kv or self._controller._vector or self._controller._decisions or self._controller._knowledge):
            stats.update(self._controller._lifecycle.get_stats())
        # Stable minimum so callers can always rely on these keys.
        stats.setdefault("memories", 0)
        stats.setdefault("decisions", 0)
        stats.setdefault("knowledge", 0)
        return stats

    def close(self) -> None:
        if self._controller._lifecycle is not None:
            self._controller._lifecycle.close()
        for backend in (self._controller._kv, self._controller._vector, self._controller._decisions, self._controller._knowledge,
                        self._controller._metadata, self._controller._tiers):
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