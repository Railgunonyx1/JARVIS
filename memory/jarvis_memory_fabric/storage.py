"""
JARVIS Memory Fabric — Storage Abstraction Layer

Defines the interface for Memory Fabric storage operations.
SQLite implementation is behind this interface.
Designed to support sqlite-vec extension without rewriting the memory layer.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Tuple, Iterator, Union
from datetime import datetime, timezone
import abc

# ---------------------------------------------------------------------------
# Type aliases for memory record fields
# ---------------------------------------------------------------------------

MemoryRecord = Dict[str, Any]
MemoryItemId = str
SessionId = str
TaskId = str

# ---------------------------------------------------------------------------
# Abstract base class — the storage contract
# ---------------------------------------------------------------------------


class MemoryStorage(abc.ABC):
    """Abstract base class defining the Memory Fabric storage contract.

    Implementations must be thread-safe for the intended deployment model.
    The SQLite implementation lives in jarvis_memory.storage_sqlite.
    """

    @abc.abstractmethod
    def remember(
        self,
        *,
        type: str,
        content: str,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,  # use obj to avoid pred conflict
        confidence: float = 1.0,
        importance: float = 0.5,
        salience: str = "MEDIUM",
        session_id: Optional[SessionId] = None,
        task_id: Optional[TaskId] = None,
        source: Optional[str] = None,
        **kwargs: Any,
    ) -> MemoryItemId:
        """Insert a new memory record and return its ID."""
        ...

    @abc.abstractmethod
    def recall(self, memory_item_id: MemoryItemId) -> Optional[MemoryRecord]:
        """Retrieve a single memory record by ID."""
        ...

    @abc.abstractmethod
    def search(
        self,
        *,
        query: Optional[str] = None,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        entity: Optional[str] = None,
        type: Optional[str] = None,
        salience: Optional[str] = None,
        min_confidence: float = 0.0,
        max_age_days: Optional[int] = None,
        limit: int = 50,
        sort_by: Optional[str] = None,
        ascending: bool = False,
    ) -> List[MemoryRecord]:
        """Search memories with hybrid filtering (FTS5 + metadata)."""
        ...

    @abc.abstractmethod
    def update(
        self,
        memory_item_id: MemoryItemId,
        **kwargs: Any,
    ) -> bool:
        """Update fields of an existing memory record. Returns True if updated."""
        ...

    @abc.abstractmethod
    def forget(self, memory_item_id: MemoryItemId) -> bool:
        """Soft-delete or retire a memory record. Returns True if removed."""
        ...

    @abc.abstractmethod
    def confirm(self, memory_item_id: MemoryItemId) -> bool:
        """Mark a memory as user-confirmed, boosting its trust_score."""
        ...

    @abc.abstractmethod
    def correct(self, memory_item_id: MemoryItemId, **correction: Any) -> bool:
        """Apply a correction to a memory record (creates version history)."""
        ...

    @abc.abstractmethod
    def explain(self, memory_item_id: MemoryItemId) -> Optional[Dict[str, Any]]:
        """Return provenance/evidence for why a memory exists."""
        ...

    @abc.abstractmethod
    def timeline(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        entity: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        """Retrieve memories within a temporal window, ordered by timestamp."""
        ...

    @abc.abstractmethod
    def related(
        self,
        memory_item_id: MemoryItemId,
        link_types: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[MemoryRecord]:
        """Find memories linked to the given item (via memory_links)."""
        ...

    @abc.abstractmethod
    def consolidate(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        """Run consolidation: merge duplicates, resolve conflicts, update summaries."""
        ...

    @abc.abstractmethod
    def stats(self) -> Dict[str, Any]:
        """Return statistics about the memory store."""
        ...

    @abc.abstractmethod
    def session_memory(self, session_id: SessionId) -> Dict[str, Any]:
        """Return all memories associated with a session."""
        ...

    @abc.abstractmethod
    def close(self) -> None:
        """Close the underlying storage connection."""
        ...


# ---------------------------------------------------------------------------
# Helper: build an FTS5 virtual table definition
# ---------------------------------------------------------------------------

FTS5_VTAB_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    content,
    content='memory_items',
    content_rowid='rowid'
);
"""

# Populate FTS5 when memory_items changes (triggered from the SQLite impl)


# ---------------------------------------------------------------------------
# End of abstraction layer
# ---------------------------------------------------------------------------

__all__ = [
    "MemoryStorage",
    "MemoryRecord",
    "MemoryItemId",
    "SessionId",
    "TaskId",
    "FTS5_VTAB_SQL",
]