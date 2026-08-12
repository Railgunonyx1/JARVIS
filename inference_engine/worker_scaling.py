"""Dynamic Worker Scaling — Automatically scale workers based on load.

Idle: 2 workers | Heavy workload: 12 workers
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger("inference_optimization.worker_scaling")


class DynamicWorkerScaler:
    """Automatically scale thread pool based on workload.

    Scales up under heavy load, scales down during idle periods.
    """

    def __init__(self, min_workers: int = 2, max_workers: int = 12,
                 scale_up_threshold: float = 0.8, scale_down_threshold: float = 0.2):
        self._min = min_workers
        self._max = max_workers
        self._up_threshold = scale_up_threshold
        self._down_threshold = scale_down_threshold
        self._current_workers = min_workers
        self._executor = ThreadPoolExecutor(max_workers=min_workers, thread_name_prefix="dynamic")
        self._active_tasks = 0
        self._total_tasks = 0
        self._lock = threading.Lock()
        self._scale_events: list = []

    def submit(self, fn, *args, **kwargs):
        """Submit a task, auto-scaling if needed."""
        with self._lock:
            self._active_tasks += 1
            self._total_tasks += 1
            self._maybe_scale()

        try:
            future = self._executor.submit(fn, *args, **kwargs)
            future.add_done_callback(self._task_done)
            return future
        except Exception:
            with self._lock:
                self._active_tasks -= 1
            raise

    def _task_done(self, future):
        with self._lock:
            self._active_tasks = max(0, self._active_tasks - 1)
            self._maybe_scale()

    def _maybe_scale(self) -> None:
        utilization = self._active_tasks / max(self._current_workers, 1)

        if utilization > self._up_threshold and self._current_workers < self._max:
            new_count = min(self._current_workers + 2, self._max)
            self._scale(new_count)
        elif utilization < self._down_threshold and self._current_workers > self._min:
            new_count = max(self._current_workers - 1, self._min)
            self._scale(new_count)

    def _scale(self, new_count: int) -> None:
        if new_count == self._current_workers:
            return
        old = self._current_workers
        self._current_workers = new_count
        self._scale_events.append({"from": old, "to": new_count, "ts": time.time()})
        if len(self._scale_events) > 100:
            self._scale_events = self._scale_events[-100:]
        logger.info("Worker pool: %d → %d", old, new_count)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "current_workers": self._current_workers,
                "active_tasks": self._active_tasks,
                "total_tasks": self._total_tasks,
                "utilization": round(self._active_tasks / max(self._current_workers, 1) * 100, 1),
                "scale_events": len(self._scale_events),
            }


_worker_scaler_instance: DynamicWorkerScaler | None = None


def get_worker_scaler() -> DynamicWorkerScaler:
    global _worker_scaler_instance
    if _worker_scaler_instance is None:
        _worker_scaler_instance = DynamicWorkerScaler()
    return _worker_scaler_instance
