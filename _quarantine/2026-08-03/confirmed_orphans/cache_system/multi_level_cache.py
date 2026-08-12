"""Multi-Level Cache — L1 RAM → L2 Disk → L3 SQLite → Internet.

Each level is slower but larger. Lookup cascades from fastest to slowest.
"""
import json
import logging
import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("cache_system.multi_level")


@dataclass
class CacheEntry:
    key: str
    value: Any
    level: int  # 0=L1, 1=L2, 2=L3
    created_at: float
    ttl_seconds: float
    access_count: int = 0
    size_bytes: int = 0

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return (time.time() - self.created_at) > self.ttl_seconds


class L1RAMCache:
    """Fast in-memory LRU cache."""

    def __init__(self, max_size: int = 500, max_bytes: int = 10 * 1024 * 1024):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._max_bytes = max_bytes
        self._current_bytes = 0
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.is_expired:
                self._remove(key)
                self._misses += 1
                return None
            self._cache.move_to_end(key)
            entry.access_count += 1
            self._hits += 1
            return entry.value

    def put(self, key: str, value: Any, ttl_seconds: float = 300) -> None:
        with self._lock:
            if key in self._cache:
                self._remove(key)
            entry = CacheEntry(
                key=key, value=value, level=0,
                created_at=time.time(), ttl_seconds=ttl_seconds,
                size_bytes=self._estimate_size(value),
            )
            self._cache[key] = entry
            self._current_bytes += entry.size_bytes
            self._evict()

    def _remove(self, key: str) -> None:
        entry = self._cache.pop(key, None)
        if entry:
            self._current_bytes -= entry.size_bytes

    def _evict(self) -> None:
        while len(self._cache) > self._max_size or self._current_bytes > self._max_bytes:
            if not self._cache:
                break
            key, _ = self._cache.popitem(last=False)
            self._current_bytes -= _.size_bytes

    def _estimate_size(self, value: Any) -> int:
        try:
            return len(json.dumps(value, default=str).encode())
        except Exception:
            return 64

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._current_bytes = 0

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "level": "L1_RAM",
                "size": len(self._cache),
                "max_size": self._max_size,
                "bytes": self._current_bytes,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / max(total, 1) * 100, 1),
            }


class L3SQLiteCache:
    """Persistent SQLite cache for cross-session data."""

    def __init__(self, db_path: str = "cache/l3_cache.db"):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()
        self._hits = 0
        self._misses = 0

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    ttl_seconds REAL NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    size_bytes INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON cache(created_at)")
            conn.commit()
            conn.close()

    def get(self, key: str) -> Any | None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT value, created_at, ttl_seconds, access_count FROM cache WHERE key = ?",
                (key,)
            ).fetchone()
            if row is None:
                conn.close()
                self._misses += 1
                return None

            value_str, created_at, ttl, access_count = row
            if ttl > 0 and (time.time() - created_at) > ttl:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
                conn.close()
                self._misses += 1
                return None

            conn.execute(
                "UPDATE cache SET access_count = ? WHERE key = ?",
                (access_count + 1, key)
            )
            conn.commit()
            conn.close()
            self._hits += 1
            return json.loads(value_str)

    def put(self, key: str, value: Any, ttl_seconds: float = 3600) -> None:
        value_str = json.dumps(value, default=str)
        size_bytes = len(value_str.encode())
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, created_at, ttl_seconds, size_bytes) VALUES (?, ?, ?, ?, ?)",
                (key, value_str, time.time(), ttl_seconds, size_bytes)
            )
            conn.commit()
            conn.close()

    def cleanup(self) -> int:
        """Remove expired entries. Returns count removed."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            now = time.time()
            cursor = conn.execute(
                "DELETE FROM cache WHERE ttl_seconds > 0 AND (created_at + ttl_seconds) < ?",
                (now,)
            )
            count = cursor.rowcount
            conn.commit()
            conn.close()
            return count

    def get_size(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("SELECT COUNT(*) FROM cache").fetchone()
            conn.close()
            return row[0] if row else 0

    def get_stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "level": "L3_SQLite",
            "size": self.get_size(),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(total, 1) * 100, 1),
            "db_path": self._db_path,
        }


class MultiLevelCache:
    """Cascading multi-level cache: L1 RAM → L3 SQLite.

    L2 (SSD/disk) is omitted for simplicity; L1 and L3 cover
    most use cases on this hardware.
    """

    def __init__(self, l1_max: int = 500, db_path: str = "cache/l3_cache.db"):
        self._l1 = L1RAMCache(max_size=l1_max)
        self._l3 = L3SQLiteCache(db_path=db_path)
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        # L1 fast path
        value = self._l1.get(key)
        if value is not None:
            return value

        # L3 persistent path
        value = self._l3.get(key)
        if value is not None:
            # Promote to L1
            self._l1.put(key, value, ttl_seconds=300)
            return value

        return None

    def put(self, key: str, value: Any, ttl_l1: float = 300, ttl_l3: float = 3600) -> None:
        self._l1.put(key, value, ttl_seconds=ttl_l1)
        self._l3.put(key, value, ttl_seconds=ttl_l3)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._l1._remove(key)
            conn = sqlite3.connect(self._l3._db_path)
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
            conn.close()

    def clear(self) -> None:
        self._l1.clear()
        with self._lock:
            conn = sqlite3.connect(self._l3._db_path)
            conn.execute("DELETE FROM cache")
            conn.commit()
            conn.close()

    def get_stats(self) -> dict[str, Any]:
        return {
            "l1": self._l1.get_stats(),
            "l3": self._l3.get_stats(),
        }


_cache_instance: MultiLevelCache | None = None


def get_multi_level_cache() -> MultiLevelCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MultiLevelCache()
    return _cache_instance
