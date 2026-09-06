"""Event Sourcing Lite — stores important events for debugging and recovery.

Only records semantically meaningful events:
  user.created, plugin.installed, permission.changed, workflow.completed,
  system.startup, system.shutdown, capability.registered

Not every telemetry point — those go to MetricsCollector.
"""
import json
import orjson
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.event_store")

_EVENT_STORE_SIZE = 5000


@dataclass
class StoredEvent:
    name: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    trace_id: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


_PRUNE_EVERY = 250  # run the full-table prune only every N writes


class EventStore:
    """Appends only. Prunes oldest when exceeding max size.

    One persistent SQLite connection (WAL, synchronous=NORMAL) is reused for
    every operation instead of connect/commit/close per event — the audit and
    tool-dispatch paths record events on every tool call, and a fresh
    connection per write made that path spend milliseconds per event.
    """

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            data_dir = Path.home() / ".jarvis" / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "events.db")
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._writes_since_prune = 0
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self._db_path, timeout=5.0,
                                   check_same_thread=False)
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    data TEXT DEFAULT '{}',
                    source TEXT DEFAULT '',
                    trace_id TEXT DEFAULT '',
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_name_ts
                ON events(name, timestamp)
            """)
            conn.commit()
            self._conn = conn
        except Exception as e:
            logger.warning("EventStore DB init failed: %s", e)

    def shutdown(self):
        """Close the persistent connection (best effort)."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def store(self, name: str, data: dict[str, Any] | None = None,
              source: str = "", trace_id: str = ""):
        event = StoredEvent(
            name=name,
            data=data or {},
            source=source,
            trace_id=trace_id,
        )
        try:
            with self._lock:
                if self._conn is None:
                    return
                self._conn.execute(
                    "INSERT INTO events(name, data, source, trace_id, timestamp) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (event.name, orjson.dumps(event.data).decode(), event.source,
                     event.trace_id, event.timestamp)
                )
                self._writes_since_prune += 1
                if self._writes_since_prune >= _PRUNE_EVERY:
                    self._conn.execute(
                        "DELETE FROM events WHERE id NOT IN "
                        "(SELECT id FROM events ORDER BY id DESC LIMIT ?)",
                        (_EVENT_STORE_SIZE,)
                    )
                    self._writes_since_prune = 0
                self._conn.commit()
        except Exception as e:
            logger.debug("EventStore write failed: %s", e)

    def query(self, name: str | None = None,
              limit: int = 100,
              since: float | None = None,
              trace_id: str | None = None) -> list[StoredEvent]:
        try:
            with self._lock:
                if self._conn is None:
                    return []
                conditions, params = [], []
                if name:
                    conditions.append("name = ?")
                    params.append(name)
                if since:
                    conditions.append("timestamp >= ?")
                    params.append(since)
                if trace_id:
                    conditions.append("trace_id = ?")
                    params.append(trace_id)
                where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
                order = "id ASC" if trace_id else "id DESC"
                rows = self._conn.execute(
                    f"SELECT name, data, source, trace_id, timestamp "
                    f"FROM events {where} ORDER BY {order} LIMIT ?",
                    params + [limit]
                ).fetchall()
            return [
                StoredEvent(
                    name=r[0],
                    data=json.loads(r[1]) if r[1] else {},
                    source=r[2] or "",
                    trace_id=r[3] or "",
                    timestamp=r[4],
                )
                for r in rows
            ]
        except Exception:
            return []

    def recent_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        """Distinct trace_ids with their latest event timestamp, newest first."""
        try:
            with self._lock:
                if self._conn is None:
                    return []
                rows = self._conn.execute(
                    "SELECT trace_id, MAX(timestamp) AS last_ts "
                    "FROM events WHERE trace_id != '' "
                    "GROUP BY trace_id ORDER BY MAX(id) DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [
                {"trace_id": r[0], "timestamp": r[1] or 0.0}
                for r in rows
            ]
        except Exception:
            return []

    def count(self) -> int:
        try:
            with self._lock:
                if self._conn is None:
                    return 0
                count = self._conn.execute(
                    "SELECT COUNT(*) FROM events").fetchone()[0]
            return count or 0
        except Exception:
            return 0


_store: EventStore | None = None


def get_event_store() -> EventStore:
    global _store
    if _store is None:
        _store = EventStore()
    return _store


def close_event_store() -> None:
    """Close the singleton store's persistent connection (best effort)."""
    global _store
    if _store is not None:
        _store.shutdown()
        _store = None
