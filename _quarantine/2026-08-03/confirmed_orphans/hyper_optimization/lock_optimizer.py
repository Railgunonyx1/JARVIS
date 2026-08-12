"""JARVIS MK-X Hyper-Optimization Engine — Lock contention monitoring."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("jarvis.hyper_opt.lock_optimizer")


class _MonitoredLockInfo:
    """Internal tracking data for a single monitored lock."""

    __slots__ = (
        "lock",
        "total_wait_ns",
        "acquisitions",
        "contention_count",
        "max_wait_ns",
        "current_waiters",
    )

    def __init__(self, lock: threading.RLock) -> None:
        self.lock = lock
        self.total_wait_ns: int = 0
        self.acquisitions: int = 0
        self.contention_count: int = 0
        self.max_wait_ns: int = 0
        self.current_waiters: int = 0


class _MonitoredContext:
    """Context manager for a monitored lock acquisition."""

    __slots__ = ("_optimizer", "_name", "_acquired")

    def __init__(self, optimizer: LockOptimizer, name: str) -> None:
        self._optimizer = optimizer
        self._name = name
        self._acquired = False

    def __enter__(self) -> _MonitoredContext:
        self._acquired = self._optimizer.acquire_monitored(self._name)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._acquired:
            self._optimizer.release_monitored(self._name)


class LockOptimizer:
    """Monitors lock contention and suggests optimizations."""

    def __init__(self) -> None:
        self._locks: dict[str, _MonitoredLockInfo] = {}
        self._lock = threading.RLock()
        self._monitoring: bool = True
        logger.debug("LockOptimizer initialized")

    def wrap_lock(self, name: str, lock: threading.RLock | None = None) -> threading.RLock:
        """Create or wrap a lock with contention monitoring. Returns the lock."""
        with self._lock:
            if name in self._locks:
                logger.debug("Lock '%s' already wrapped", name)
                return self._locks[name].lock
            if lock is None:
                lock = threading.RLock()
            info = _MonitoredLockInfo(lock)
            self._locks[name] = info
            logger.debug("Wrapped lock '%s'", name)
            return lock

    def acquire_monitored(self, name: str, timeout: float = 5.0) -> bool:
        """Acquire a monitored lock, tracking wait time."""
        with self._lock:
            info = self._locks.get(name)
            if info is None:
                info = _MonitoredLockInfo(threading.RLock())
                self._locks[name] = info
        info.current_waiters += 1
        start_ns = time.perf_counter_ns()
        acquired = info.lock.acquire(timeout=timeout)
        elapsed_ns = time.perf_counter_ns() - start_ns
        info.current_waiters -= 1
        if not acquired:
            logger.warning("Lock '%s' acquisition timed out after %.1fms", name, elapsed_ns / 1e6)
            return False
        info.acquisitions += 1
        info.total_wait_ns += elapsed_ns
        if elapsed_ns > 100_000:
            info.contention_count += 1
        if elapsed_ns > info.max_wait_ns:
            info.max_wait_ns = elapsed_ns
        return True

    def release_monitored(self, name: str) -> None:
        """Release a monitored lock."""
        with self._lock:
            info = self._locks.get(name)
        if info is None:
            logger.warning("Release called for unknown lock '%s'", name)
            return
        try:
            info.lock.release()
        except RuntimeError:
            logger.exception("Failed to release lock '%s'", name)

    def context_manager(self, name: str) -> _MonitoredContext:
        """Return a context manager for a monitored lock."""
        return _MonitoredContext(self, name)

    def get_contention_report(self) -> dict:
        """Returns per-lock contention stats sorted by total wait time."""
        with self._lock:
            report = {}
            for name, info in self._locks.items():
                avg_wait_ms = (
                    (info.total_wait_ns / info.acquisitions) / 1e6
                    if info.acquisitions > 0
                    else 0.0
                )
                report[name] = {
                    "total_wait_ms": round(info.total_wait_ns / 1e6, 4),
                    "acquisitions": info.acquisitions,
                    "contention_count": info.contention_count,
                    "avg_wait_ms": round(avg_wait_ms, 4),
                    "max_wait_ms": round(info.max_wait_ns / 1e6, 4),
                    "current_waiters": info.current_waiters,
                }
            sorted_report = dict(
                sorted(report.items(), key=lambda x: x[1]["total_wait_ms"], reverse=True)
            )
            return sorted_report

    def get_hot_locks(self, threshold_ms: float = 10) -> list:
        """Returns locks with high contention (avg wait > threshold_ms)."""
        with self._lock:
            hot = []
            for name, info in self._locks.items():
                if info.acquisitions == 0:
                    continue
                avg_ms = (info.total_wait_ns / info.acquisitions) / 1e6
                if avg_ms > threshold_ms or info.contention_count > 5:
                    hot.append(
                        {
                            "name": name,
                            "avg_wait_ms": round(avg_ms, 4),
                            "contention_count": info.contention_count,
                            "total_wait_ms": round(info.total_wait_ns / 1e6, 4),
                        }
                    )
            hot.sort(key=lambda x: x["total_wait_ms"], reverse=True)
            return hot

    def suggest_optimizations(self) -> list:
        """Suggest lock optimizations based on contention patterns."""
        suggestions = []
        hot_locks = self.get_hot_locks(threshold_ms=5)
        for entry in hot_locks:
            name = entry["name"]
            avg_ms = entry["avg_wait_ms"]
            contentions = entry["contention_count"]
            if avg_ms > 20:
                suggestions.append(
                    {
                        "lock": name,
                        "issue": "very_high_contention",
                        "suggestion": "Consider lock-free data structures or sharding",
                        "severity": "critical",
                        "avg_wait_ms": avg_ms,
                    }
                )
            elif avg_ms > 10:
                suggestions.append(
                    {
                        "lock": name,
                        "issue": "high_contention",
                        "suggestion": "Reduce critical section scope or use RLock for reentrant access",
                        "severity": "warning",
                        "avg_wait_ms": avg_ms,
                    }
                )
            elif contentions > 10:
                suggestions.append(
                    {
                        "lock": name,
                        "issue": "frequent_contention",
                        "suggestion": "Use fine-grained locking or per-thread buffers",
                        "severity": "info",
                        "avg_wait_ms": avg_ms,
                    }
                )
        if not suggestions:
            suggestions.append(
                {
                    "lock": None,
                    "issue": "none",
                    "suggestion": "No significant contention detected",
                    "severity": "ok",
                    "avg_wait_ms": 0.0,
                }
            )
        return suggestions

    def get_stats(self) -> dict:
        """Returns total_locks, total_contentions, avg_wait_ms, max_wait_ms."""
        with self._lock:
            total_locks = len(self._locks)
            total_contentions = 0
            total_wait_ns = 0
            max_wait_ns = 0
            total_acquisitions = 0
            for info in self._locks.values():
                total_contentions += info.contention_count
                total_wait_ns += info.total_wait_ns
                if info.max_wait_ns > max_wait_ns:
                    max_wait_ns = info.max_wait_ns
                total_acquisitions += info.acquisitions
            avg_wait_ms = (
                (total_wait_ns / total_acquisitions) / 1e6
                if total_acquisitions > 0
                else 0.0
            )
            return {
                "total_locks": total_locks,
                "total_contentions": total_contentions,
                "total_acquisitions": total_acquisitions,
                "avg_wait_ms": round(avg_wait_ms, 4),
                "max_wait_ms": round(max_wait_ns / 1e6, 4),
                "monitoring": self._monitoring,
            }

    def reset_stats(self) -> None:
        """Reset all lock statistics."""
        with self._lock:
            for info in self._locks.values():
                info.total_wait_ns = 0
                info.acquisitions = 0
                info.contention_count = 0
                info.max_wait_ns = 0
                info.current_waiters = 0
            logger.info("Lock stats reset for %d locks", len(self._locks))

    def set_monitoring(self, enabled: bool) -> None:
        """Enable or disable monitoring."""
        with self._lock:
            self._monitoring = enabled
            logger.debug("Monitoring %s", "enabled" if enabled else "disabled")

    def remove_lock(self, name: str) -> bool:
        """Remove a lock from monitoring. Returns True if found."""
        with self._lock:
            removed = self._locks.pop(name, None)
            if removed is not None:
                logger.debug("Removed lock '%s' from monitoring", name)
                return True
            return False


_instance: LockOptimizer | None = None
_instance_lock = threading.RLock()


def get_lock_optimizer() -> LockOptimizer:
    """Singleton accessor for LockOptimizer."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = LockOptimizer()
                logger.info("LockOptimizer singleton created")
    return _instance
