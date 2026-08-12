"""Process Priority Profiles — Dynamically switch process priorities.

Voice capture → High | Background indexing → Below Normal | Downloads → Idle
"""
import logging
import os
import platform
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("os_optimization.process_priority")


class PriorityLevel(Enum):
    """Windows process priority classes."""
    IDLE = "idle"
    BELOW_NORMAL = "below_normal"
    NORMAL = "normal"
    ABOVE_NORMAL = "above_normal"
    HIGH = "high"
    REALTIME = "realtime"


# Map our priority levels to OS constants (Windows)
PRIORITY_MAP = {
    PriorityLevel.IDLE: 64,        # IDLE_PRIORITY_CLASS
    PriorityLevel.BELOW_NORMAL: 16384,  # BELOW_NORMAL_PRIORITY_CLASS
    PriorityLevel.NORMAL: 32,      # NORMAL_PRIORITY_CLASS
    PriorityLevel.ABOVE_NORMAL: 32768,  # ABOVE_NORMAL_PRIORITY_CLASS
    PriorityLevel.HIGH: 128,       # HIGH_PRIORITY_CLASS
    PriorityLevel.REALTIME: 256,   # REALTIME_PRIORITY_CLASS
}

# Task → priority mapping
TASK_PRIORITIES = {
    "voice_capture": PriorityLevel.HIGH,
    "audio_playback": PriorityLevel.HIGH,
    "stt": PriorityLevel.ABOVE_NORMAL,
    "tts": PriorityLevel.ABOVE_NORMAL,
    "llm_inference": PriorityLevel.ABOVE_NORMAL,
    "tool_execution": PriorityLevel.NORMAL,
    "vision": PriorityLevel.NORMAL,
    "context_update": PriorityLevel.NORMAL,
    "background_indexing": PriorityLevel.BELOW_NORMAL,
    "model_download": PriorityLevel.IDLE,
    "telemetry": PriorityLevel.IDLE,
    "cache_cleanup": PriorityLevel.IDLE,
}


@dataclass
class PriorityProfile:
    """A named priority configuration."""
    name: str
    task_priorities: dict[str, PriorityLevel] = None

    def __post_init__(self):
        if self.task_priorities is None:
            self.task_priorities = dict(TASK_PRIORITIES)


class ProcessPriorityManager:
    """Dynamically manage process priority based on active tasks."""

    def __init__(self):
        self._current_priority = PriorityLevel.NORMAL
        self._active_tasks: dict[str, PriorityLevel] = {}
        self._lock = threading.Lock()
        self._switch_count = 0
        self._profiles: dict[str, PriorityProfile] = {
            "default": PriorityProfile("default"),
            "voice_active": PriorityProfile("voice_active", {
                **TASK_PRIORITIES,
                "voice_capture": PriorityLevel.REALTIME,
            }),
            "low_power": PriorityProfile("low_power", {
                task: PriorityLevel.BELOW_NORMAL for task in TASK_PRIORITIES
            }),
        }

    def set_task_priority(self, task_name: str, priority: PriorityLevel) -> None:
        with self._lock:
            self._active_tasks[task_name] = priority
            self._apply_highest_priority()

    def clear_task(self, task_name: str) -> None:
        with self._lock:
            self._active_tasks.pop(task_name, None)
            self._apply_highest_priority()

    def _apply_highest_priority(self) -> None:
        if not self._active_tasks:
            new_priority = PriorityLevel.NORMAL
        else:
            new_priority = max(self._active_tasks.values(), key=lambda p: PRIORITY_MAP.get(p, 0))

        if new_priority != self._current_priority:
            self._current_priority = new_priority
            self._switch_count += 1
            self._apply_os_priority(new_priority)

    def _apply_os_priority(self, priority: PriorityLevel) -> None:
        try:
            if platform.system() == "Windows":
                import ctypes
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                win_priority = PRIORITY_MAP.get(priority, PRIORITY_MAP[PriorityLevel.NORMAL])
                ctypes.windll.kernel32.SetPriorityClass(handle, win_priority)
            else:
                nice_map = {
                    PriorityLevel.IDLE: 19,
                    PriorityLevel.BELOW_NORMAL: 10,
                    PriorityLevel.NORMAL: 0,
                    PriorityLevel.ABOVE_NORMAL: -5,
                    PriorityLevel.HIGH: -10,
                }
                os.nice(nice_map.get(priority, 0))
            logger.debug("Process priority → %s", priority.name)
        except Exception as e:
            logger.debug("Priority set failed: %s", e)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "current_priority": self._current_priority.name,
                "active_tasks": dict(self._active_tasks),
                "switch_count": self._switch_count,
                "profiles": list(self._profiles.keys()),
            }


_priority_instance: ProcessPriorityManager | None = None


def get_process_priority_manager() -> ProcessPriorityManager:
    global _priority_instance
    if _priority_instance is None:
        _priority_instance = ProcessPriorityManager()
    return _priority_instance
