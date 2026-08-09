"""Cache Layer — tiered LRU + TTL cache.

L1: Memory (fastest, bounded)
L2: SQLite (persistent, slower)
L3: Provider/LLM (slowest, auto-populated on miss)

Every roundtrip to the provider goes through this cache.
"""
import json
import time
import sqlite3
import hashlib
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("jarvis.cache")

_DEFAULT_MAX_MEMORY_ITEMS = 500
_DEFAULT_TTL_S = 300


class SemanticCache:
    """GPTCache-style semantic response cache.

    Keys on query *meaning* (MiniLM embedding + cosine similarity) instead of
    an exact string, so paraphrases of a repeated question hit the cache and
    skip the LLM roundtrip. In-memory, bounded, TTL'd.

    Embedding is lazy (only computed when there is something to compare
    against), and disabled-by-default via the JARVIS_SEMANTIC_CACHE env var
    (set to "1" to enable) so it is a safe opt-in hook.
    """

    def __init__(self, max_items: int = 256, threshold: float = 0.72,
                 ttl: int = 300, enabled: bool | None = None):
        import os
        if enabled is None:
            enabled = os.environ.get("JARVIS_SEMANTIC_CACHE", "0") == "1"
        self.enabled = enabled
        self._max_items = max_items
        self._threshold = threshold
        self._ttl = ttl
        self._entries: "OrderedDict[str, tuple]" = OrderedDict()  # query -> (embedding, value, created)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _embed(self, text: str):
        from memory.vector_store import _text_to_vector
        return _text_to_vector(text)

    def get(self, query: str) -> Optional[Any]:
        """Return cached value if query is semantically near a stored query."""
        if not self.enabled or not query.strip():
            return None
        q = query.strip().lower()
        with self._lock:
            if not self._entries:
                self._misses += 1
                return None
        q_vec = self._embed(q)
        now = time.time()
        best_sim = 0.0
        best_value = None
        with self._lock:
            for stored_q, (vec, value, created) in self._entries.items():
                if now - created > self._ttl:
                    continue
                sim = _cosine_sim(q_vec, vec)
                if sim > best_sim:
                    best_sim = sim
                    best_value = value
        if best_value is not None and best_sim >= self._threshold:
            self._hits += 1
            return best_value
        self._misses += 1
        return None

    def set(self, query: str, value: Any):
        if not self.enabled or not query.strip():
            return
        q = query.strip().lower()
        vec = self._embed(q)
        with self._lock:
            self._entries[q] = (vec, value, time.time())
            self._entries.move_to_end(q)
            while len(self._entries) > self._max_items:
                self._entries.popitem(last=False)

    def clear(self):
        with self._lock:
            self._entries.clear()

    def get_stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "enabled": self.enabled,
            "entries": len(self._entries),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round((self._hits / total * 100) if total else 0.0, 1),
            "threshold": self._threshold,
        }


def _cosine_sim(a, b):
    try:
        import numpy as np
        a = np.asarray(a, dtype=np.float32)
        b = np.asarray(b, dtype=np.float32)
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-9
        return float(np.dot(a, b) / denom)
    except Exception:
        return 0.0


@dataclass
class CacheEntry:
    key: str
    value: Any
    ttl: float  # expiration timestamp
    created: float = 0.0
    hit_count: int = 0

    def __post_init__(self):
        if self.created == 0.0:
            self.created = time.time()

    @property
    def expired(self) -> bool:
        return time.time() > self.ttl


class Cache:
    """Tiered LRU cache with TTL and optional SQLite persistence."""

    def __init__(self, name: str = "default",
                 max_memory_items: int = _DEFAULT_MAX_MEMORY_ITEMS,
                 default_ttl: int = _DEFAULT_TTL_S,
                 db_path: Optional[str] = None):
        self.name = name
        self._max_memory = max_memory_items
        self._default_ttl = default_ttl
        self._memory: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._db_path = db_path
        self._hit_count = 0
        self._miss_count = 0
        if db_path:
            self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self._db_path, timeout=2.0)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    ttl REAL NOT NULL,
                    created REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_ttl ON cache(ttl)
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Cache DB init failed: %s", e)

    # ── Public API ───────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._memory.get(key)
            if entry is not None:
                if entry.expired:
                    del self._memory[key]
                    self._miss_count += 1
                    return None
                entry.hit_count += 1
                self._memory.move_to_end(key)
                self._hit_count += 1
                return entry.value

        # Check SQLite
        if self._db_path:
            val = self._get_sqlite(key)
            if val is not None:
                self._hit_count += 1
                # Promote to memory
                with self._lock:
                    self._memory[key] = CacheEntry(
                        key=key, value=val,
                        ttl=time.time() + self._default_ttl,
                    )
                return val

        self._miss_count += 1
        return None

    def set(self, key: str, value: Any,
            ttl: Optional[int] = None):
        ttl_sec = ttl if ttl is not None else self._default_ttl
        entry = CacheEntry(
            key=key, value=value,
            ttl=time.time() + ttl_sec,
        )
        with self._lock:
            self._memory[key] = entry
            self._memory.move_to_end(key)
            if len(self._memory) > self._max_memory:
                self._memory.popitem(last=False)

        if self._db_path:
            self._set_sqlite(key, value, entry.ttl)

    def get_or_compute(self, key: str, compute_fn: Callable,
                       ttl: Optional[int] = None) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = compute_fn()
        self.set(key, value, ttl=ttl)
        return value

    def invalidate(self, pattern: str):
        with self._lock:
            keys = [k for k in self._memory if k.startswith(pattern)]
            for k in keys:
                del self._memory[k]
        if self._db_path:
            try:
                conn = sqlite3.connect(self._db_path, timeout=2.0)
                conn.execute("DELETE FROM cache WHERE key LIKE ?", (pattern + "%",))
                conn.commit()
                conn.close()
            except Exception:
                pass

    def clear(self):
        with self._lock:
            self._memory.clear()
        if self._db_path:
            try:
                conn = sqlite3.connect(self._db_path, timeout=2.0)
                conn.execute("DELETE FROM cache")
                conn.commit()
                conn.close()
            except Exception:
                pass

    # ── Stats ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        total = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total * 100) if total > 0 else 0.0
        return {
            "name": self.name,
            "memory_items": len(self._memory),
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate_percent": round(hit_rate, 1),
            "max_memory_items": self._max_memory,
            "default_ttl_s": self._default_ttl,
        }

    def shutdown(self):
        self.clear()

    # ── SQLite helpers ───────────────────────────────────────────

    def _get_sqlite(self, key: str) -> Optional[Any]:
        try:
            conn = sqlite3.connect(self._db_path, timeout=2.0)
            row = conn.execute(
                "SELECT value, ttl FROM cache WHERE key = ?", (key,)
            ).fetchone()
            conn.close()
            if row:
                if time.time() > row[1]:
                    self._del_sqlite(key)
                    return None
                return json.loads(row[0])
        except Exception:
            pass
        return None

    def _set_sqlite(self, key: str, value: Any, ttl: float):
        try:
            conn = sqlite3.connect(self._db_path, timeout=2.0)
            conn.execute(
                "INSERT OR REPLACE INTO cache(key, value, ttl, created) "
                "VALUES (?, ?, ?, ?)",
                (key, json.dumps(value), ttl, time.time())
            )
            conn.execute(
                "DELETE FROM cache WHERE ttl < ?",
                (time.time(),)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _del_sqlite(self, key: str):
        try:
            conn = sqlite3.connect(self._db_path, timeout=2.0)
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    @staticmethod
    def make_key(*parts: str) -> str:
        raw = ":".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
