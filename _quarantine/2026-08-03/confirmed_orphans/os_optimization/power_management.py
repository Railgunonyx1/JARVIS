"""Adaptive Power Management — Optimize performance vs battery.

Plugged in → maximize performance
On battery → reduce background work, lower model size
"""
import logging
import platform
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("os_optimization.power_management")


class PowerState(Enum):
    AC_POWER = "ac_power"
    BATTERY = "battery"
    LOW_BATTERY = "low_battery"
    UNKNOWN = "unknown"


class PerformanceMode(Enum):
    MAX_PERFORMANCE = "max_performance"
    BALANCED = "balanced"
    POWER_SAVER = "power_saver"
    ULTRA_SAVER = "ultra_saver"


@dataclass
class PowerProfile:
    """Configuration for a power mode."""
    mode: PerformanceMode
    max_model_size: str = "large"
    background_indexing: bool = True
    vision_enabled: bool = True
    prefetch_enabled: bool = True
    max_workers: int = 8
    description: str = ""


POWER_PROFILES = {
    PerformanceMode.MAX_PERFORMANCE: PowerProfile(
        PerformanceMode.MAX_PERFORMANCE,
        max_model_size="large", background_indexing=True,
        vision_enabled=True, prefetch_enabled=True, max_workers=8,
        description="Full performance, all features enabled",
    ),
    PerformanceMode.BALANCED: PowerProfile(
        PerformanceMode.BALANCED,
        max_model_size="medium", background_indexing=True,
        vision_enabled=True, prefetch_enabled=True, max_workers=6,
        description="Balanced performance and power",
    ),
    PerformanceMode.POWER_SAVER: PowerProfile(
        PerformanceMode.POWER_SAVER,
        max_model_size="small", background_indexing=False,
        vision_enabled=False, prefetch_enabled=False, max_workers=4,
        description="Reduced performance, extended battery",
    ),
    PerformanceMode.ULTRA_SAVER: PowerProfile(
        PerformanceMode.ULTRA_SAVER,
        max_model_size="tiny", background_indexing=False,
        vision_enabled=False, prefetch_enabled=False, max_workers=2,
        description="Minimal power, voice only",
    ),
}


class PowerManager:
    """Adaptive power management based on power source and battery level."""

    def __init__(self):
        self._power_state = PowerState.UNKNOWN
        self._current_mode = PerformanceMode.BALANCED
        self._battery_percent = 100
        self._lock = threading.Lock()
        self._mode_history: list = []
        self._check_count = 0

    def detect_power_state(self) -> PowerState:
        """Detect current power state from OS."""
        self._check_count += 1

        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["WMIC", "Path", "Win32_Battery", "Get", "BatteryStatus,EstimatedChargeRemaining"],
                    capture_output=True, text=True, timeout=5
                )
                if "BatteryStatus" in result.stdout:
                    lines = result.stdout.strip().split("\n")
                    for line in lines[1:]:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            status = int(parts[0])
                            self._battery_percent = int(parts[1])
                            if status == 2:  # Discharging
                                self._power_state = PowerState.BATTERY
                            else:
                                self._power_state = PowerState.AC_POWER
                            break
                else:
                    self._power_state = PowerState.AC_POWER
            else:
                # Linux fallback
                try:
                    with open("/sys/class/power_supply/BAC/online") as f:
                        online = f.read().strip()
                        self._power_state = PowerState.AC_POWER if online == "1" else PowerState.BATTERY
                except FileNotFoundError:
                    self._power_state = PowerState.AC_POWER

        except Exception:
            self._power_state = PowerState.AC_POWER

        # Auto-select mode based on power state
        self._auto_select_mode()
        return self._power_state

    def _auto_select_mode(self) -> None:
        if self._power_state == PowerState.AC_POWER:
            new_mode = PerformanceMode.MAX_PERFORMANCE
        elif self._battery_percent < 20:
            new_mode = PerformanceMode.ULTRA_SAVER
        elif self._battery_percent < 50:
            new_mode = PerformanceMode.POWER_SAVER
        else:
            new_mode = PerformanceMode.BALANCED

        if new_mode != self._current_mode:
            self.set_mode(new_mode)

    def set_mode(self, mode: PerformanceMode) -> None:
        with self._lock:
            old = self._current_mode
            self._current_mode = mode
            self._mode_history.append({
                "from": old.value, "to": mode.value, "ts": time.time()
            })
            if len(self._mode_history) > 50:
                self._mode_history = self._mode_history[-50:]
        logger.info("Power mode: %s → %s", old.value, mode.value)

    def get_profile(self) -> PowerProfile:
        return POWER_PROFILES.get(self._current_mode, POWER_PROFILES[PerformanceMode.BALANCED])

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "power_state": self._power_state.value,
                "battery_percent": self._battery_percent,
                "current_mode": self._current_mode.value,
                "check_count": self._check_count,
                "recent_changes": self._mode_history[-5:],
            }


_power_manager_instance: PowerManager | None = None


def get_power_manager() -> PowerManager:
    global _power_manager_instance
    if _power_manager_instance is None:
        _power_manager_instance = PowerManager()
    return _power_manager_instance
