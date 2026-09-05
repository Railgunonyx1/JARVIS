"""Memory Store - JSON + SQLite persistent memory for JARVIS MK-X."""

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("jarvis.memory")

# G12 BLOB mode cap: artifacts are bounded so they never bloat the store.
BLOB_MAX_BYTES = 16 * 1024 * 1024  # 16 MiB

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

        # Integrity check — if corrupt, backup and rebuild
        try:
            result = self._conn.execute("PRAGMA integrity_check").fetchone()
            if result and result[0] != "ok":
                logger.error("SQLite integrity check failed: %s — rebuilding", result[0])
                self._rebuild_from_json()
        except Exception as e:
            logger.warning("Integrity check skipped: %s", e)

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
        # FTS5 virtual table for fast BM25 full-text search
        # Standalone table (not content-synced) — rebuilt on store/delete
        try:
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    key, value, category,
                    tokenize='porter unicode61'
                )
            """)
            self._fts_available = True
        except Exception as e:
            logger.debug("FTS5 not available: %s", e)
            self._fts_available = False
        self._ensure_ownership_schema()
        self._conn.commit()

    def _ensure_ownership_schema(self) -> None:
        """Idempotent migration: owner column + BLOB table (G12 selective memory).

        Existing databases predate ownership; ``ALTER TABLE ... ADD COLUMN``
        with a NOT NULL DEFAULT is safe and idempotent across runs.
        """
        try:
            self._conn.execute(
                "ALTER TABLE memories ADD COLUMN owner TEXT NOT NULL DEFAULT 'user'"
            )
        except sqlite3.OperationalError:
            pass  # column already present
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_blobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                owner TEXT NOT NULL DEFAULT 'user',
                mime TEXT NOT NULL DEFAULT 'application/octet-stream',
                size INTEGER NOT NULL,
                data BLOB NOT NULL,
                category TEXT DEFAULT 'artifact',
                meta TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memories_owner ON memories(owner);
            CREATE INDEX IF NOT EXISTS idx_blobs_owner ON memory_blobs(owner);
        """)

    def _rebuild_from_json(self) -> None:
        """Rebuild the SQLite memories table from long_term.json.

        Called when integrity_check fails. Creates a fresh DB and
        re-imports from the JSON source of truth.
        """
        try:
            # Backup corrupt DB
            backup_path = self._db_path.with_suffix(".db.corrupt")
            if backup_path.exists():
                backup_path.unlink()
            self._db_path.rename(backup_path)
            logger.info("Backed up corrupt DB to %s", backup_path)
        except OSError:
            pass
        # Re-init with fresh DB
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
        self._ensure_ownership_schema()
        self._conn.commit()
        # Rebuild from JSON
        try:
            from core.utils import get_project_root
            json_path = get_project_root() / "memory" / "long_term.json"
            if not json_path.exists():
                return
            import json as _json
            data = _json.loads(json_path.read_text(encoding="utf-8"))
            count = 0
            for category, items in data.items():
                if not isinstance(items, dict):
                    continue
                for key, entry in items.items():
                    val = entry.get("value") if isinstance(entry, dict) else entry
                    if val and isinstance(val, str):
                        self.store(key, val, category=category, importance=0.9)
                        count += 1
            logger.info("Rebuilt %d memories from long_term.json", count)
        except Exception as e:
            logger.error("Failed to rebuild from JSON: %s", e)

    def _upsert(self, key: str, value: str, category: str, importance: float,
                owner: str = "user") -> None:
        """Insert or update one memory row with its owner."""
        now = time.time()
        with self._lock:
            self._conn.execute("""
                INSERT INTO memories (key, value, category, created_at, updated_at,
                                     importance, owner)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at,
                    importance = excluded.importance
            """, (key, value, category, now, now, importance, owner))
            # Sync FTS5 index
            if getattr(self, '_fts_available', False):
                try:
                    # Delete old FTS entry if exists, then insert new
                    self._conn.execute(
                        "DELETE FROM memories_fts WHERE key = ?", (key,)
                    )
                    self._conn.execute(
                        "INSERT INTO memories_fts(key, value, category) VALUES (?, ?, ?)",
                        (key, value, category),
                    )
                except Exception:
                    pass  # FTS sync is best-effort
            self._conn.commit()
        logger.info("Memory stored: %s [%s]", key, category)

    def store(self, key: str, value: str, category: str = "general", importance: float = 0.5):
        """Store a key-value memory (legacy surface; rows are user-owned)."""
        self._upsert(key, value, category, importance, owner="user")

    def store_owned(self, key: str, value: str, owner: str,
                    category: str = "general", importance: float = 0.5) -> None:
        """Ownership-enforced store under the constellation keyspace (G12).

        Raises ``ValueError`` for malformed keys and ``PermissionError`` when
        ``owner`` may not write the key's namespace.
        """
        from memory.keyspace import can_write, parse_key

        parse_key(key)  # ValueError on malformed keyspace key
        if not can_write(key, owner):
            raise PermissionError(f"{owner!r} may not write memory key {key!r}")
        self._upsert(key, value, category, importance, owner=owner)

    def recall(self, key: str, owner: str | None = None) -> str | None:
        """Recall a memory by key; ``owner`` scopes reads (None = admin)."""
        from memory.keyspace import can_read

        with self._lock:
            row = self._conn.execute(
                "SELECT key, value, owner FROM memories WHERE key = ?", (key,)
            ).fetchone()
            if row and (owner is None or can_read(row["key"], owner)):
                self._conn.execute(
                    "UPDATE memories SET access_count = access_count + 1 WHERE key = ?",
                    (key,)
                )
                self._conn.commit()
                return row["value"]
        return None

    def delete_owned(self, key: str, owner: str) -> bool:
        """Delete a memory only when ``owner`` may write its key."""
        from memory.keyspace import can_write, parse_key

        parse_key(key)
        if not can_write(key, owner):
            raise PermissionError(f"{owner!r} may not delete memory key {key!r}")
        return self.delete(key)

    def delete(self, key: str) -> bool:
        """Delete a memory by key."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memories WHERE key = ?", (key,)
            )
            # Sync FTS5 index
            if getattr(self, '_fts_available', False):
                try:
                    self._conn.execute(
                        "DELETE FROM memories_fts WHERE key = ?", (key,)
                    )
                except Exception:
                    pass  # FTS sync is best-effort
            self._conn.commit()
        return cur.rowcount > 0

    # ── G12: BLOB mode (binary / large artifacts) ────────────────────────────

    def put_blob(self, key: str, data: bytes, owner: str = "user",
                 mime: str = "application/octet-stream",
                 category: str = "artifact", meta: str = "") -> int:
        """Store a binary artifact under the keyspace; returns its size.

        Ownership rules mirror text memories. Blobs never appear in text
        recall/search — they are retrieved by key reference only.
        """
        from memory.keyspace import can_write, parse_key

        parse_key(key)
        if not can_write(key, owner):
            raise PermissionError(f"{owner!r} may not write blob key {key!r}")
        if data is None or not isinstance(data, (bytes, bytearray)):
            raise ValueError("blob data must be bytes")
        size = len(data)
        if size > BLOB_MAX_BYTES:
            raise ValueError(
                f"blob {size} bytes exceeds cap of {BLOB_MAX_BYTES} bytes"
            )
        now = time.time()
        with self._lock:
            self._conn.execute("""
                INSERT INTO memory_blobs (key, owner, mime, size, data, category,
                                         meta, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    owner = excluded.owner,
                    mime = excluded.mime,
                    size = excluded.size,
                    data = excluded.data,
                    category = excluded.category,
                    meta = excluded.meta,
                    created_at = excluded.created_at
            """, (key, owner, mime, size, bytes(data), category, meta, now))
            self._conn.commit()
        return size

    def get_blob(self, key: str, owner: str | None = None) -> dict | None:
        """Return ``{key, data, mime, size, category, meta, created_at}``."""
        from memory.keyspace import can_read, parse_key

        with self._lock:
            row = self._conn.execute(
                "SELECT key, owner, mime, size, data, category, meta, created_at "
                "FROM memory_blobs WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        if owner is not None and not can_read(row["key"], owner):
            return None
        return dict(row)

    def blob_info(self, key: str, owner: str | None = None) -> dict | None:
        """Metadata for a blob, never its payload."""
        blob = self.get_blob(key, owner=owner)
        if blob is None:
            return None
        blob.pop("data", None)
        return blob

    def list_blobs(self, owner: str | None = None, limit: int = 50) -> list[dict]:
        """Metadata rows for stored blobs, newest first (never payloads)."""
        from memory.keyspace import can_read

        with self._lock:
            rows = [dict(r) for r in self._conn.execute(
                "SELECT key, owner, mime, size, category, meta, created_at "
                "FROM memory_blobs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            )]
        if owner is not None:
            rows = [r for r in rows if can_read(r["key"], owner)]
        return rows

    def search(self, query: str, category: str | None = None, limit: int = 10,
               owner: str | None = None) -> list[dict]:
        """Search memories by value content; ``owner`` scopes the results."""
        from memory.keyspace import can_read

        sql = "SELECT key, value, category, importance FROM memories WHERE value LIKE ?"
        params = [f"%{query}%"]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY importance DESC, access_count DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        rows = [dict(r) for r in rows]
        if owner is not None:
            rows = [r for r in rows if can_read(r["key"], owner)]
        return rows

    def search_lexical(self, query: str, limit: int = 10) -> list[dict]:
        """Token-overlap scored search via FTS5 (fast) or selector (fallback).

        Uses FTS5 BM25 ranking when available (much faster than loading
        500 rows into Python). Falls back to the Headroom selector for
        scoring when FTS5 is unavailable.
        """
        if not query:
            return []

        # Fast path: FTS5 BM25 search
        if getattr(self, '_fts_available', False):
            try:
                # FTS5 query syntax: wrap in quotes for phrase, or use AND/OR
                fts_query = query.replace('"', '""')
                with self._lock:
                    rows = [dict(r) for r in self._conn.execute(
                        "SELECT m.key, m.value, m.category, m.importance, "
                        "rank AS bm25_score "
                        "FROM memories_fts fts "
                        "JOIN memories m ON m.id = fts.rowid "
                        "WHERE memories_fts MATCH ? "
                        "ORDER BY rank "
                        "LIMIT ?",
                        (fts_query, limit * 3),
                    ).fetchall()]
                if rows:
                    return rows[:limit]
            except Exception as e:
                logger.debug("FTS5 search failed, falling back: %s", e)

        # Fallback: load-and-score (slow but reliable)
        from core.context.selector import score as _score
        with self._lock:
            rows = [dict(r) for r in self._conn.execute(
                "SELECT key, value, category, importance FROM memories "
                "ORDER BY updated_at DESC LIMIT 500",
            ).fetchall()]
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
