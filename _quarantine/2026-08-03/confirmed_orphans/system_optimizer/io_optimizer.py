"""IO Optimizer — disk I/O stats, batch writes, read-ahead, and disk health heuristics."""

import os
import sys
import time
import logging
import threading
from typing import List, Tuple, Optional

import psutil

logger = logging.getLogger("jarvis.system_optimizer.io_optimizer")


class IOOptimizer:
    """Monitors I/O stats, provides batch writing, and disk usage heuristics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._batch_history: List[dict] = []

    def get_io_stats(self) -> dict:
        """Return current system I/O counters."""
        try:
            counters = psutil.disk_io_counters()
            if counters is None:
                return {"error": "Disk I/O counters not available on this platform"}
            return {
                "read_bytes": counters.read_bytes,
                "write_bytes": counters.write_bytes,
                "read_count": counters.read_count,
                "write_count": counters.write_count,
                "read_time_ms": counters.read_time,
                "write_time_ms": counters.write_time,
            }
        except Exception as e:
            return {"error": str(e)}

    def set_read_ahead(self, path: str = "C:\\", bytes_ahead: int = 524288) -> dict:
        """Best-effort read-ahead hint for a given path. Windows-aware."""
        result = {"path": path, "bytes_ahead": bytes_ahead, "success": False, "method": None}
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.CreateFileW(
                    path, 0x80000000, 1, None, 3, 0x80, None,
                )
                if handle != -1:
                    try:
                        FSCTL_SET_ZERO_DATA = 0x9C040
                        kernel32.DeviceIoControl(handle, FSCTL_SET_ZERO_DATA, None, None)
                        result["success"] = True
                        result["method"] = "best_effort"
                    finally:
                        kernel32.CloseHandle(handle)
            except Exception as e:
                result["error"] = str(e)
                result["method"] = "failed"
        else:
            try:
                proc_path = f"/sys/block/{os.path.basename(path.rstrip('/'))}/queue/read_ahead_kb"
                if os.path.exists(proc_path):
                    with open(proc_path, "w") as f:
                        f.write(str(bytes_ahead // 1024))
                    result["success"] = True
                    result["method"] = "sysfs"
                else:
                    result["method"] = "not_supported"
                    result["error"] = f"Path {proc_path} not found"
            except Exception as e:
                result["error"] = str(e)
                result["method"] = "failed"
        return result

    def batch_writes(self, writes: List[Tuple[str, bytes]]) -> int:
        """Write multiple (path, data) pairs. Returns count of successful writes."""
        completed = 0
        for path, data in writes:
            try:
                parent = os.path.dirname(path)
                if parent and not os.path.exists(parent):
                    os.makedirs(parent, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                completed += 1
            except Exception as e:
                logger.error("Batch write failed for %s: %s", path, e)

        if completed:
            with self._lock:
                self._batch_history.append({
                    "timestamp": time.time(),
                    "total": len(writes),
                    "completed": completed,
                })
                if len(self._batch_history) > 1000:
                    self._batch_history = self._batch_history[-500:]

        return completed

    def get_disk_info(self) -> List[dict]:
        """Return total, used, free, and percent for each disk partition."""
        results = []
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                results.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_gb": round(usage.total / 1073741824, 2),
                    "used_gb": round(usage.used / 1073741824, 2),
                    "free_gb": round(usage.free / 1073741824, 2),
                    "percent": usage.percent,
                })
            except PermissionError:
                continue
        return results

    def should_defrag(self) -> bool:
        """Simple heuristic: return True if any drive is above 85% usage."""
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                if usage.percent > 85.0:
                    return True
            except PermissionError:
                continue
        return False


_io_optimizer: Optional[IOOptimizer] = None
_io_optimizer_lock = threading.Lock()


def get_io_optimizer() -> IOOptimizer:
    global _io_optimizer
    if _io_optimizer is None:
        with _io_optimizer_lock:
            if _io_optimizer is None:
                _io_optimizer = IOOptimizer()
    return _io_optimizer
