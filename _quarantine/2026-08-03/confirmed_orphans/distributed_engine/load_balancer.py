"""Load Balancer — tracks workers and assigns tasks to the least-loaded one."""

import time
import threading
import logging
from typing import Dict, Optional

logger = logging.getLogger("jarvis.distributed_engine.load_balancer")


class LoadBalancer:
    """Thread-safe load balancer for distributing tasks across named workers."""

    def __init__(self) -> None:
        self._workers: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def register_worker(self, name: str, capacity: int = 10) -> None:
        """Register a named worker with a given capacity."""
        with self._lock:
            if name in self._workers:
                logger.warning("Worker '%s' already registered, updating capacity", name)
            self._workers[name] = {
                "capacity": max(1, capacity),
                "current_load": 0,
                "total_tasks": 0,
                "total_duration_ms": 0.0,
                "avg_duration_ms": 0.0,
                "registered_at": time.monotonic(),
            }
            logger.info("Registered worker '%s' with capacity %d", name, capacity)

    def assign_task(self, task_id: str) -> Optional[str]:
        """Return the least-loaded worker name, or None if no workers registered."""
        with self._lock:
            best_name: Optional[str] = None
            best_load = float("inf")
            for name, info in self._workers.items():
                if info["current_load"] < best_load:
                    best_load = info["current_load"]
                    best_name = name
            if best_name is None:
                return None
            self._workers[best_name]["current_load"] += 1
            logger.debug("Assigned task '%s' to worker '%s'", task_id, best_name)
            return best_name

    def report_completion(self, worker: str, task_id: str, duration_ms: float) -> None:
        """Record that a task finished on the given worker."""
        with self._lock:
            info = self._workers.get(worker)
            if info is None:
                logger.warning("Completion reported for unknown worker '%s'", worker)
                return
            info["current_load"] = max(0, info["current_load"] - 1)
            info["total_tasks"] += 1
            info["total_duration_ms"] += duration_ms
            info["avg_duration_ms"] = info["total_duration_ms"] / info["total_tasks"]
            logger.debug(
                "Worker '%s' completed task '%s' in %.1f ms",
                worker, task_id, duration_ms,
            )

    def get_worker_stats(self) -> Dict[str, dict]:
        """Return per-worker load, average duration, and task count."""
        with self._lock:
            stats: Dict[str, dict] = {}
            for name, info in self._workers.items():
                stats[name] = {
                    "current_load": info["current_load"],
                    "capacity": info["capacity"],
                    "load_ratio": round(
                        info["current_load"] / info["capacity"], 4
                    ) if info["capacity"] else 0.0,
                    "total_tasks": info["total_tasks"],
                    "avg_duration_ms": round(info["avg_duration_ms"], 2),
                }
            return stats

    def get_least_loaded(self) -> Optional[str]:
        """Return the worker name with the lowest current load."""
        with self._lock:
            best_name: Optional[str] = None
            best_load = float("inf")
            for name, info in self._workers.items():
                if info["current_load"] < best_load:
                    best_load = info["current_load"]
                    best_name = name
            return best_name

    def unregister_worker(self, name: str) -> bool:
        """Remove a worker. Returns True if it existed."""
        with self._lock:
            if name in self._workers:
                del self._workers[name]
                logger.info("Unregistered worker '%s'", name)
                return True
            return False


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: Optional[LoadBalancer] = None
_instance_lock = threading.Lock()


def get_load_balancer() -> LoadBalancer:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = LoadBalancer()
    return _instance
