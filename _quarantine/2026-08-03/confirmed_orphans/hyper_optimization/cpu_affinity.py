"""JARVIS MK-X Hyper-Optimization Engine — CPU affinity management."""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from typing import Dict, List, Optional

logger = logging.getLogger("jarvis.hyper_opt.cpu_affinity")

_WORKLOAD_PREFERENCES: Dict[str, dict] = {
    "audio": {
        "preferred_cores": [0, 1],
        "priority": "high",
        "description": "Low-latency audio processing, prefers isolated cores",
    },
    "inference": {
        "preferred_cores": [2, 3],
        "priority": "high",
        "description": "ML inference, benefits from dedicated cores",
    },
    "vision": {
        "preferred_cores": [3, 4],
        "priority": "medium",
        "description": "Vision pipeline, benefits from high-throughput cores",
    },
    "io": {
        "preferred_cores": [0],
        "priority": "low",
        "description": "I/O-bound tasks, can share cores",
    },
    "general": {
        "preferred_cores": list(range(4)),
        "priority": "medium",
        "description": "General-purpose workloads",
    },
}


class CPUAffinityManager:
    """Pin threads to CPU cores for better cache locality."""

    def __init__(self) -> None:
        self._assignments: Dict[str, List[int]] = {}
        self._core_usage: Dict[int, int] = {}
        self._cpu_count: int = os.cpu_count() or 4
        self._lock = threading.RLock()
        self._available: bool = self._check_affinity_support()
        self._thread_handles: Dict[str, int] = {}
        for core_id in range(self._cpu_count):
            self._core_usage[core_id] = 0
        logger.debug(
            "CPUAffinityManager initialized: cpu_count=%d, affinity_available=%s",
            self._cpu_count,
            self._available,
        )

    @staticmethod
    def _check_affinity_support() -> bool:
        """Check if the OS supports thread affinity setting."""
        try:
            if os.name == "nt":
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetCurrentThread()
                return handle is not None
            return hasattr(os, "sched_setaffinity")
        except Exception:
            return False

    def set_affinity(self, thread_name: str, core_ids: List[int]) -> bool:
        """Pin a named thread to specific cores. Returns True on success."""
        with self._lock:
            if not core_ids:
                logger.warning("Empty core_ids for thread '%s'", thread_name)
                return False
            validated = [c for c in core_ids if 0 <= c < self._cpu_count]
            if not validated:
                logger.warning(
                    "All core_ids out of range for thread '%s' (cpu_count=%d)",
                    thread_name,
                    self._cpu_count,
                )
                return False
            old_cores = self._assignments.get(thread_name, [])
            for c in old_cores:
                self._core_usage[c] = max(0, self._core_usage.get(c, 1) - 1)
            self._assignments[thread_name] = validated
            for c in validated:
                self._core_usage[c] = self._core_usage.get(c, 0) + 1
            success = self._apply_affinity(validated)
            logger.debug(
                "Thread '%s' assigned to cores %s: %s",
                thread_name,
                validated,
                "ok" if success else "apply failed",
            )
            return success

    def _apply_affinity(self, core_ids: List[int]) -> bool:
        """Apply CPU affinity to the current thread using OS APIs."""
        try:
            if os.name == "nt":
                mask = 0
                for c in core_ids:
                    mask |= 1 << c
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetCurrentThread()
                result = kernel32.SetThreadAffinityMask(handle, ctypes.c_size_t(mask))
                return result != 0
            elif hasattr(os, "sched_setaffinity"):
                os.sched_setaffinity(0, set(core_ids))
                return True
        except Exception:
            logger.exception("Failed to apply CPU affinity")
        return False

    def get_affinity(self, thread_name: str) -> List[int]:
        """Get current core assignment for a thread."""
        with self._lock:
            return list(self._assignments.get(thread_name, []))

    def get_cpu_info(self) -> dict:
        """Returns cpu_count, physical_cores, per_core_usage."""
        with self._lock:
            physical_cores = self._detect_physical_cores()
            return {
                "cpu_count": self._cpu_count,
                "physical_cores": physical_cores,
                "affinity_available": self._available,
                "per_core_usage": dict(self._core_usage),
                "assigned_threads": len(self._assignments),
            }

    @staticmethod
    def _detect_physical_cores() -> int:
        """Best-effort detection of physical core count."""
        try:
            if os.name == "nt":
                core_count = os.cpu_count()
                return core_count // 2 if core_count else 2
            return os.cpu_count() or 4
        except Exception:
            return os.cpu_count() or 4

    def suggest_assignment(self, workload_type: str) -> List[int]:
        """Suggest core assignment for workload type."""
        with self._lock:
            prefs = _WORKLOAD_PREFERENCES.get(workload_type)
            if prefs is None:
                logger.debug("Unknown workload type '%s', using general", workload_type)
                prefs = _WORKLOAD_PREFERENCES["general"]
            preferred = prefs["preferred_cores"]
            available = [
                c
                for c in preferred
                if c < self._cpu_count and self._core_usage.get(c, 0) < 2
            ]
            if not available:
                available = [
                    c
                    for c in range(self._cpu_count)
                    if self._core_usage.get(c, 0) < 2
                ]
            if not available:
                available = [min(preferred[0], self._cpu_count - 1)]
            logger.debug(
                "Suggested cores for '%s': %s", workload_type, available
            )
            return available

    def auto_assign(self) -> Dict[str, List[int]]:
        """Automatically assign JARVIS threads to cores. Returns assignments."""
        with self._lock:
            jarvis_threads = ["jarvis_audio", "jarvis_inference", "jarvis_vision", "jarvis_io", "jarvis_general"]
            workload_map = {
                "jarvis_audio": "audio",
                "jarvis_inference": "inference",
                "jarvis_vision": "vision",
                "jarvis_io": "io",
                "jarvis_general": "general",
            }
            assignments: Dict[str, List[int]] = {}
            for thread_name in jarvis_threads:
                workload = workload_map.get(thread_name, "general")
                cores = self.suggest_assignment(workload)
                self.set_affinity(thread_name, cores)
                assignments[thread_name] = cores
            logger.info("Auto-assigned %d threads to cores", len(assignments))
            return assignments

    def get_load_balance(self) -> dict:
        """Returns per-core load and load imbalance score."""
        with self._lock:
            total_threads = sum(self._core_usage.values())
            ideal = total_threads / self._cpu_count if self._cpu_count > 0 else 0
            imbalance = 0.0
            for core_id in range(self._cpu_count):
                usage = self._core_usage.get(core_id, 0)
                imbalance += abs(usage - ideal)
            if self._cpu_count > 0:
                imbalance /= self._cpu_count
            return {
                "per_core_usage": dict(self._core_usage),
                "total_threads": total_threads,
                "ideal_per_core": ideal,
                "load_imbalance_score": round(imbalance, 4),
            }

    def get_recommended_layout(self) -> dict:
        """Returns recommended thread-to-core mapping."""
        with self._lock:
            layout = {}
            for workload_type in _WORKLOAD_PREFERENCES:
                cores = self.suggest_assignment(workload_type)
                layout[workload_type] = {
                    "recommended_cores": cores,
                    "preferences": _WORKLOAD_PREFERENCES[workload_type],
                }
            return layout

    def pin_current_thread(self, core_id: int) -> bool:
        """Pin the current thread to a specific core."""
        if core_id < 0 or core_id >= self._cpu_count:
            logger.warning("Invalid core_id %d (cpu_count=%d)", core_id, self._cpu_count)
            return False
        return self._apply_affinity([core_id])

    def remove_assignment(self, thread_name: str) -> bool:
        """Remove a thread assignment. Returns True if found."""
        with self._lock:
            old_cores = self._assignments.pop(thread_name, None)
            if old_cores is None:
                return False
            for c in old_cores:
                self._core_usage[c] = max(0, self._core_usage.get(c, 1) - 1)
            logger.debug("Removed assignment for thread '%s'", thread_name)
            return True


_instance: Optional[CPUAffinityManager] = None
_instance_lock = threading.RLock()


def get_cpu_affinity_manager() -> CPUAffinityManager:
    """Singleton accessor for CPUAffinityManager."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CPUAffinityManager()
                logger.info("CPUAffinityManager singleton created")
    return _instance
