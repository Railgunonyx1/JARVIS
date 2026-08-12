"""JARVIS MK-X Hyper-Optimization Engine — High-performance object pool."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("jarvis.hyper_opt.object_pool")


class HyperObjectPool:
    """High-performance object pool with pre-allocation, auto-scaling, and reset protocols."""

    def __init__(
        self,
        factory: Callable[[], Any] | None = None,
        reset_fn: Callable[[Any], None] | None = None,
        max_size: int = 50,
        min_size: int = 5,
        preallocate: bool = True,
        name: str = "default",
    ):
        self._factory = factory or dict
        self._reset_fn = reset_fn
        self._max_size = max_size
        self._min_size = min_size
        self._pool: list[Any] = []
        self._in_use: set = set()
        self._lock = threading.RLock()
        self._name = name
        self._current_obj: Any = None
        self._stats: dict[str, int] = {
            "created": 0,
            "reused": 0,
            "pool_hits": 0,
            "pool_misses": 0,
        }
        if preallocate:
            self._preallocate()
        logger.debug(
            "Pool '%s' created: max=%d min=%d preallocate=%s",
            self._name,
            self._max_size,
            self._min_size,
            preallocate,
        )

    def _preallocate(self) -> None:
        """Pre-create min_size objects."""
        with self._lock:
            for _ in range(self._min_size):
                obj = self._factory()
                self._pool.append(obj)
                self._stats["created"] += 1
        logger.debug("Pool '%s': pre-allocated %d objects", self._name, self._min_size)

    def acquire(self) -> Any:
        """Get an object from pool or create new. Returns object."""
        with self._lock:
            if self._pool:
                obj = self._pool.pop()
                self._in_use.add(id(obj))
                self._stats["pool_hits"] += 1
                self._stats["reused"] += 1
                logger.debug(
                    "Pool '%s': acquired from pool (remaining=%d, in_use=%d)",
                    self._name,
                    len(self._pool),
                    len(self._in_use),
                )
                return obj
            self._stats["pool_misses"] += 1
            obj = self._factory()
            self._stats["created"] += 1
            self._in_use.add(id(obj))
            logger.debug(
                "Pool '%s': created new object (in_use=%d)",
                self._name,
                len(self._in_use),
            )
            return obj

    def release(self, obj: Any) -> None:
        """Return object to pool after resetting it."""
        with self._lock:
            obj_id = id(obj)
            if obj_id not in self._in_use:
                logger.warning(
                    "Pool '%s': release called for object not tracked as in-use", self._name
                )
                return
            self._in_use.discard(obj_id)
            if self._reset_fn is not None:
                try:
                    self._reset_fn(obj)
                except Exception:
                    logger.exception("Pool '%s': reset function failed", self._name)
            if len(self._pool) < self._max_size:
                self._pool.append(obj)
                logger.debug(
                    "Pool '%s': released to pool (pool_size=%d, in_use=%d)",
                    self._name,
                    len(self._pool),
                    len(self._in_use),
                )
            else:
                logger.debug(
                    "Pool '%s': pool full, discarding object (max=%d)",
                    self._name,
                    self._max_size,
                )

    def batch_acquire(self, count: int) -> list[Any]:
        """Acquire multiple objects at once."""
        with self._lock:
            objects = []
            for _ in range(count):
                if self._pool:
                    obj = self._pool.pop()
                    self._in_use.add(id(obj))
                    self._stats["pool_hits"] += 1
                    self._stats["reused"] += 1
                else:
                    obj = self._factory()
                    self._stats["created"] += 1
                    self._stats["pool_misses"] += 1
                    self._in_use.add(id(obj))
                objects.append(obj)
            logger.debug(
                "Pool '%s': batch acquired %d objects", self._name, count
            )
            return objects

    def batch_release(self, objects: list[Any]) -> None:
        """Release multiple objects at once."""
        with self._lock:
            for obj in objects:
                obj_id = id(obj)
                if obj_id not in self._in_use:
                    continue
                self._in_use.discard(obj_id)
                if self._reset_fn is not None:
                    try:
                        self._reset_fn(obj)
                    except Exception:
                        logger.exception("Pool '%s': reset function failed in batch", self._name)
                if len(self._pool) < self._max_size:
                    self._pool.append(obj)
            logger.debug(
                "Pool '%s': batch released %d objects", self._name, len(objects)
            )

    def get_stats(self) -> dict:
        """Returns created, reused, pool_size, in_use, hit_rate, pool_hits, pool_misses."""
        with self._lock:
            total = self._stats["pool_hits"] + self._stats["pool_misses"]
            hit_rate = self._stats["pool_hits"] / total if total > 0 else 0.0
            return {
                "created": self._stats["created"],
                "reused": self._stats["reused"],
                "pool_size": len(self._pool),
                "in_use": len(self._in_use),
                "hit_rate": hit_rate,
                "pool_hits": self._stats["pool_hits"],
                "pool_misses": self._stats["pool_misses"],
            }

    def shrink(self, target: int | None = None) -> int:
        """Reduce pool size to target (default: min_size). Returns objects removed."""
        if target is None:
            target = self._min_size
        with self._lock:
            removed = 0
            while len(self._pool) > target:
                self._pool.pop()
                removed += 1
            logger.debug("Pool '%s': shrunk by %d objects", self._name, removed)
            return removed

    def clear(self) -> None:
        """Release all pooled objects."""
        with self._lock:
            count = len(self._pool)
            self._pool.clear()
            logger.debug("Pool '%s': cleared %d objects", self._name, count)

    @property
    def name(self) -> str:
        return self._name

    def __enter__(self) -> Any:
        """Context manager: acquire on enter."""
        self._current_obj = self.acquire()
        return self._current_obj

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager: release on exit."""
        if self._current_obj is not None:
            self.release(self._current_obj)
            self._current_obj = None


_named_pools: dict[str, HyperObjectPool] = {}
_pools_lock = threading.RLock()


def create_pool(
    name: str,
    factory: Callable[[], Any] | None = None,
    max_size: int = 50,
    min_size: int = 5,
) -> HyperObjectPool:
    """Creates or retrieves a named pool."""
    with _pools_lock:
        if name in _named_pools:
            logger.debug("Named pool '%s' already exists, returning existing", name)
            return _named_pools[name]
        pool = HyperObjectPool(
            factory=factory, max_size=max_size, min_size=min_size, name=name
        )
        _named_pools[name] = pool
        logger.info("Created named pool '%s' (max=%d, min=%d)", name, max_size, min_size)
        return pool


def get_pool(name: str) -> HyperObjectPool | None:
    """Retrieve a named pool by name."""
    with _pools_lock:
        return _named_pools.get(name)


def get_all_pools() -> dict[str, HyperObjectPool]:
    """Return a snapshot of all named pools."""
    with _pools_lock:
        return dict(_named_pools)


def remove_pool(name: str) -> bool:
    """Remove a named pool. Returns True if found and removed."""
    with _pools_lock:
        if name in _named_pools:
            _named_pools[name].clear()
            del _named_pools[name]
            logger.info("Removed named pool '%s'", name)
            return True
        return False
