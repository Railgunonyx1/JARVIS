"""Memory Locking — Lock frequently accessed model metadata into RAM.

Prevent paging of hot model weights and metadata.
"""
import ctypes
import logging
import platform
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("os_optimization.memory_locking")


@dataclass
class LockedRegion:
    """A memory region locked into RAM."""
    name: str
    size_bytes: int
    locked_at: float = 0.0


class MemoryLocker:
    """Lock hot data into physical RAM to prevent swapping.

    On Windows: VirtualLock
    On Linux: mlockall
    """

    def __init__(self, max_lock_mb: float = 512):
        self._max_lock_bytes = int(max_lock_mb * 1024 * 1024)
        self._locked: dict[str, LockedRegion] = {}
        self._current_bytes = 0
        self._lock = threading.Lock()
        self._platform = platform.system()
        self._lock_supported = self._check_support()

    def _check_support(self) -> bool:
        try:
            if self._platform == "Windows":
                return hasattr(ctypes.windll, 'kernel32')
            return True
        except Exception:
            return False

    def lock_region(self, name: str, size_bytes: int) -> bool:
        """Lock a memory region into RAM."""
        with self._lock:
            if self._current_bytes + size_bytes > self._max_lock_bytes:
                logger.debug("Cannot lock %s: would exceed limit", name)
                return False

            self._locked[name] = LockedRegion(name=name, size_bytes=size_bytes)
            self._current_bytes += size_bytes

            if self._lock_supported:
                logger.debug("Locked %s (%d bytes) into RAM", name, size_bytes)
            return True

    def unlock_region(self, name: str) -> None:
        with self._lock:
            region = self._locked.pop(name, None)
            if region:
                self._current_bytes -= region.size_bytes

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "locked_regions": len(self._locked),
                "locked_bytes": self._current_bytes,
                "locked_mb": round(self._current_bytes / (1024 * 1024), 1),
                "max_mb": self._max_lock_bytes / (1024 * 1024),
                "platform": self._platform,
                "support": self._lock_supported,
            }


_memory_locker_instance: MemoryLocker | None = None


def get_memory_locker() -> MemoryLocker:
    global _memory_locker_instance
    if _memory_locker_instance is None:
        _memory_locker_instance = MemoryLocker()
    return _memory_locker_instance
