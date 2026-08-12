"""Hyper-Prefetch Engine: Predictive data prefetching using idle CPU cycles."""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger("jarvis.hyper_opt.prefetch_engine")


class HyperPrefetchEngine:
    """Predictive data prefetching that uses idle CPU cycles."""

    def __init__(self):
        self._sources: dict[str, dict] = {}
        self._cache: dict[str, tuple] = {}
        self._patterns: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="prefetch")
        self._stats = {
            "prefetches": 0,
            "cache_hits": 0,
            "total_saved_ms": 0.0,
        }

    def register_source(
        self,
        name: str,
        fetch_fn: Callable,
        priority: int = 5,
        ttl_seconds: float = 300,
        dependencies: list[str] | None = None,
    ):
        """Register a prefetchable data source."""
        with self._lock:
            self._sources[name] = {
                "fetch_fn": fetch_fn,
                "priority": priority,
                "last_fetch": 0.0,
                "avg_ms": 0.0,
                "fetch_count": 0,
                "ttl_seconds": ttl_seconds,
                "dependencies": dependencies or [],
            }
            logger.debug("Registered prefetch source '%s' (priority=%d, ttl=%.0fs)", name, priority, ttl_seconds)

    def prefetch(self, names: list[str] | None = None):
        """Fetch specified sources (or all high-priority) in background threads."""
        with self._lock:
            if names is None:
                names = [
                    n for n, s in self._sources.items()
                    if s["priority"] >= 5
                ]
            for name in names:
                if name not in self._sources:
                    logger.warning("Unknown prefetch source: %s", name)
                    continue
                self._thread_pool.submit(self._do_prefetch, name)

    def _do_prefetch(self, name: str):
        with self._lock:
            source = self._sources.get(name)
            if source is None:
                return
            cached = self._cache.get(name)
            if cached is not None:
                _, _, ttl = cached
                if time.time() < ttl:
                    return

        start = time.perf_counter()
        try:
            result = source["fetch_fn"]()
            elapsed_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                self._cache[name] = (result, time.time(), time.time() + source["ttl_seconds"])
                old_avg = source["avg_ms"]
                count = source["fetch_count"]
                source["avg_ms"] = (old_avg * count + elapsed_ms) / (count + 1) if count > 0 else elapsed_ms
                source["fetch_count"] = count + 1
                source["last_fetch"] = time.time()
                self._stats["prefetches"] += 1
            logger.debug("Prefetched '%s' in %.1fms", name, elapsed_ms)
        except Exception as exc:
            logger.warning("Prefetch of '%s' failed: %s", name, exc)

    def get(self, name: str) -> Any | None:
        """Get prefetched data. Returns None if not available or expired."""
        with self._lock:
            entry = self._cache.get(name)
            if entry is None:
                return None
            data, timestamp, expiry = entry
            if time.time() >= expiry:
                del self._cache[name]
                return None
            self._stats["cache_hits"] += 1
            return data

    def get_with_fallback(self, name: str) -> Any | None:
        """Get prefetched data; if missing, fetch synchronously as fallback."""
        result = self.get(name)
        if result is not None:
            return result
        with self._lock:
            source = self._sources.get(name)
        if source is None:
            return None
        start = time.perf_counter()
        try:
            result = source["fetch_fn"]()
            elapsed_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                self._cache[name] = (result, time.time(), time.time() + source["ttl_seconds"])
            logger.debug("Fallback fetch of '%s' in %.1fms", name, elapsed_ms)
            return result
        except Exception as exc:
            logger.warning("Fallback fetch of '%s' failed: %s", name, exc)
            return None

    def learn_pattern(self, context_key: str, prefetch_list: list):
        """Learn that certain context triggers certain prefetches."""
        with self._lock:
            if context_key in self._patterns:
                old_list = self._patterns[context_key]["prefetch_list"]
                merged = list(dict.fromkeys(old_list + prefetch_list))
                self._patterns[context_key]["prefetch_list"] = merged
                self._patterns[context_key]["frequency"] += 1
            else:
                self._patterns[context_key] = {
                    "prefetch_list": list(prefetch_list),
                    "frequency": 1,
                }
            logger.debug("Learned pattern for '%s': %s", context_key, prefetch_list)

    def predict_prefetch(self, current_context: str) -> list:
        """Predict which sources to prefetch based on current context."""
        with self._lock:
            pattern = self._patterns.get(current_context)
            if pattern is None:
                return [n for n, s in self._sources.items() if s["priority"] >= 7]
            return list(pattern["prefetch_list"])

    def auto_prefetch(self, current_context: str):
        """Automatically prefetch predicted sources for a given context."""
        predicted = self.predict_prefetch(current_context)
        if predicted:
            logger.info("Auto-prefetching %d sources for context '%s'", len(predicted), current_context)
            self.prefetch(predicted)

    def get_stats(self) -> dict:
        """Returns prefetches, cache_hits, hit_rate, avg_saved_ms."""
        with self._lock:
            total = self._stats["prefetches"] + self._stats["cache_hits"]
            hit_rate = self._stats["cache_hits"] / total if total > 0 else 0.0
            avg_saved = 0.0
            source_count = 0
            total_ms = 0.0
            for source in self._sources.values():
                if source["fetch_count"] > 0:
                    total_ms += source["avg_ms"]
                    source_count += 1
            if source_count > 0:
                avg_saved = total_ms / source_count
            return {
                "prefetches": self._stats["prefetches"],
                "cache_hits": self._stats["cache_hits"],
                "hit_rate": round(hit_rate, 4),
                "avg_saved_ms": round(avg_saved, 2),
                "sources_registered": len(self._sources),
                "patterns_learned": len(self._patterns),
            }

    def preload_common(self):
        """Preload commonly needed data sources (priority >= 5)."""
        with self._lock:
            high_priority = [
                n for n, s in self._sources.items()
                if s["priority"] >= 5
            ]
        if high_priority:
            logger.info("Preloading %d common data sources", len(high_priority))
            self.prefetch(high_priority)

    def shutdown(self):
        self._thread_pool.shutdown(wait=False)
        logger.info("HyperPrefetchEngine shut down")


_instance: HyperPrefetchEngine | None = None
_instance_lock = threading.RLock()


def get_hyper_prefetch_engine() -> HyperPrefetchEngine:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = HyperPrefetchEngine()
            logger.info("Created HyperPrefetchEngine singleton")
        return _instance
