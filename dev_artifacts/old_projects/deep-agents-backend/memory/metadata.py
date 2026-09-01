"""Memory metadata store (Stage 1D).

The vector DB answers *"what is similar?"* — the metadata table answers
*"what matters?"*. Every memory gets a row tracking importance, confidence,
recency and prior usefulness so hybrid ranking has real signals and the
vector index stays a pure similarity index.

One key design rule: the vector DB is *not* the source of truth for scoring
fields. They live here.
"""

from __future__ import annotations

import builtins
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

logger = __import__("logging").getLogger("jarvis.memory.metadata")

_IMPORTANCE_BOOST_ON_TOUCH = 0.02  # each useful recall nudges importance up
_ACCESS_SATURATION = 20            # above this, further touches stop boosting


class MetadataStore:
    """SQLite-backed per-memory metadata: importance, confidence, recency, usage."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or (Path.home() / ".jarvis" / "data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "memory_metadata.db"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_metadata (
                memory_key TEXT PRIMARY KEY,
                type TEXT DEFAULT 'semantic',
                project TEXT DEFAULT '',
                importance REAL DEFAULT 0.5,
                confidence REAL DEFAULT 1.0,
                created REAL NOT NULL,
                last_used REAL NOT NULL,
                access_count INTEGER DEFAULT 0,
                source TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_meta_project ON memory_metadata(project);
            CREATE INDEX IF NOT EXISTS idx_meta_type ON memory_metadata(type);
            CREATE INDEX IF NOT EXISTS idx_meta_importance ON memory_metadata(importance DESC);
        """)
        self._conn.commit()

    def upsert(
        self,
        memory_key: str,
        type: str = "semantic",
        project: str = "",
        importance: float = 0.5,
        confidence: float = 1.0,
        source: str = "",
    ) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO memory_metadata
                       (memory_key, type, project, importance, confidence, created, last_used, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(memory_key) DO UPDATE SET
                       type = excluded.type,
                       project = excluded.project,
                       importance = excluded.importance,
                       confidence = excluded.confidence,
                       source = excluded.source,
                       last_used = excluded.last_used""",
                (memory_key, type, project, importance, confidence, now, now, source),
            )
            self._conn.commit()

    def get(self, memory_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memory_metadata WHERE memory_key = ?", (memory_key,),
            ).fetchone()
        return dict(row) if row else None

    def touch(self, memory_key: str) -> None:
        """Record a recall: bump last_used + access_count, small importance boost."""
        with self._lock:
            self._conn.execute(
                """UPDATE memory_metadata SET
                       last_used = ?,
                       access_count = access_count + 1,
                       importance = MIN(1.0,
                           importance + ? * (access_count <= ?))
                   WHERE memory_key = ?""",
                (time.time(), _IMPORTANCE_BOOST_ON_TOUCH, _ACCESS_SATURATION, memory_key),
            )
            self._conn.commit()

    def set_importance(self, memory_key: str, importance: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE memory_metadata SET importance = ? WHERE memory_key = ?",
                (max(0.0, min(1.0, importance)), memory_key),
            )
            self._conn.commit()

    def remove(self, memory_key: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memory_metadata WHERE memory_key = ?", (memory_key,),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def list(self, project: str = "", limit: int = 1000) -> builtins.list[dict[str, Any]]:
        sql = "SELECT * FROM memory_metadata"
        params: list = []
        if project:
            sql += " WHERE project = ?"
            params.append(project)
        sql += " ORDER BY importance DESC, last_used DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) AS c FROM memory_metadata").fetchone()["c"]

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
