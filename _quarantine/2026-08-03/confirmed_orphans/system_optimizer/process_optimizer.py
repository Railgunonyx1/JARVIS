"""Process Optimizer — JARVIS process priority, affinity, memory, and CPU management."""

import os
import sys
import gc
import time
import ctypes
import logging
import threading
from typing import List, Optional

import psutil

logger = logging.getLogger("jarvis.system_optimizer.process_optimizer")

_BELOW_NORMAL_PRIORITY = 16384  # BELOW_NORMAL_PRIORITY_CLASS on Windows


class ProcessOptimizer:
    """Manages JARVIS process priority, CPU affinity, and memory defragmentation."""

    def __init__(self) -> None:
        self._process = psutil.Process(os.getpid())
        self._lock = threading.Lock()

    def optimize_priority(self) -> dict:
        """Set the JARVIS process to BELOW_NORMAL_PRIORITY_CLASS on Windows, best-effort."""
        result = {"previous_priority": None, "new_priority": None, "success": False}
        try:
            if sys.platform == "win32":
                current = self._get_windows_priority()
                result["previous_priority"] = current
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                ctypes.windll.kernel32.SetPriorityClass(handle, _BELOW_NORMAL_PRIORITY)
                new = self._get_windows_priority()
                result["new_priority"] = new
                result["success"] = True
                logger.info("Process priority set to %s", new)
            else:
                self._process.nice(10)
                result["new_priority"] = "below_normal"
                result["success"] = True
                logger.info("Process nice value set to 10")
        except Exception as e:
            logger.error("Failed to set priority: %s", e)
            result["error"] = str(e)
        return result

    def get_process_info(self) -> dict:
        """Return pid, priority, cpu_affinity, memory_info, and thread_count."""
        try:
            mem = self._process.memory_info()
            return {
                "pid": os.getpid(),
                "priority": self._get_priority(),
                "cpu_affinity": self._process.cpu_affinity(),
                "memory_rss_mb": round(mem.rss / 1048576, 2),
                "memory_vms_mb": round(mem.vms / 1048576, 2),
                "thread_count": self._process.num_threads(),
                "cpu_percent": self._process.cpu_percent(interval=None),
                "uptime_seconds": time_since(self._process.create_time()),
            }
        except Exception as e:
            logger.error("Failed to get process info: %s", e)
            return {"error": str(e)}

    def set_cpu_affinity(self, cores: List[int]) -> dict:
        """Set CPU core affinity for the JARVIS process."""
        result = {"cores": cores, "success": False}
        try:
            max_cores = psutil.cpu_count(logical=True)
            valid = [c for c in cores if 0 <= c < max_cores]
            if not valid:
                result["error"] = f"No valid cores in {cores} (max: {max_cores - 1})"
                return result
            self._process.cpu_affinity(valid)
            result["success"] = True
            result["actual"] = self._process.cpu_affinity()
            logger.info("CPU affinity set to cores %s", valid)
        except Exception as e:
            result["error"] = str(e)
            logger.error("Failed to set CPU affinity: %s", e)
        return result

    def get_cpu_info(self) -> dict:
        """Return core_count, physical_cores, and per-core usage percentages."""
        try:
            per_core = psutil.cpu_percent(interval=0.1, percpu=True)
            return {
                "logical_cores": psutil.cpu_count(logical=True),
                "physical_cores": psutil.cpu_count(logical=False),
                "usage_per_core": per_core,
                "overall_usage": psutil.cpu_percent(interval=None),
                "frequency_mhz": _get_cpu_freq(),
            }
        except Exception as e:
            return {"error": str(e)}

    def defragment_memory(self) -> dict:
        """Force Python garbage collection and report freed objects."""
        before = len(gc.get_objects())
        collected = gc.collect()
        after = len(gc.get_objects())
        freed = before - after
        result = {
            "collected_cycles": collected,
            "objects_before": before,
            "objects_after": after,
            "objects_freed": freed,
        }
        logger.info("GC collected %d cycles, freed %d objects", collected, freed)
        return result

    def _get_windows_priority(self) -> Optional[str]:
        if sys.platform != "win32":
            return self._process.nice()
        try:
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            priority_class = ctypes.windll.kernel32.GetPriorityClass(handle)
            names = {
                64: "realtime", 128: "high", 32768: "above_normal",
                32: "normal", 16384: "below_normal", 16: "idle",
                256: "normal", 384: "below_normal",
            }
            return names.get(priority_class, f"unknown({priority_class})")
        except Exception:
            return "unknown"

    def _get_priority(self) -> str:
        if sys.platform == "win32":
            return self._get_windows_priority()
        try:
            return str(self._process.nice())
        except Exception:
            return "unknown"


def _get_cpu_freq() -> Optional[float]:
    try:
        freq = psutil.cpu_freq()
        if freq:
            return round(freq.current, 1)
    except Exception:
        pass
    return None


def time_since(timestamp: float) -> float:
    return round(time.time() - timestamp, 1)


_process_optimizer: Optional[ProcessOptimizer] = None
_process_optimizer_lock = threading.Lock()


def get_process_optimizer() -> ProcessOptimizer:
    global _process_optimizer
    if _process_optimizer is None:
        with _process_optimizer_lock:
            if _process_optimizer is None:
                _process_optimizer = ProcessOptimizer()
    return _process_optimizer
