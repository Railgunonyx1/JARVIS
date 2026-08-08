"""Async Optimizer — thread-pool-based concurrent execution for blocking callables."""

import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("jarvis.performance_engine.async_optimizer")

_MAX_WORKERS = 4


class AsyncOptimizer:
    """Runs blocking functions concurrently via a fixed-size thread pool."""

    def __init__(self, max_workers: int = _MAX_WORKERS) -> None:
        self._max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()
        self._tasks_completed: int = 0
        self._total_time: float = 0.0
        self._failures: int = 0

    # ------------------------------------------------------------------
    # Executor management
    # ------------------------------------------------------------------

    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            with self._lock:
                if self._executor is None:
                    self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
        return self._executor

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the thread pool."""
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown(wait=wait)
                self._executor = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_concurrent(self, tasks: List[Callable]) -> List[Any]:
        """Run a list of blocking callables concurrently and return their results.

        Order of results matches the order of *tasks*.
        """
        if not tasks:
            return []
        executor = self._get_executor()
        futures = [executor.submit(self._safe_call, fn) for fn in tasks]
        results: List[Any] = []
        for i, future in enumerate(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                logger.error("Task %d failed: %s", i, exc)
                results.append(None)
                with self._lock:
                    self._failures += 1
        return results

    def run_with_timeout(self, fn: Callable, timeout: float = 5.0) -> Optional[Any]:
        """Run *fn* with a timeout. Returns None if it exceeds *timeout* seconds."""
        executor = self._get_executor()
        future = executor.submit(self._safe_call, fn)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout:
            logger.warning("Task timed out after %.1fs", timeout)
            with self._lock:
                self._failures += 1
            return None
        except Exception as exc:
            logger.error("Task failed: %s", exc)
            with self._lock:
                self._failures += 1
            return None

    def batch_execute(self, fns: List[Callable], batch_size: int = 5) -> List[Any]:
        """Execute callables in controlled batches of *batch_size*.

        Waits for each batch to complete before starting the next.
        """
        if not fns:
            return []
        all_results: List[Any] = []
        for start in range(0, len(fns), batch_size):
            batch = fns[start : start + batch_size]
            batch_results = self.run_concurrent(batch)
            all_results.extend(batch_results)
        return all_results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _safe_call(self, fn: Callable) -> Any:
        """Wrap *fn* with timing and error handling."""
        start = time.perf_counter()
        try:
            result = fn()
            elapsed = time.perf_counter() - start
            with self._lock:
                self._tasks_completed += 1
                self._total_time += elapsed
            return result
        except Exception:
            elapsed = time.perf_counter() - start
            with self._lock:
                self._tasks_completed += 1
                self._total_time += elapsed
                self._failures += 1
            raise

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return execution statistics."""
        with self._lock:
            count = self._tasks_completed
            avg = (self._total_time / count) if count > 0 else 0.0
            return {
                "tasks_completed": count,
                "avg_time": round(avg, 4),
                "failures": self._failures,
                "max_workers": self._max_workers,
            }

    def reset_stats(self) -> None:
        """Reset statistics counters without shutting down the pool."""
        with self._lock:
            self._tasks_completed = 0
            self._total_time = 0.0
            self._failures = 0


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_async_optimizer: Optional[AsyncOptimizer] = None
_async_lock = threading.Lock()


def get_async_optimizer() -> AsyncOptimizer:
    global _async_optimizer
    if _async_optimizer is None:
        with _async_lock:
            if _async_optimizer is None:
                _async_optimizer = AsyncOptimizer()
    return _async_optimizer
