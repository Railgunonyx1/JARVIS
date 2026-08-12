"""Token Prediction Cache — Predict likely response prefixes.

Many responses begin similarly:
"Sure,", "Certainly,", "The issue is,", "Based on your project,"

Cache these common prefixes for instant display.
"""
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("ai_runtime.token_prediction")


@dataclass
class PrefixEntry:
    """A cached prefix pattern."""
    prefix: str
    count: int = 0
    avg_continuation_ms: float = 0.0
    last_used: float = 0.0
    continuations: dict[str, int] = None

    def __post_init__(self):
        if self.continuations is None:
            self.continuations = {}


class TokenPredictionCache:
    """Cache common response prefixes for instant display.

    When the LLM starts generating, check if the first few tokens
    match a cached prefix. If so, display the cached prefix immediately
    while waiting for the actual tokens.
    """

    def __init__(self, max_prefixes: int = 1000, min_occurrences: int = 2):
        self._prefixes: dict[str, PrefixEntry] = {}
        self._max_prefixes = max_prefixes
        self._min_occurrences = min_occurrences
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def record_response(self, prefix: str, full_response: str) -> None:
        """Record a response for prefix learning."""
        prefix = prefix.strip()[:50]
        if not prefix:
            return

        with self._lock:
            if prefix not in self._prefixes:
                if len(self._prefixes) >= self._max_prefixes:
                    self._evict()
                self._prefixes[prefix] = PrefixEntry(prefix=prefix)

            entry = self._prefixes[prefix]
            entry.count += 1
            entry.last_used = time.time()

            # Track what comes after this prefix
            continuation = full_response[len(prefix):len(prefix) + 20].strip()
            if continuation:
                entry.continuations[continuation] = entry.continuations.get(continuation, 0) + 1

    def predict_prefix(self, partial_tokens: str) -> tuple[str, float] | None:
        """Given the first few tokens, predict the likely full prefix.

        Returns (predicted_prefix, confidence) or None.
        """
        partial = partial_tokens.strip()[:50]

        with self._lock:
            # Exact match
            if partial in self._prefixes:
                entry = self._prefixes[partial]
                if entry.count >= self._min_occurrences:
                    self._hits += 1
                    best_continuation = max(entry.continuations, key=entry.continuations.get) if entry.continuations else ""
                    confidence = min(entry.count / 100, 0.95)
                    return (partial + best_continuation, confidence)

            # Prefix match
            for cached_prefix, entry in self._prefixes.items():
                if cached_prefix.startswith(partial) and len(cached_prefix) > len(partial):
                    if entry.count >= self._min_occurrences:
                        self._hits += 1
                        confidence = min(entry.count / 100, 0.9)
                        return (cached_prefix, confidence)

        self._misses += 1
        return None

    def _evict(self) -> None:
        """Remove least-used entries."""
        sorted_entries = sorted(self._prefixes.values(), key=lambda e: e.count)
        for entry in sorted_entries[:len(sorted_entries) // 4]:
            self._prefixes.pop(entry.prefix, None)

    def get_common_prefixes(self, top_n: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            sorted_entries = sorted(self._prefixes.values(), key=lambda e: e.count, reverse=True)
            return [
                {"prefix": e.prefix, "count": e.count, "last_used": e.last_used}
                for e in sorted_entries[:top_n]
            ]

    def get_stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "cached_prefixes": len(self._prefixes),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(total, 1) * 100, 1),
        }


_prediction_cache_instance: TokenPredictionCache | None = None


def get_token_prediction_cache() -> TokenPredictionCache:
    global _prediction_cache_instance
    if _prediction_cache_instance is None:
        _prediction_cache_instance = TokenPredictionCache()
    return _prediction_cache_instance
