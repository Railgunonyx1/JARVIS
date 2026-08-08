"""Predictive Perception Cache — caches screen analyses and learns transitions."""

import time
import threading
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.perception_engine.predictive_cache")


class PredictivePerceptionCache:
    """Caches screen analyses with TTL and learns screen-state transitions."""

    def __init__(self) -> None:
        self._cache: Dict[str, tuple] = {}
        self._transitions: Dict[str, Dict[str, int]] = {}
        self._lock = threading.Lock()
        self._hits: int = 0
        self._misses: int = 0

    def cache_analysis(self, screen_hash: str, analysis: dict, ttl: int = 30) -> None:
        """Cache an analysis result for *ttl* seconds."""
        expiry = time.monotonic() + ttl
        with self._lock:
            self._cache[screen_hash] = (analysis, expiry)

    def get_cached(self, screen_hash: str) -> Optional[dict]:
        """Retrieve a cached analysis if it has not expired."""
        with self._lock:
            entry = self._cache.get(screen_hash)
            if entry is None:
                self._misses += 1
                return None
            analysis, expiry = entry
            if time.monotonic() > expiry:
                del self._cache[screen_hash]
                self._misses += 1
                return None
            self._hits += 1
            return analysis

    def predict_next_screen(self, current_elements: list) -> list:
        """Predict likely next screen states based on learned transitions.

        Uses the last known screen hash from *current_elements* (if it contains
        a ``"hash"`` key) to look up transition history and returns a sorted
        list of probable next hashes (most frequent first).
        """
        if not current_elements:
            return []

        screen_hash: Optional[str] = None
        for elem in current_elements:
            if isinstance(elem, dict) and "hash" in elem:
                screen_hash = elem["hash"]
                break
        if screen_hash is None and isinstance(current_elements, list):
            if current_elements and isinstance(current_elements[0], str):
                screen_hash = current_elements[0]

        if screen_hash is None:
            return []

        with self._lock:
            transitions = self._transitions.get(screen_hash, {})
            if not transitions:
                return []
            ranked = sorted(transitions.items(), key=lambda kv: kv[1], reverse=True)
            return [h for h, _ in ranked]

    def record_transition(self, from_hash: str, to_hash: str) -> None:
        """Record that the screen transitioned from *from_hash* to *to_hash*."""
        with self._lock:
            if from_hash not in self._transitions:
                self._transitions[from_hash] = {}
            bucket = self._transitions[from_hash]
            bucket[to_hash] = bucket.get(to_hash, 0) + 1

    def get_transition_probability(self, from_hash: str, to_hash: str) -> float:
        """Return the probability of transitioning from one hash to another."""
        with self._lock:
            bucket = self._transitions.get(from_hash, {})
            if not bucket:
                return 0.0
            total = sum(bucket.values())
            if total == 0:
                return 0.0
            return bucket.get(to_hash, 0) / total

    def cleanup_expired(self) -> int:
        """Remove all expired cache entries. Returns count removed."""
        now = time.monotonic()
        removed = 0
        with self._lock:
            expired = [k for k, (_, exp) in self._cache.items() if now > exp]
            for k in expired:
                del self._cache[k]
                removed += 1
        return removed

    def clear(self) -> None:
        """Clear all cached analyses and transition data."""
        with self._lock:
            self._cache.clear()
            self._transitions.clear()

    def clear_transitions(self) -> None:
        """Clear only transition learning data."""
        with self._lock:
            self._transitions.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Return cache and transition statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "cache_size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
                "transitions_learned": sum(
                    len(v) for v in self._transitions.values()
                ),
                "transition_sources": len(self._transitions),
            }


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: Optional[PredictivePerceptionCache] = None
_instance_lock = threading.Lock()


def get_perception_cache() -> PredictivePerceptionCache:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PredictivePerceptionCache()
    return _instance
