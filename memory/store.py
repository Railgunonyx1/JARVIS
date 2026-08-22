"""Memory Store - JSON + SQLite persistent memory for JARVIS MK-X."""

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("jarvis.memory")

# Pre-prime CPU percent so first real call is non-blocking
try:
    import psutil
    psutil.cpu_percent(interval=None)
except Exception:
    pass


@dataclass
class MemoryEntry:
    """A single memory entry."""
    key: str
    value: str
    category: str = "general"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    importance: float = 0.5


class MemoryStore:
    """Dual storage: SQLite for structured data, JSON for quick access.
    Thread-safe with batched commits and write-behind for conversation logs.
    """

    _CONV_FLUSH_INTERVAL = 5.0  # seconds between conversation flushes

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir or Path.home() / ".jarvis" / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "jarvis.db"
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

        # Write-behind for conversation logs
        self._conv_buffer: list[tuple] = []
        self._conv_timer: threading.Timer | None = None
        self._conv_flush_lock = threading.Lock()
        self._closed = False

    def _init_db(self):
        """Initialize SQLite database with required tables."""
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            timeout=10,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA journal_mode = WAL")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                access_count INTEGER DEFAULT 0,
                importance REAL DEFAULT 0.5
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                intent TEXT DEFAULT '',
                timestamp REAL NOT NULL,
                tokens_used INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
            CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversations(timestamp);
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
        """)
        self._conn.commit()

    def store(self, key: str, value: str, category: str = "general", importance: float = 0.5):
        """Store a key-value memory."""
        now = time.time()
        with self._lock:
            self._conn.execute("""
                INSERT INTO memories (key, value, category, created_at, updated_at, importance)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at,
                    importance = excluded.importance
            """, (key, value, category, now, now, importance))
            self._conn.commit()
        logger.info("Memory stored: %s [%s]", key, category)

    def recall(self, key: str) -> str | None:
        """Recall a memory by key."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM memories WHERE key = ?", (key,)
            ).fetchone()
            if row:
                self._conn.execute(
                    "UPDATE memories SET access_count = access_count + 1 WHERE key = ?",
                    (key,)
                )
                self._conn.commit()
                return row["value"]
        return None

    def delete(self, key: str) -> bool:
        """Delete a memory by key."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memories WHERE key = ?", (key,)
            )
            self._conn.commit()
        return cur.rowcount > 0

    def search(self, query: str, category: str | None = None, limit: int = 10) -> list[dict]:
        """Search memories by value content."""
        sql = "SELECT key, value, category, importance FROM memories WHERE value LIKE ?"
        params = [f"%{query}%"]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY importance DESC, access_count DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def search_lexical(self, query: str, limit: int = 10) -> list[dict]:
        """Token-overlap scored search via the Headroom selector (Claude Mem).

        Stronger than the LIKE substring match: ranks by shared vocabulary so
        a query can hit memories that don't contain the exact phrase.
        """
        if not query:
            return []
        from core.context.selector import score as _score
        with self._lock:
            rows = [dict(r) for r in self._conn.execute(
                "SELECT key, value, category, importance FROM memories "
                "ORDER BY updated_at DESC LIMIT 500",
            ).fetchall()]
        # Split snake_case keys so "favorite_language" matches "favorite language".
        scored = [
            (_score(f"{r['key'].replace('_', ' ')} {r['value']}", query), r)
            for r in rows
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [r for s, r in scored if s > 0.0][:limit]

    def log_conversation(self, session_id: str, role: str, content: str,
                         intent: str = "", tokens_used: int = 0):
        """Log a conversation turn — buffered and flushed periodically."""
        if self._closed:
            return
        with self._conv_flush_lock:
            self._conv_buffer.append((session_id, role, content, intent, time.time(), tokens_used))
            if self._conv_timer and self._conv_timer.is_alive():
                return
            self._conv_timer = threading.Timer(self._CONV_FLUSH_INTERVAL, self._flush_conversations)
            self._conv_timer.daemon = True
            self._conv_timer.start()

    def _flush_conversations(self, force: bool = False):
        """Flush buffered conversation logs to SQLite.

        Args:
            force: If True, bypasses the _closed check (used by shutdown).
        """
        with self._conv_flush_lock:
            buffer = self._conv_buffer[:]
            self._conv_buffer.clear()
        if not buffer:
            return
        if not force and self._closed:
            return
        if self._conn is None:
            return
        with self._lock:
            self._conn.executemany("""
                INSERT INTO conversations (session_id, role, content, intent, timestamp, tokens_used)
                VALUES (?, ?, ?, ?, ?, ?)
            """, buffer)
            self._conn.commit()

    def flush_conversations(self):
        """Force immediate flush (called on shutdown)."""
        self._flush_conversations()

    def recent(self, limit: int = 10, category: str | None = None) -> list[dict]:
        """Most recently updated memories — used for prompt injection.

        Args:
            limit: Max entries to return.
            category: If set, filter to this category (e.g., 'identity', 'preferences').
        """
        with self._lock:
            if category:
                rows = [dict(r) for r in self._conn.execute(
                    "SELECT key, value, category, importance FROM memories "
                    "WHERE category = ? ORDER BY updated_at DESC LIMIT ?",
                    (category, limit),
                ).fetchall()]
            else:
                rows = [dict(r) for r in self._conn.execute(
                    "SELECT key, value, category, importance FROM memories "
                    "ORDER BY updated_at DESC LIMIT ?", (limit,),
                ).fetchall()]
        return rows

    def get_conversation_history(self, session_id: str, limit: int = 50) -> list[dict]:
        """Get conversation history for a session."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content, intent, timestamp FROM conversations "
                "WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_stats(self) -> dict:
        """Get memory store statistics."""
        with self._lock:
            mem_count = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            conv_count = self._conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        return {"memories": mem_count, "conversations": conv_count}

    def close(self):
        """Flush pending writes, cancel the flush timer, and close the DB."""
        if self._closed:
            return
        self.shutdown()

    def shutdown(self):
        """Cancel the conversation timer, flush the buffer, close the connection.

        Sets _closed BEFORE flushing to prevent new writes from being added
        to the buffer after the flush runs but before _closed is set.
        """
        self._closed = True  # Block new writes first
        with self._conv_flush_lock:
            timer = self._conv_timer
            self._conv_timer = None
        if timer is not None:
            timer.cancel()
        self._flush_conversations(force=True)  # force=True bypasses _closed check
        if self._conn:
            self._conn.close()
            self._conn = None
