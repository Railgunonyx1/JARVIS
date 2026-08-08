"""Central Thread Pool Manager — Prevents thread explosion across services.

All background work should use this pool instead of creating raw threads.
"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

_pool: Optional[ThreadPoolExecutor] = None
_lock = threading.Lock()


def get_pool(max_workers: Optional[int] = None) -> ThreadPoolExecutor:
    """Get or create the shared thread pool.

    Worker count is auto-scaled to CPU cores (capped at 8) unless overridden.
    """
    global _pool
    with _lock:
        if _pool is None:
            if max_workers is None:
                cpu_count = os.cpu_count() or 4
                max_workers = min(8, max(4, cpu_count))
            _pool = ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="jarvis-worker",
            )
        return _pool


def shutdown_pool(wait: bool = True):
    """Shutdown the thread pool gracefully."""
    global _pool
    with _lock:
        if _pool is not None:
            _pool.shutdown(wait=wait)
            _pool = None
