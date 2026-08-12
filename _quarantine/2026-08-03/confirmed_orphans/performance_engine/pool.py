"""Object Pool — reusable object pool for expensive-to-create resources."""

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("jarvis.performance_engine.pool")


class ObjectPool:
    """Generic, thread-safe object pool with pre-allocation and lifecycle tracking."""

    def __init__(
        self,
        factory: Callable[[], Any],
        max_size: int = 10,
        min_size: int = 2,
    ) -> None:
        if min_size < 0:
            raise ValueError("min_size must be >= 0")
        if max_size < max(min_size, 1):
            raise ValueError("max_size must be >= min_size and >= 1")

        self._factory = factory
        self._max_size = max_size
        self._min_size = min_size
        self._pool: list[Any] = []
        self._lock = threading.Lock()
        self._created_count: int = 0
        self._reused_count: int = 0

        self._pre_create(min_size)

    # ------------------------------------------------------------------
    # Pre-allocation
    # ------------------------------------------------------------------

    def _pre_create(self, count: int) -> None:
        for _ in range(count):
            obj = self._factory()
            self._pool.append(obj)
            self._created_count += 1
        if count > 0:
            logger.debug("Pre-created %d objects", count)

    # ------------------------------------------------------------------
    # Acquire / release
    # ------------------------------------------------------------------

    def acquire(self) -> Any:
        """Get an object from the pool or create a new one if the pool is empty."""
        with self._lock:
            if self._pool:
                obj = self._pool.pop()
                self._reused_count += 1
                return obj

        # Pool empty — create outside lock to avoid blocking during factory call.
        obj = self._factory()
        with self._lock:
            self._created_count += 1
        return obj

    def release(self, obj: Any) -> None:
        """Return an object to the pool. Drops it if the pool is at max capacity."""
        with self._lock:
            if len(self._pool) < self._max_size:
                self._pool.append(obj)
            else:
                logger.debug("Pool full, discarding object")

    # ------------------------------------------------------------------
    # Context manager convenience
    # ------------------------------------------------------------------

    def __enter__(self) -> "ObjectPoolContext":
        obj = self.acquire()
        return ObjectPoolContext(self, obj)

    def __exit__(self, *args: Any) -> None:
        pass

    # ------------------------------------------------------------------
    # Stats / housekeeping
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return pool statistics."""
        with self._lock:
            return {
                "created": self._created_count,
                "reused": self._reused_count,
                "pool_size": len(self._pool),
                "max_size": self._max_size,
                "min_size": self._min_size,
            }

    def clear(self) -> int:
        """Remove all objects from the pool. Returns the count removed."""
        with self._lock:
            count = len(self._pool)
            self._pool.clear()
            return count

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._pool)


class ObjectPoolContext:
    """Context manager wrapper that auto-releases an object back to the pool."""

    __slots__ = ("_pool", "_obj")

    def __init__(self, pool: ObjectPool, obj: Any) -> None:
        self._pool = pool
        self._obj = obj

    @property
    def obj(self) -> Any:
        return self._obj

    def __enter__(self) -> "ObjectPoolContext":
        return self

    def __exit__(self, *args: Any) -> None:
        self._pool.release(self._obj)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._obj, name)
