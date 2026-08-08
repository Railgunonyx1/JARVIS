"""Prefetch Engine — background data preloading with dependency-aware scheduling."""

import time
import threading
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("jarvis.orchestration_engine.prefetch_engine")


class PrefetchEngine:
    """Registers data sources, prefetches them in background threads, and caches results."""

    def __init__(self) -> None:
        self._prefetchers: Dict[str, dict] = {}
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._inflight: Dict[str, threading.Event] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_prefetch(
        self,
        name: str,
        prefetch_fn: Callable,
        dependencies: Optional[List[str]] = None,
    ) -> None:
        """Register a prefetchable data source.

        Args:
            name: Unique identifier for this data source.
            prefetch_fn: Callable that fetches and returns the data.
            dependencies: Other prefetch names that must complete first.
        """
        with self._lock:
            self._prefetchers[name] = {
                "fn": prefetch_fn,
                "dependencies": dependencies or [],
            }
        logger.debug("Registered prefetch source '%s'", name)

    def trigger_prefetch(self, context: Optional[dict] = None) -> None:
        """Trigger all registered prefetches in background threads.

        Respects dependency ordering — sources whose dependencies are not yet
        cached are deferred until their deps complete (or skipped on timeout).
        """
        with self._lock:
            registered = dict(self._prefetchers)

        ready = [n for n, p in registered.items() if not p["dependencies"]]
        dispatched: set = set()

        for name in ready:
            self._dispatch(name, context)

        max_rounds = len(registered) + 1
        for _ in range(max_rounds):
            with self._lock:
                remaining = {
                    n: p for n, p in registered.items()
                    if n not in dispatched and n not in self._inflight
                }
            if not remaining:
                break
            for name, p in remaining.items():
                deps_met = all(d in self._cache for d in p["dependencies"])
                if deps_met:
                    self._dispatch(name, context)
                    dispatched.add(name)

        for name in list(self._inflight):
            self._inflight[name].wait(timeout=10.0)

    def get_prefetched(self, name: str) -> Optional[Any]:
        """Return prefetched data for *name* if available, else ``None``."""
        with self._lock:
            return self._cache.get(name)

    def invalidate(self, name: str) -> None:
        """Mark prefetched data for *name* as stale (removes from cache)."""
        with self._lock:
            self._cache.pop(name, None)
            self._timestamps.pop(name, None)
        logger.debug("Invalidated prefetch cache for '%s'", name)

    def get_stats(self) -> Dict[str, dict]:
        """Return per-source ``hit_rate``, ``avg_prefetch_ms``, ``last_prefetch_time``."""
        with self._lock:
            stats: Dict[str, dict] = {}
            for name in self._prefetchers:
                data = self._prefetchers[name]
                timings = data.get("_timings", [])
                hits = data.get("_hits", 0)
                misses = data.get("_misses", 0)
                total = hits + misses
                hit_rate = hits / total if total > 0 else 0.0
                avg_ms = (sum(timings) / len(timings)) if timings else 0.0
                stats[name] = {
                    "hit_rate": round(hit_rate, 4),
                    "avg_prefetch_ms": round(avg_ms, 3),
                    "last_prefetch_time": self._timestamps.get(name),
                    "calls": len(timings),
                }
            return stats

    def preload_common(self) -> None:
        """Preload commonly needed data (memory context, KG context, user profile)."""
        common_sources = {
            "memory_context": self._load_memory_context,
            "kg_context": self._load_kg_context,
            "user_profile": self._load_user_profile,
        }
        for name, fn in common_sources.items():
            if name not in self._prefetchers:
                self.register_prefetch(name, fn)

        logger.info("Preloading common data sources")
        self.trigger_prefetch()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dispatch(self, name: str, context: Optional[dict] = None) -> None:
        event = threading.Event()
        with self._lock:
            self._inflight[name] = event

        def _worker(src_name: str) -> None:
            start = time.perf_counter()
            try:
                prefetcher = self._prefetchers.get(src_name)
                if prefetcher is None:
                    return
                fn = prefetcher["fn"]
                result = fn(context) if context else fn()
                ms = (time.perf_counter() - start) * 1000
                with self._lock:
                    self._cache[src_name] = result
                    self._timestamps[src_name] = time.time()
                    timings = self._prefetchers[src_name].setdefault("_timings", [])
                    timings.append(ms)
                    self._prefetchers[src_name]["_hits"] = \
                        self._prefetchers[src_name].get("_hits", 0) + 1
                logger.debug("Prefetched '%s' in %.1fms", src_name, ms)
            except Exception as exc:
                ms = (time.perf_counter() - start) * 1000
                with self._lock:
                    timings = self._prefetchers.get(src_name, {}).setdefault("_timings", [])
                    timings.append(ms)
                    if src_name in self._prefetchers:
                        self._prefetchers[src_name]["_misses"] = \
                            self._prefetchers[src_name].get("_misses", 0) + 1
                logger.warning("Prefetch '%s' failed after %.1fms: %s", src_name, ms, exc)
            finally:
                event.set()
                with self._lock:
                    self._inflight.pop(src_name, None)

        thread = threading.Thread(target=_worker, args=(name,), daemon=True, name=f"prefetch-{name}")
        thread.start()

    @staticmethod
    def _load_memory_context(context: Optional[dict] = None) -> Any:
        try:
            from memory_engine import get_memory_engine
            engine = get_memory_engine()
            if hasattr(engine, "get_recent"):
                return engine.get_recent(limit=20)
            return {}
        except Exception:
            return {}

    @staticmethod
    def _load_kg_context(context: Optional[dict] = None) -> Any:
        try:
            from knowledge_graph.graph import KnowledgeGraph
            graph = KnowledgeGraph()
            if hasattr(graph, "get_recent_facts"):
                return graph.get_recent_facts(limit=20)
            return {}
        except Exception:
            return {}

    @staticmethod
    def _load_user_profile(context: Optional[dict] = None) -> Any:
        try:
            from personal_intelligence.user_model import UserModel
            model = UserModel()
            if hasattr(model, "get_profile"):
                return model.get_profile()
            return {}
        except Exception:
            return {}


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: Optional[PrefetchEngine] = None
_lock = threading.Lock()


def get_prefetch_engine() -> PrefetchEngine:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = PrefetchEngine()
    return _instance
