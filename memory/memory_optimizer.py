"""Memory Optimizer — memory profiling, tracking, and garbage collection for JARVIS."""

import gc
import logging
import sys
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("jarvis.memory_engine.memory_optimizer")

try:
    import psutil
    _psutil_ok = True
except ImportError:
    _psutil_ok = False

_instance: Optional["MemoryOptimizer"] = None
_lock = threading.Lock()

_PROCESS = None
if _psutil_ok:
    try:
        _PROCESS = psutil.Process()
    except Exception:
        pass


def _obj_size_mb(obj: Any) -> float:
    """Rough byte-size estimate for a Python object via sys.getsizeof recursion."""
    try:
        size = sys.getsizeof(obj)
        if isinstance(obj, dict):
            size += sum(_obj_size_mb(k) + _obj_size_mb(v) for k, v in obj.items())
        elif hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, bytearray)):
            try:
                size += sum(_obj_size_mb(item) for item in obj)
            except TypeError:
                pass
        return size / (1024 * 1024)
    except Exception:
        return 0.0


class MemoryOptimizer:
    """Tracks memory allocations, profiles usage, and runs garbage collection."""

    def __init__(self):
        self._allocations: dict[str, int] = {}
        self._limit_mb: int = 2048
        self._lock = threading.Lock()
        self._profile_cache: dict | None = None
        self._profile_ts: float = 0.0

    def optimize(self) -> dict:
        """Run garbage collection and return a summary of freed memory."""
        before = self._rss_mb()
        collected = gc.collect()
        after = self._rss_mb()
        freed = max(0.0, before - after)
        logger.info("GC collected %d objects, freed %.2f MB", collected, freed)
        return {
            "objects_collected": collected,
            "rss_before_mb": round(before, 2),
            "rss_after_mb": round(after, 2),
            "freed_mb": round(freed, 2),
        }

    def force_gc(self) -> dict:
        """Force a full garbage collection cycle and return freed bytes estimate."""
        before = self._rss_bytes()
        gc.collect(2)
        after = self._rss_bytes()
        freed = max(0, before - after)
        logger.info("Force GC freed %d bytes", freed)
        return {
            "freed_bytes": freed,
            "freed_mb": round(freed / (1024 * 1024), 2),
        }

    def get_memory_profile(self) -> dict:
        """Return detailed memory usage breakdown by category."""
        now = time.time()
        if self._profile_cache is not None and (now - self._profile_ts) < 5.0:
            return self._profile_cache

        profile: dict[str, Any] = {}

        if _PROCESS:
            mem_info = _PROCESS.memory_info()
            profile["rss_mb"] = round(mem_info.rss / (1024 * 1024), 2)
            profile["vms_mb"] = round(mem_info.vms / (1024 * 1024), 2)
        else:
            profile["rss_mb"] = 0.0
            profile["vms_mb"] = 0.0

        profile["python_objects"] = round(_obj_size_mb(sys.modules), 2)

        sqlite_mb = 0.0
        try:
            import memory.store as _store_mod
            store = getattr(_store_mod, "_store", None)
            if store is not None:
                conn = getattr(store, "_conn", None)
                if conn is not None:
                    result = conn.execute("PRAGMA page_count").fetchone()
                    page_size = conn.execute("PRAGMA page_size").fetchone()
                    if result and page_size:
                        sqlite_mb = round((result[0] * page_size[0]) / (1024 * 1024), 2)
        except Exception:
            pass
        profile["sqlite_mb"] = sqlite_mb

        profile["cache_mb"] = 0.0

        vector_mb = 0.0
        try:
            import memory.vector_store as _vs_mod
            for attr_name in dir(_vs_mod):
                attr = getattr(_vs_mod, attr_name, None)
                if hasattr(attr, "_conn"):
                    vector_mb = round(_obj_size_mb(attr), 2)
                    break
        except Exception:
            pass
        profile["vector_store_mb"] = vector_mb

        profile["plugin_mb"] = round(_obj_size_mb(self._allocations), 2)

        profile["total_allocations"] = len(self._allocations)
        profile["tracked_bytes"] = sum(self._allocations.values())

        self._profile_cache = profile
        self._profile_ts = now
        return profile

    def suggest_optimizations(self) -> list[dict]:
        """Return actionable optimization suggestions with priority levels."""
        suggestions: list[dict] = []
        profile = self.get_memory_profile()

        rss = profile.get("rss_mb", 0)
        if rss > self._limit_mb * 0.8:
            suggestions.append({
                "priority": "high",
                "category": "memory_limit",
                "message": (
                    f"RSS ({rss} MB) is above 80% of limit ({self._limit_mb} MB). "
                    "Consider reducing cache sizes."
                ),
                "action": "reduce_caches",
            })

        if profile.get("cache_mb", 0) > 100:
            suggestions.append({
                "priority": "medium",
                "category": "cache",
                "message": f"Cache is using {profile['cache_mb']} MB. Consider warming fewer entries.",
                "action": "reduce_warm_cache",
            })

        if profile.get("python_objects", 0) > 200:
            suggestions.append({
                "priority": "low",
                "category": "python_objects",
                "message": "Large number of loaded Python modules. Consider lazy-loading non-critical modules.",
                "action": "lazy_import",
            })

        if profile.get("sqlite_mb", 0) > 500:
            suggestions.append({
                "priority": "medium",
                "category": "sqlite",
                "message": f"SQLite database is {profile['sqlite_mb']} MB. Consider VACUUM or archiving old data.",
                "action": "vacuum_database",
            })

        if not suggestions:
            suggestions.append({
                "priority": "info",
                "category": "general",
                "message": "Memory usage is within normal bounds.",
                "action": "none",
            })

        return suggestions

    def set_memory_limit(self, limit_mb: int = 2048) -> None:
        """Set the soft memory limit in MB."""
        self._limit_mb = limit_mb
        logger.info("Memory limit set to %d MB", limit_mb)

    def should_throttle(self) -> bool:
        """Return True if current RSS is approaching the memory limit."""
        rss = self._rss_mb()
        return rss > self._limit_mb * 0.9

    def track_allocation(self, name: str, size_bytes: int) -> None:
        """Track a named memory allocation."""
        with self._lock:
            self._allocations[name] = size_bytes

    def get_allocations(self) -> dict:
        """Return a copy of all tracked allocations."""
        with self._lock:
            return dict(self._allocations)

    def _rss_mb(self) -> float:
        return self._rss_bytes() / (1024 * 1024)

    def _rss_bytes(self) -> int:
        if _PROCESS:
            try:
                return _PROCESS.memory_info().rss
            except Exception:
                pass
        return 0


def get_memory_optimizer() -> MemoryOptimizer:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = MemoryOptimizer()
    return _instance
