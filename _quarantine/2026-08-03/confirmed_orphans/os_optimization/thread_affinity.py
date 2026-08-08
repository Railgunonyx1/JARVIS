"""Thread Pool Affinity — Dedicated pools for each subsystem.

STT pool | TTS pool | Vision pool | Automation pool | LLM pool | Network pool
Avoids thread creation/destruction overhead.
"""
import logging
import threading
from typing import Optional, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

logger = logging.getLogger("os_optimization.thread_affinity")


@dataclass
class ThreadPool:
    """A dedicated thread pool for a subsystem."""
    name: str
    executor: ThreadPoolExecutor = None
    min_threads: int = 1
    max_threads: int = 4
    active_tasks: int = 0
    total_tasks: int = 0

    def __post_init__(self):
        if self.executor is None:
            self.executor = ThreadPoolExecutor(
                max_workers=self.max_threads,
                thread_name_prefix=f"jarvis_{self.name}",
            )


class ThreadAffinityManager:
    """Maintain dedicated thread pools per subsystem.

    Avoids overhead of creating/destroying threads for each request.
    Pre-warmed pools are always ready for immediate task execution.
    """

    DEFAULT_POOLS = {
        "stt": ThreadPool("stt", min_threads=1, max_threads=2),
        "tts": ThreadPool("tts", min_threads=1, max_threads=2),
        "vision": ThreadPool("vision", min_threads=1, max_threads=2),
        "automation": ThreadPool("automation", min_threads=2, max_threads=4),
        "llm": ThreadPool("llm", min_threads=1, max_threads=3),
        "network": ThreadPool("network", min_threads=2, max_threads=6),
        "indexing": ThreadPool("indexing", min_threads=1, max_threads=2),
    }

    def __init__(self):
        self._pools: Dict[str, ThreadPool] = dict(self.DEFAULT_POOLS)
        self._lock = threading.Lock()

    def submit(self, pool_name: str, fn: Callable, *args, **kwargs):
        """Submit a task to a specific subsystem pool."""
        pool = self._pools.get(pool_name)
        if pool is None:
            raise ValueError(f"Unknown pool: {pool_name}")

        with self._lock:
            pool.active_tasks += 1
            pool.total_tasks += 1

        future = pool.executor.submit(fn, *args, **kwargs)
        future.add_done_callback(lambda _: self._task_done(pool_name))
        return future

    def _task_done(self, pool_name: str) -> None:
        pool = self._pools.get(pool_name)
        if pool:
            with self._lock:
                pool.active_tasks = max(0, pool.active_tasks - 1)

    def get_pool_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                name: {
                    "max_threads": pool.max_threads,
                    "active_tasks": pool.active_tasks,
                    "total_tasks": pool.total_tasks,
                }
                for name, pool in self._pools.items()
            }

    def shutdown(self) -> None:
        for pool in self._pools.values():
            pool.executor.shutdown(wait=False)


_affinity_instance: Optional[ThreadAffinityManager] = None


def get_thread_affinity_manager() -> ThreadAffinityManager:
    global _affinity_instance
    if _affinity_instance is None:
        _affinity_instance = ThreadAffinityManager()
    return _affinity_instance
