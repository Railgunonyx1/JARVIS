"""JARVIS MK-X Hyper-Optimization Engine — Smart memory management."""

from __future__ import annotations

import gc
import logging
import threading
import time

logger = logging.getLogger("jarvis.hyper_opt.memory_allocator")


class MemoryAllocator:
    """Smart memory management with GC control and allocation tracking."""

    def __init__(self) -> None:
        self._allocations: dict[str, dict] = {}
        self._pools: dict[str, list[bytearray]] = {}
        self._gc_disabled_until: float = 0.0
        self._gc_scheduled: bool = False
        self._gc_scheduled_at: float = 0.0
        self._gc_delay: float = 0.0
        self._lock = threading.RLock()
        self._stats: dict[str, int | float] = {
            "allocated": 0,
            "freed": 0,
            "gc_runs": 0,
            "gc_disabled_time": 0.0,
        }
        logger.debug("MemoryAllocator initialized")

    def allocate(self, name: str, size_bytes: int, category: str = "general") -> bytearray:
        """Allocate a named buffer."""
        with self._lock:
            if name in self._allocations:
                logger.warning("Allocation '%s' already exists, returning existing", name)
                return self._allocations[name]["buffer"]
            buf = self._get_or_create_buffer(size_bytes, category)
            self._allocations[name] = {
                "buffer": buf,
                "size": size_bytes,
                "created_at": time.time(),
                "category": category,
            }
            self._stats["allocated"] += 1
            logger.debug(
                "Allocated '%s': %d bytes (category=%s)",
                name,
                size_bytes,
                category,
            )
            return buf

    def _get_or_create_buffer(self, size_bytes: int, category: str) -> bytearray:
        """Retrieve a reusable buffer from pool or create a new one."""
        pool = self._pools.get(category, [])
        for i, buf in enumerate(pool):
            if len(buf) >= size_bytes:
                pool.pop(i)
                return buf
        return bytearray(size_bytes)

    def free(self, name: str) -> bool:
        """Free a named allocation. Returns True if freed."""
        with self._lock:
            entry = self._allocations.pop(name, None)
            if entry is None:
                logger.warning("Allocation '%s' not found", name)
                return False
            buf = entry["buffer"]
            category = entry["category"]
            if category not in self._pools:
                self._pools[category] = []
            pool = self._pools[category]
            if len(pool) < 16:
                pool.append(buf)
            self._stats["freed"] += 1
            logger.debug(
                "Freed '%s': %d bytes (category=%s)",
                name,
                entry["size"],
                category,
            )
            return True

    def get_allocation(self, name: str) -> bytearray | None:
        """Get an allocated buffer by name."""
        with self._lock:
            entry = self._allocations.get(name)
            if entry is None:
                return None
            return entry["buffer"]

    def disable_gc(self, duration_seconds: float = 5.0) -> None:
        """Temporarily disable garbage collection during critical path."""
        with self._lock:
            self._gc_disabled_until = time.time() + duration_seconds
            self._stats["gc_disabled_time"] += duration_seconds
            logger.debug("GC disabled for %.1f seconds", duration_seconds)

    def enable_gc(self) -> None:
        """Re-enable garbage collection."""
        with self._lock:
            self._gc_disabled_until = 0.0
            logger.debug("GC re-enabled")

    def should_gc(self) -> bool:
        """Check if GC should run (returns False if disabled)."""
        if self._gc_disabled_until > 0.0:
            if time.time() < self._gc_disabled_until:
                return False
            self._gc_disabled_until = 0.0
        if self._gc_scheduled:
            if time.time() >= self._gc_scheduled_at + self._gc_delay:
                self._gc_scheduled = False
                return True
        return False

    def schedule_gc(self, delay_seconds: float = 1.0) -> None:
        """Schedule a deferred GC run."""
        with self._lock:
            self._gc_scheduled = True
            self._gc_scheduled_at = time.time()
            self._gc_delay = delay_seconds
            logger.debug("GC scheduled in %.1f seconds", delay_seconds)

    def force_gc(self) -> dict:
        """Force garbage collection, return freed bytes."""
        before = len(gc.garbage)
        freed = gc.collect()
        self._stats["gc_runs"] += 1
        after = len(gc.garbage)
        result = {
            "collected": freed,
            "garbage_before": before,
            "garbage_after": after,
            "gc_disabled": self.should_gc() is False,
        }
        logger.debug("Forced GC: collected=%d", freed)
        return result

    def get_memory_profile(self) -> dict:
        """Returns total_allocated, by_category, gc_stats."""
        with self._lock:
            total_allocated = sum(e["size"] for e in self._allocations.values())
            by_category: dict[str, int] = {}
            for entry in self._allocations.values():
                cat = entry["category"]
                by_category[cat] = by_category.get(cat, 0) + entry["size"]
            pool_sizes: dict[str, int] = {}
            for cat, pool in self._pools.items():
                pool_sizes[cat] = sum(len(b) for b in pool)
            return {
                "total_allocated": total_allocated,
                "allocation_count": len(self._allocations),
                "by_category": by_category,
                "pool_sizes": pool_sizes,
                "gc_disabled": time.time() < self._gc_disabled_until,
                "gc_scheduled": self._gc_scheduled,
            }

    def get_stats(self) -> dict:
        """Returns allocation stats, GC stats, memory usage."""
        with self._lock:
            total_allocated = sum(e["size"] for e in self._allocations.values())
            total_pooled = sum(
                sum(len(b) for b in pool) for pool in self._pools.values()
            )
            return {
                "allocated": self._stats["allocated"],
                "freed": self._stats["freed"],
                "active_count": len(self._allocations),
                "active_bytes": total_allocated,
                "pooled_bytes": total_pooled,
                "gc_runs": self._stats["gc_runs"],
                "gc_disabled_time": self._stats["gc_disabled_time"],
            }

    def cleanup_expired(self, max_age_seconds: float = 300) -> int:
        """Free allocations older than max_age. Returns count freed."""
        with self._lock:
            now = time.time()
            expired = [
                name
                for name, entry in self._allocations.items()
                if (now - entry["created_at"]) > max_age_seconds
            ]
            for name in expired:
                self.free(name)
            if expired:
                logger.info("Cleaned up %d expired allocations", len(expired))
            return len(expired)

    def get_pool_stats(self) -> dict:
        """Returns buffer pool statistics per category."""
        with self._lock:
            result = {}
            for cat, pool in self._pools.items():
                result[cat] = {
                    "count": len(pool),
                    "total_bytes": sum(len(b) for b in pool),
                }
            return result


_instance: MemoryAllocator | None = None
_instance_lock = threading.RLock()


def get_memory_allocator() -> MemoryAllocator:
    """Singleton accessor for MemoryAllocator."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = MemoryAllocator()
                logger.info("MemoryAllocator singleton created")
    return _instance
