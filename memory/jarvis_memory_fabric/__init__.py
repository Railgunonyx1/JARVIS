"""
JARVIS Memory Fabric — Public Memory API

Thin facade over storage + retrieval. Exposes the complete Memory API
from the architecture: remember, recall, search, update, forget, confirm,
correct, explain, timeline, related, consolidate, stats.

Backend-agnostic: works with any MemoryStorage implementation.
No LLM calls are made here — extraction is optional and injected separately.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from datetime import datetime

from .storage import MemoryStorage
from .storage_sqlite import SQLiteMemoryStorage
from .retrieval import RetrievalEngine
from .write_pipeline import WritePipeline


class MemoryFabric:
    """Public API for the JARVIS Memory Fabric.

    Usage:
        fabric = MemoryFabric(SQLiteMemoryStorage("jarvis.db"))
        mid = fabric.remember(type="fact", content="...", subject="J", predicate="uses", obj="Piper")
        rec = fabric.recall(mid)
        results = fabric.search(query="what TTS does JARVIS use?")
    """

    def __init__(
        self,
        storage: MemoryStorage,
        *,
        retrieval: Optional[RetrievalEngine] = None,
        enable_vec: bool = False,
        vec_dim: int = 768,
    ) -> None:
        self._storage = storage
        self._retrieval = retrieval or RetrievalEngine(storage)

    # ------------------------------------------------------------------
    # remember
    # ------------------------------------------------------------------

    def remember(
        self,
        *,
        type: str,
        content: str,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        confidence: float = 1.0,
        importance: float = 0.5,
        salience: str = "MEDIUM",
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        source: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        return self._storage.remember(
            type=type,
            content=content,
            subject=subject,
            predicate=predicate,
            obj=obj,
            confidence=confidence,
            importance=importance,
            salience=salience,
            session_id=session_id,
            task_id=task_id,
            source=source,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # recall
    # ------------------------------------------------------------------

    def recall(self, memory_item_id: str) -> Optional[Dict[str, Any]]:
        return self._storage.recall(memory_item_id)

    # ------------------------------------------------------------------
    # search (hybrid)
    # ------------------------------------------------------------------

    def search(
        self,
        *,
        query: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        entity: Optional[str] = None,
        type: Optional[str] = None,
        salience: Optional[str] = None,
        min_confidence: float = 0.0,
        max_age_days: Optional[int] = None,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        return self._retrieval.retrieve(
            query=query,
            embedding=embedding,
            subject=subject,
            predicate=predicate,
            obj=obj,
            entity=entity,
            type=type,
            salience=salience,
            min_confidence=min_confidence,
            max_age_days=max_age_days,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    def update(self, memory_item_id: str, **kwargs: Any) -> bool:
        return self._storage.update(memory_item_id, **kwargs)

    # ------------------------------------------------------------------
    # forget
    # ------------------------------------------------------------------

    def forget(self, memory_item_id: str) -> bool:
        return self._storage.forget(memory_item_id)

    # ------------------------------------------------------------------
    # confirm
    # ------------------------------------------------------------------

    def confirm(self, memory_item_id: str) -> bool:
        return self._storage.confirm(memory_item_id)

    # ------------------------------------------------------------------
    # correct
    # ------------------------------------------------------------------

    def correct(self, memory_item_id: str, **correction: Any) -> bool:
        return self._storage.correct(memory_item_id, **correction)

    # ------------------------------------------------------------------
    # explain
    # ------------------------------------------------------------------

    def explain(self, memory_item_id: str) -> Optional[Dict[str, Any]]:
        return self._storage.explain(memory_item_id)

    # ------------------------------------------------------------------
    # timeline
    # ------------------------------------------------------------------

    def timeline(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        entity: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return self._storage.timeline(start=start, end=end, entity=entity, limit=limit)

    # ------------------------------------------------------------------
    # related
    # ------------------------------------------------------------------

    def related(
        self,
        memory_item_id: str,
        link_types: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return self._storage.related(memory_item_id, link_types=link_types, limit=limit)

    # ------------------------------------------------------------------
    # consolidate
    # ------------------------------------------------------------------

    def consolidate(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        return self._storage.consolidate(job_id=job_id)

    # ------------------------------------------------------------------
    # stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        return self._storage.stats()

    # ------------------------------------------------------------------
    # Convenience helpers for the six memory layers
    # ------------------------------------------------------------------

    def remember_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        *,
        confidence: float = 1.0,
        importance: float = 0.5,
        salience: str = "MEDIUM",
        **kwargs: Any,
    ) -> str:
        return self.remember(
            type="fact",
            content=f"{subject} {predicate} {obj}",
            subject=subject,
            predicate=predicate,
            obj=obj,
            confidence=confidence,
            importance=importance,
            salience=salience,
            **kwargs,
        )

    def remember_episode(
        self,
        title: str,
        events: List[str],
        *,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        import json

        mid = self.remember(
            type="episode",
            content=description or title,
            subject=None,
            predicate=None,
            obj=None,
            session_id=session_id,
            task_id=task_id,
            **kwargs,
        )
        # Insert episode-specific row
        self._storage._conn.execute(
            "INSERT INTO episodes (id, memory_item_id, session_id, task_id, title, description, events, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"ep_{mid[4:]}",
                mid,
                session_id,
                task_id,
                title,
                description or title,
                json.dumps(events),
                "complete",
            ),
        )
        self._storage._conn.commit()
        return mid

    def remember_procedure(
        self,
        name: str,
        *,
        prerequisites: Optional[List[str]] = None,
        command: Optional[str] = None,
        port: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
        verification: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        import json

        mid = self.remember(
            type="procedure",
            content=name,
            subject=None,
            predicate=None,
            obj=None,
            **kwargs,
        )
        self._storage._conn.execute(
            "INSERT INTO procedures (id, memory_item_id, name, prerequisites, command, port, params, verification) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"proc_{mid[4:]}",
                mid,
                name,
                json.dumps(prerequisites or []),
                command,
                port,
                json.dumps(params or {}),
                verification,
            ),
        )
        self._storage._conn.commit()
        return mid


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def create_memory_fabric(
    db_path: str = "jarvis_memory.db",
    *,
    enable_vec: bool = False,
    vec_dim: int = 768,
) -> MemoryFabric:
    """Create a MemoryFabric with a SQLite backend."""
    storage = SQLiteMemoryStorage(db_path, enable_vec=enable_vec, vec_dim=vec_dim)
    return MemoryFabric(storage, enable_vec=enable_vec, vec_dim=vec_dim)


# ---------------------------------------------------------------------------
# End of Memory API facade
# ---------------------------------------------------------------------------

__all__ = [
    "MemoryFabric",
    "create_memory_fabric",
    "WritePipeline",
    "RetrievalEngine",
]
