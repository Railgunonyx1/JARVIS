"""
Audit Log — Action tracking and compliance logging for JARVIS MK-X.

Records every action with full context for security auditing.
SQLite-backed with buffered writes for performance.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.security.audit")


@dataclass
class AuditEntry:
    """A single audit log entry."""
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    trace_id: str = ""
    action: str = ""
    tool: str = ""
    permission_level: int = 0
    allowed: bool = True
    confirmed: bool = False
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None
    params_hash: str = ""
    mode: str = ""
    decision: str = ""  # once | run | deny (operator confirmation decision)


class AuditLog:
    """SQLite-backed audit log with buffered writes."""

    _FLUSH_INTERVAL = 5.0

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or (Path.home() / ".jarvis" / "data" / "audit.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._buffer: list[tuple] = []
        self._buffer_lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10.0)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                self._conn = conn
            return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                session_id TEXT NOT NULL,
                trace_id TEXT DEFAULT '',
                action TEXT NOT NULL,
                tool TEXT NOT NULL,
                permission_level INTEGER DEFAULT 0,
                allowed INTEGER DEFAULT 1,
                confirmed INTEGER DEFAULT 0,
                duration_ms REAL DEFAULT 0,
                success INTEGER DEFAULT 1,
                error TEXT,
                params_hash TEXT DEFAULT '',
                mode TEXT DEFAULT '',
                decision TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id);
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_tool ON audit_log(tool);
        """)
        # ALTER-migration for pre-existing databases (no trace_id column)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()]
        if "trace_id" not in cols:
            conn.execute("ALTER TABLE audit_log ADD COLUMN trace_id TEXT DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_log(trace_id)")
        if "decision" not in cols:
            conn.execute("ALTER TABLE audit_log ADD COLUMN decision TEXT DEFAULT ''")
        conn.commit()

    def log(self, entry: AuditEntry):
        """Buffer an audit entry for periodic flush."""
        with self._buffer_lock:
            self._buffer.append((
                entry.timestamp, entry.session_id, entry.trace_id, entry.action,
                entry.tool, entry.permission_level, int(entry.allowed),
                int(entry.confirmed), entry.duration_ms, int(entry.success),
                entry.error, entry.params_hash, entry.mode, entry.decision,
            ))
            if self._timer is None or not self._timer.is_alive():
                self._timer = threading.Timer(self._FLUSH_INTERVAL, self._flush)
                self._timer.daemon = True
                self._timer.start()

    def log_immediate(self, entry: AuditEntry):
        """Log immediately (for critical security events)."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO audit_log (timestamp, session_id, trace_id, action, tool, "
            "permission_level, allowed, confirmed, duration_ms, success, error, "
            "params_hash, mode, decision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry.timestamp, entry.session_id, entry.trace_id, entry.action,
             entry.tool, entry.permission_level, int(entry.allowed),
             int(entry.confirmed), entry.duration_ms, int(entry.success),
             entry.error, entry.params_hash, entry.mode, entry.decision)
        )
        conn.commit()

    def _flush(self):
        with self._buffer_lock:
            buffer = self._buffer[:]
            self._buffer.clear()
        if not buffer:
            return
        conn = self._get_conn()
        conn.executemany(
            "INSERT INTO audit_log (timestamp, session_id, trace_id, action, tool, "
            "permission_level, allowed, confirmed, duration_ms, success, error, "
            "params_hash, mode, decision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            buffer
        )
        conn.commit()

    def flush(self):
        self._flush()

    def query(self, session_id: str | None = None, tool: str | None = None,
              since: float | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Query audit log entries."""
        sql = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        if tool:
            sql += " AND tool LIKE ?"
            params.append(f"%{tool}%")
        if since:
            sql += " AND timestamp > ?"
            params.append(since)
        sql += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(limit)

        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_trace(self, trace_id: str, limit: int = 200) -> list[dict[str, Any]]:
        """Return all audit entries for a trace, oldest first."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE trace_id = ? ORDER BY id ASC LIMIT ?",
            (trace_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self, since: float | None = None) -> dict[str, Any]:
        """Get audit statistics."""
        conn = self._get_conn()
        where = "WHERE timestamp > ?" if since else ""
        params = [since] if since else []

        total = conn.execute(f"SELECT COUNT(*) FROM audit_log {where}", params).fetchone()[0]
        denied = conn.execute(f"SELECT COUNT(*) FROM audit_log {where} {'AND' if where else 'WHERE'} allowed = 0", params).fetchone()[0]  # noqa: E501
        failed = conn.execute(f"SELECT COUNT(*) FROM audit_log {where} {'AND' if where else 'WHERE'} success = 0", params).fetchone()[0]  # noqa: E501

        tool_counts = conn.execute(
            f"SELECT tool, COUNT(*) as cnt FROM audit_log {where} GROUP BY tool ORDER BY cnt DESC LIMIT 10",
            params
        ).fetchall()

        return {
            "total_actions": total,
            "denied": denied,
            "failed": failed,
            "top_tools": {r["tool"]: r["cnt"] for r in tool_counts},
        }

    def close(self):
        self._flush()
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None


_audit_log: AuditLog | None = None


def get_audit_log() -> AuditLog:
    """Process-wide singleton AuditLog."""
    global _audit_log
    if _audit_log is None:
        _audit_log = AuditLog()
    return _audit_log
