"""Tiered Memory Store — hot/warm/cold tiered storage with LRU eviction and automatic promotion."""

import json
import logging
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("jarvis.memory_engine.tiered_store")

_instance: Optional["TieredMemoryStore"] = None
_lock = threading.Lock()


class TieredMemoryStore:
    """Three-tier memory: hot (in-memory LRU), warm (recent SQLite), cold (full SQLite)."""

    def __init__(
        self,
        data_dir: Path | None = None,
        hot_max: int = 100,
        warm_max: int = 1000,
    ):
        self._data_dir = data_dir or Path.home() / ".jarvis" / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "tiered_memory.db"

        self._hot_max = hot_max
        self._warm_max = warm_max

        self._hot: OrderedDict[str, Any] = OrderedDict()
        self._hot_ts: dict[str, float] = {}
        self._lock = threading.Lock()

        self._stats = {
            "promotions": 0,
            "demotions": 0,
            "hits": 0,
            "misses": 0,
        }

        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            timeout=10,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA journal_mode = WAL")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_tier (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'warm',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                access_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_tier ON memory_tier(tier);
            CREATE INDEX IF NOT EXISTS idx_updated ON memory_tier(updated_at);
        """)
        self._conn.commit()

    def store(self, key: str, value: Any, tier: str = "auto") -> None:
        """Store a value. 'auto' picks the tier based on current hot capacity."""
        serialized = json.dumps(value, ensure_ascii=False)
        now = time.time()

        with self._lock:
            if tier == "auto":
                tier = "hot" if len(self._hot) < self._hot_max else "warm"

            if tier == "hot":
                self._hot[key] = value
                self._hot_ts[key] = now
                self._hot.move_to_end(key)
                if len(self._hot) > self._hot_max:
                    self._evict_hot_to_warm()
            else:
                self._put_sql(key, serialized, tier, now)

        logger.debug("Stored key='%s' tier='%s'", key, tier)

    def retrieve(self, key: str) -> Any | None:
        """Search hot -> warm -> cold tiers. Promotes on access."""
        with self._lock:
            if key in self._hot:
                self._hot.move_to_end(key)
                self._hot_ts[key] = time.time()
                self._stats["hits"] += 1
                return self._hot[key]

        row = self._get_sql(key)
        if row is None:
            with self._lock:
                self._stats["misses"] += 1
            return None

        value = json.loads(row["value"])
        tier = row["tier"]

        with self._lock:
            self._stats["hits"] += 1
            if len(self._hot) < self._hot_max:
                self._promote_to_hot(key, value)

        if tier == "cold":
            self._update_sql(key, "warm")

        return value

    def promote(self, key: str) -> None:
        """Move a key from cold/warm to hot tier."""
        with self._lock:
            if key in self._hot:
                return

        row = self._get_sql(key)
        if row is None:
            return

        value = json.loads(row["value"])
        self._promote_to_hot(key, value)
        self._delete_sql(key)

        with self._lock:
            self._stats["promotions"] += 1
            if len(self._hot) > self._hot_max:
                self._evict_hot_to_warm()

        logger.debug("Promoted key='%s' to hot", key)

    def demote(self, key: str) -> None:
        """Move a key from hot to warm tier."""
        with self._lock:
            if key not in self._hot:
                return
            value = self._hot.pop(key)
            self._hot_ts.pop(key, None)

        serialized = json.dumps(value, ensure_ascii=False)
        now = time.time()
        self._put_sql(key, serialized, "warm", now)

        with self._lock:
            self._stats["demotions"] += 1

        logger.debug("Demoted key='%s' to warm", key)

    def delete(self, key: str) -> bool:
        """Delete a key from every tier. Returns True if anything was removed."""
        removed = False
        with self._lock:
            if key in self._hot:
                del self._hot[key]
                self._hot_ts.pop(key, None)
                removed = True
        if removed:
            return True
        try:
            cur = self._conn.execute("DELETE FROM memory_tier WHERE key = ?", (key,))
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            logger.error("SQLite delete failed for key='%s': %s", key, e)
            return False

    def get_stats(self) -> dict:
        """Return tier sizes and operation counts."""
        with self._lock:
            hot_size = len(self._hot)

        warm_size = 0
        cold_size = 0
        try:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM memory_tier WHERE tier='warm'"
            ).fetchone()
            warm_size = row["cnt"] if row else 0

            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM memory_tier WHERE tier='cold'"
            ).fetchone()
            cold_size = row["cnt"] if row else 0
        except Exception:
            pass

        with self._lock:
            stats = dict(self._stats)
        stats["hot_size"] = hot_size
        stats["warm_size"] = warm_size
        stats["cold_size"] = cold_size
        return stats

    def cleanup(self, max_age_hours: int = 72) -> int:
        """Evict hot-tier entries not accessed within max_age_hours."""
        cutoff = time.time() - (max_age_hours * 3600)
        removed = 0

        with self._lock:
            stale = [k for k in list(self._hot) if self._hot_ts.get(k, 0.0) < cutoff]
            for k in stale:
                del self._hot[k]
                self._hot_ts.pop(k, None)
                removed += 1

        if removed > 0:
            logger.info("Cleaned up %d stale entries from hot tier", removed)
        return removed

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _promote_to_hot(self, key: str, value: Any) -> None:
        with self._lock:
            self._hot[key] = value
            self._hot_ts[key] = time.time()
            self._hot.move_to_end(key)

    def _evict_hot_to_warm(self) -> None:
        with self._lock:
            while len(self._hot) > self._hot_max:
                evicted_key, evicted_value = self._hot.popitem(last=False)
                self._hot_ts.pop(evicted_key, None)
                serialized = json.dumps(evicted_value, ensure_ascii=False)
                now = time.time()
                self._put_sql(evicted_key, serialized, "warm", now)

    def _put_sql(self, key: str, value: str, tier: str, now: float) -> None:
        try:
            self._conn.execute(
                """INSERT INTO memory_tier (key, value, tier, created_at, updated_at, access_count)
                   VALUES (?, ?, ?, ?, ?, 0)
                   ON CONFLICT(key) DO UPDATE SET
                     value=excluded.value,
                     tier=excluded.tier,
                     updated_at=excluded.updated_at,
                     access_count=memory_tier.access_count + 1""",
                (key, value, tier, now, now),
            )
            self._conn.commit()
        except Exception as e:
            logger.error("SQLite put failed for key='%s': %s", key, e)

    def _get_sql(self, key: str) -> dict | None:
        try:
            row = self._conn.execute(
                "SELECT * FROM memory_tier WHERE key=?", (key,)
            ).fetchone()
            if row:
                self._conn.execute(
                    "UPDATE memory_tier SET access_count=access_count+1 WHERE key=?",
                    (key,),
                )
                self._conn.commit()
                return dict(row)
        except Exception as e:
            logger.error("SQLite get failed for key='%s': %s", key, e)
        return None

    def _update_sql(self, key: str, tier: str) -> None:
        try:
            self._conn.execute(
                "UPDATE memory_tier SET tier=?, updated_at=? WHERE key=?",
                (tier, time.time(), key),
            )
            self._conn.commit()
        except Exception as e:
            logger.error("SQLite update failed for key='%s': %s", key, e)

    def _delete_sql(self, key: str) -> None:
        try:
            self._conn.execute("DELETE FROM memory_tier WHERE key=?", (key,))
            self._conn.commit()
        except Exception as e:
            logger.error("SQLite delete failed for key='%s': %s", key, e)


def get_tiered_store() -> TieredMemoryStore:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = TieredMemoryStore()
    return _instance
