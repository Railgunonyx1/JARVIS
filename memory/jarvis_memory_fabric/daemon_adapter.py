"""
JARVIS Memory Fabric — Daemon Adapter (stub)

This module demonstrates how the Memory Fabric would integrate with a JARVIS daemon.
It is intentionally minimal — the actual daemon codebase is not available in this
repository, so this stub shows the interface contract without reimplementing the
full architecture.

The pattern is:

  React/Tauri frontend
    ↓ WebSocket / IPC
  JARVIS daemon process
    ↓ Memory API calls
  Memory Fabric (this package)
    ↓ SQLite + FTS5 + sqlite-vec
  Persistent storage

The daemon should import from this package and expose the Memory API over IPC.
"""


from __future__ import annotations

from typing import Optional

from .memory_fabric import MemoryFabric, create_memory_fabric


class DaemonMemoryAdapter:
    """Adapter that a JARVIS daemon would use to embed the Memory Fabric.

    In the real architecture, this would be instantiated once at daemon start,
    and the MemoryFabric instance would be shared across all agent components.

    Example:

        # In the daemon process:
        fabric = DaemonMemoryAdapter.create()
        # Remember a fact from agent activity:
        mid = fabric.remember(
            type="fact",
            content="daemon initialized with VectorStore",
            subject="JARVIS",
            predicate="uses",
            obj="sqlite-vec",
        )
        # Retrieve during agent reasoning:
        rec = fabric.recall(mid)
    """

    _fabric: Optional[MemoryFabric] = None

    @classmethod
    def create(
        cls,
        db_path: str = "jarvis_memory.db",
        *,
        enable_vec: bool = False,
        vec_dim: int = 768,
    ) -> MemoryFabric:
        """Create (or reuse) a MemoryFabric instance for the daemon."""
        if cls._fabric is None:
            cls._fabric = create_memory_fabric(
                db_path,
                enable_vec=enable_vec,
                vec_dim=vec_dim,
            )
        return cls._fabric

    @classmethod
    def close(cls) -> None:
        """Close the underlying storage connection."""
        if cls._fabric is not None:
            cls._fabric._storage.close()
            cls._fabric = None

    # --- Convenience passthroughs to MemoryFabric ---

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
    ) -> str:
        return self._fabric.remember(
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
        )

    def recall(self, memory_item_id: str) -> Optional[dict]:
        return self._fabric.recall(memory_item_id)

    def search(
        self,
        *,
        query: Optional[str] = None,
        embedding: Optional[list] = None,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        entity: Optional[str] = None,
        type: Optional[str] = None,
        salience: Optional[str] = None,
        min_confidence: float = 0.0,
        max_age_days: Optional[int] = None,
        limit: int = 15,
    ) -> list:
        return self._fabric.search(
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

    def update(self, memory_item_id: str, **kwargs) -> bool:
        return self._fabric.update(memory_item_id, **kwargs)

    def forget(self, memory_item_id: str) -> bool:
        return self._fabric.forget(memory_item_id)

    def confirm(self, memory_item_id: str) -> bool:
        return self._fabric.confirm(memory_item_id)

    def correct(self, memory_item_id: str, **correction) -> bool:
        return self._fabric.correct(memory_item_id, **correction)

    def explain(self, memory_item_id: str) -> Optional[dict]:
        return self._fabric.explain(memory_item_id)

    def timeline(
        self,
        start: Optional[object] = None,
        end: Optional[object] = None,
        entity: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        return self._fabric.timeline(start=start, end=end, entity=entity, limit=limit)

    def related(
        self,
        memory_item_id: str,
        link_types: Optional[list] = None,
        limit: int = 20,
    ) -> list:
        return self._fabric.related(memory_item_id, link_types=link_types, limit=limit)

    def consolidate(self, job_id: Optional[str] = None) -> dict:
        return self._fabric.consolidate(job_id=job_id)

    def stats(self) -> dict:
        return self._fabric.stats()


# ---------------------------------------------------------------------------
# Module-level convenience when imported from the daemon
# ---------------------------------------------------------------------------

__all__ = ["DaemonMemoryAdapter"]