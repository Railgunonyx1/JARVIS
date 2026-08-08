"""Prefix KV Cache — Reuse attention keys for unchanged conversation history.

If conversation history hasn't changed, don't recompute attention.
Cache the key-value pairs and continue generation from the cache point.
"""
import logging
import time
import threading
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("ai_runtime.prefix_kv_cache")


@dataclass
class KVEntry:
    """Cached key-value pair entry."""
    prefix_hash: str
    kv_data: Any = None  # In real implementation: torch tensor pairs
    token_count: int = 0
    created_at: float = 0.0
    access_count: int = 0
    size_bytes: int = 0


class PrefixKVCache:
    """Cache attention key-value pairs for conversation prefixes.

    When the same conversation prefix is used repeatedly:
    1. Compute hash of the prefix tokens
    2. Check if KV pairs exist for that hash
    3. If yes, load cached KV and continue from there
    4. If no, compute and cache

    This eliminates redundant attention computation for common prefixes
    (system prompt + recent conversation).
    """

    def __init__(self, max_entries: int = 50, max_bytes: int = 500 * 1024 * 1024):
        self._cache: Dict[str, KVEntry] = {}
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._current_bytes = 0
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._total_reuse_ms = 0.0

    @staticmethod
    def hash_prefix(tokens: List[str]) -> str:
        """Hash a list of tokens to create a cache key."""
        combined = "|".join(tokens)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def get(self, tokens: List[str]) -> Optional[Any]:
        """Get cached KV pairs for a token prefix."""
        key = self.hash_prefix(tokens)

        with self._lock:
            entry = self._cache.get(key)
            if entry:
                entry.access_count += 1
                self._hits += 1
                self._total_reuse_ms += entry.token_count * 0.5  # Estimated savings
                return entry.kv_data

        self._misses += 1
        return None

    def put(self, tokens: List[str], kv_data: Any, size_bytes: int = 0) -> None:
        """Cache KV pairs for a token prefix."""
        key = self.hash_prefix(tokens)

        entry = KVEntry(
            prefix_hash=key,
            kv_data=kv_data,
            token_count=len(tokens),
            created_at=time.time(),
            size_bytes=size_bytes or len(tokens) * 128,  # Estimate
        )

        with self._lock:
            self._cache[key] = entry
            self._current_bytes += entry.size_bytes
            self._evict()

    def find_longest_match(self, tokens: List[str]) -> Tuple[int, Any]:
        """Find the longest cached prefix match.

        Returns (match_length, kv_data) or (0, None).
        """
        best_length = 0
        best_kv = None

        for length in range(len(tokens), 0, -1):
            key = self.hash_prefix(tokens[:length])
            with self._lock:
                entry = self._cache.get(key)
                if entry and length > best_length:
                    best_length = length
                    best_kv = entry.kv_data
                    entry.access_count += 1

        if best_length > 0:
            self._hits += 1
            self._total_reuse_ms += best_length * 0.5
        else:
            self._misses += 1

        return (best_length, best_kv)

    def _evict(self) -> None:
        while len(self._cache) > self._max_entries or self._current_bytes > self._max_bytes:
            if not self._cache:
                break
            # Remove least recently used
            oldest_key = min(self._cache, key=lambda k: self._cache[k].created_at)
            entry = self._cache.pop(oldest_key)
            self._current_bytes -= entry.size_bytes

    def invalidate(self, tokens: List[str] = None) -> None:
        """Invalidate cache entries. If tokens provided, invalidate only that entry."""
        with self._lock:
            if tokens:
                key = self.hash_prefix(tokens)
                entry = self._cache.pop(key, None)
                if entry:
                    self._current_bytes -= entry.size_bytes
            else:
                self._cache.clear()
                self._current_bytes = 0

    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "cached_entries": len(self._cache),
            "current_bytes": self._current_bytes,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(total, 1) * 100, 1),
            "total_reuse_ms_saved": round(self._total_reuse_ms, 1),
        }


_kv_cache_instance: Optional[PrefixKVCache] = None


def get_prefix_kv_cache() -> PrefixKVCache:
    global _kv_cache_instance
    if _kv_cache_instance is None:
        _kv_cache_instance = PrefixKVCache()
    return _kv_cache_instance
