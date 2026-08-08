"""Semantic Cache — LRU cache with TTL support and glob-based invalidation."""

import time
import threading
import logging
import fnmatch
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.performance_engine.cache")

_MAX_ENTRIES = 1000


class SemanticCache:
    """Thread-safe LRU cache with per-entry TTL expiry and glob invalidation."""

    def __init__(self, max_entries: int = _MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._access_order: List[str] = []
        self._lock = threading.Lock()
        self._hits: int = 0
        self._misses: int = 0

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """Return cached value if present and not expired, else None."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expiry = entry
            if expiry is not None and time.monotonic() > expiry:
                self._remove_key(key)
                self._misses += 1
                return None
            self._hits += 1
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            return value

    def put(self, key: str, value: Any, ttl_seconds: float = 300.0) -> None:
        """Insert or update a cache entry with a TTL in seconds."""
        expiry = time.monotonic() + ttl_seconds if ttl_seconds > 0 else None
        with self._lock:
            if key in self._cache:
                self._cache[key] = (value, expiry)
                if key in self._access_order:
                    self._access_order.remove(key)
                self._access_order.append(key)
                return
            while len(self._cache) >= self._max_entries and self._access_order:
                self._evict_lru()
            self._cache[key] = (value, expiry)
            self._access_order.append(key)

    def invalidate(self, key: str) -> bool:
        """Remove a single key. Returns True if the key existed."""
        with self._lock:
            if key in self._cache:
                self._remove_key(key)
                return True
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """Remove all keys matching a glob *pattern*. Returns count removed."""
        with self._lock:
            keys_to_remove = [k for k in self._cache if fnmatch.fnmatch(k, pattern)]
            for k in keys_to_remove:
                self._remove_key(k)
            return len(keys_to_remove)

    # ------------------------------------------------------------------
    # Warm-up
    # ------------------------------------------------------------------

    def warm_cache(self, items: Dict[str, Any], ttl_seconds: float = 300.0) -> None:
        """Pre-populate the cache with *items*."""
        for key, value in items.items():
            self.put(key, value, ttl_seconds=ttl_seconds)
        logger.info("Cache warmed with %d entries", len(items))

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            size = len(self._cache)
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": size,
                "max_size": self._max_entries,
                "hit_rate": round(hit_rate, 4),
            }

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()

    # ------------------------------------------------------------------
    # Internal helpers (caller must hold _lock)
    # ------------------------------------------------------------------

    def _evict_lru(self) -> None:
        if self._access_order:
            oldest = self._access_order.pop(0)
            self._cache.pop(oldest, None)

    def _remove_key(self, key: str) -> None:
        self._cache.pop(key, None)
        if key in self._access_order:
            self._access_order.remove(key)


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_cache: Optional[SemanticCache] = None
_cache_lock = threading.Lock()


def get_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = SemanticCache()
    return _cache
