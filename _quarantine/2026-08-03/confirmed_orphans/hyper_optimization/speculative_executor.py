"""Speculative Hyper-Executor: Executes likely next actions before user requests them."""

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("jarvis.hyper_opt.speculative_executor")


class SpeculativeHyperExecutor:
    """Executes likely next actions before user requests them."""

    def __init__(self):
        self._predictions: Dict[str, Dict] = {}
        self._cache: Dict[str, tuple] = {}
        self._thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="spec-hyper")
        self._lock = threading.RLock()
        self._stats = {
            "predictions_made": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "precomputed": 0,
        }

    def predict_and_precompute(self, context: dict, predictions: list):
        """Given context, predict likely actions and precompute results.

        predictions: list of {"key": str, "fn": callable, "args": tuple, "kwargs": dict, "ttl": float}
        """
        with self._lock:
            for pred in predictions:
                key = pred.get("key", "")
                fn = pred.get("fn")
                args = pred.get("args", ())
                kwargs = pred.get("kwargs", {})
                ttl = pred.get("ttl", 300.0)

                if fn is None or not key:
                    continue

                cached = self._cache.get(key)
                if cached is not None:
                    _, expiry = cached
                    if time.time() < expiry:
                        continue

                pred_id = uuid.uuid4().hex[:12]
                self._predictions[pred_id] = {
                    "fn": fn,
                    "args": args,
                    "kwargs": kwargs,
                    "result": None,
                    "status": "pending",
                    "created_at": time.perf_counter(),
                }
                self._stats["predictions_made"] += 1

                future = self._thread_pool.submit(self._run_prediction, pred_id, key, fn, args, kwargs, ttl)
                future.add_done_callback(lambda f, pid=pred_id: self._on_prediction_done(pid, f))

    def _run_prediction(self, pred_id: str, key: str, fn: Callable, args: tuple, kwargs: dict, ttl: float):
        start = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                self._cache[key] = (result, time.time() + ttl)
                if pred_id in self._predictions:
                    self._predictions[pred_id]["result"] = result
                    self._predictions[pred_id]["status"] = "completed"
                self._stats["precomputed"] += 1
            logger.debug("Precomputed '%s' in %.1fms", key, elapsed_ms)
            return result
        except Exception as exc:
            with self._lock:
                if pred_id in self._predictions:
                    self._predictions[pred_id]["status"] = "failed"
            logger.warning("Prediction '%s' failed: %s", key, exc)
            raise

    def _on_prediction_done(self, pred_id: str, future: Future):
        with self._lock:
            if pred_id in self._predictions:
                if future.exception() is not None:
                    self._predictions[pred_id]["status"] = "failed"

    def get_cached(self, key: str) -> Optional[Any]:
        """Get precomputed result if available and not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["cache_misses"] += 1
                return None
            value, expiry = entry
            if time.time() >= expiry:
                del self._cache[key]
                self._stats["cache_misses"] += 1
                return None
            self._stats["cache_hits"] += 1
            return value

    def execute_speculative(self, primary_fn: Callable, fallback_fn: Callable, timeout_ms: float = 500):
        """Run primary function; if it times out, fall back to speculative result from fallback_fn."""
        result_holder = [None]
        exception_holder = [None]

        def _run_primary():
            try:
                result_holder[0] = primary_fn()
            except Exception as exc:
                exception_holder[0] = exc

        primary_thread = threading.Thread(target=_run_primary, daemon=True)
        primary_thread.start()
        primary_thread.join(timeout=timeout_ms / 1000.0)

        if primary_thread.is_alive():
            logger.warning("Primary function timed out after %.0fms, using speculative fallback", timeout_ms)
            try:
                return fallback_fn()
            except Exception as exc:
                logger.error("Fallback also failed: %s", exc)
                raise
        if exception_holder[0] is not None:
            raise exception_holder[0]
        return result_holder[0]

    def get_stats(self) -> dict:
        """Returns predictions_made, cache_hits, cache_misses, hit_rate."""
        with self._lock:
            total = self._stats["cache_hits"] + self._stats["cache_misses"]
            hit_rate = self._stats["cache_hits"] / total if total > 0 else 0.0
            return {
                "predictions_made": self._stats["predictions_made"],
                "cache_hits": self._stats["cache_hits"],
                "cache_misses": self._stats["cache_misses"],
                "hit_rate": round(hit_rate, 4),
                "precomputed": self._stats["precomputed"],
                "active_predictions": sum(
                    1 for p in self._predictions.values() if p["status"] == "pending"
                ),
            }

    def invalidate(self, pattern: Optional[str] = None):
        """Invalidate cached predictions. pattern=None clears all."""
        with self._lock:
            if pattern is None:
                cleared = len(self._cache)
                self._cache.clear()
                logger.info("Invalidated all %d cached predictions", cleared)
            else:
                keys_to_remove = [k for k in self._cache if pattern in k]
                for k in keys_to_remove:
                    del self._cache[k]
                logger.info("Invalidated %d cached predictions matching '%s'", len(keys_to_remove), pattern)

    def warm_cache(self, common_queries: list):
        """Pre-warm cache with common query results.

        common_queries: list of {"key": str, "fn": callable, "args": tuple, "kwargs": dict, "ttl": float}
        """
        logger.info("Warming cache with %d common queries", len(common_queries))
        for query in common_queries:
            key = query.get("key", "")
            fn = query.get("fn")
            args = query.get("args", ())
            kwargs = query.get("kwargs", {})
            ttl = query.get("ttl", 600.0)
            if fn is None or not key:
                continue
            try:
                start = time.perf_counter()
                result = fn(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                with self._lock:
                    self._cache[key] = (result, time.time() + ttl)
                    self._stats["precomputed"] += 1
                logger.debug("Warmed cache key '%s' in %.1fms", key, elapsed_ms)
            except Exception as exc:
                logger.warning("Failed to warm cache key '%s': %s", key, exc)

    def shutdown(self):
        self._thread_pool.shutdown(wait=False)
        logger.info("SpeculativeHyperExecutor shut down")


_instance: Optional[SpeculativeHyperExecutor] = None
_instance_lock = threading.RLock()


def get_speculative_hyper_executor() -> SpeculativeHyperExecutor:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SpeculativeHyperExecutor()
            logger.info("Created SpeculativeHyperExecutor singleton")
        return _instance
