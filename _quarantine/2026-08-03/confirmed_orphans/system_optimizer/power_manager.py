"""Power Manager — battery monitoring, power plan control, and thermal estimation."""

import sys
import time
import logging
import threading
import subprocess
from typing import Dict, List, Optional

import psutil

logger = logging.getLogger("jarvis.system_optimizer.power_manager")

_THERMAL_WINDOW = 30


class PowerManager:
    """Monitors battery state, controls Windows power plans, and estimates thermal levels."""

    def __init__(self) -> None:
        self._cpu_history: List[float] = []
        self._lock = threading.Lock()

    def get_power_state(self) -> dict:
        """Return battery percentage, plugged-in status, power plan, and battery-saver state."""
        result: dict = {
            "battery_percent": None,
            "plugged_in": True,
            "power_plan": "unknown",
            "is_battery_saver": False,
        }
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                result["battery_percent"] = battery.percent
                result["plugged_in"] = battery.power_plugged
                result["is_battery_saver"] = battery.percent < 20 and not battery.power_plugged
        except Exception:
            pass

        if sys.platform == "win32":
            result["power_plan"] = self._get_windows_power_plan()
        else:
            result["power_plan"] = "linux_default"

        return result

    def set_power_plan(self, plan: str) -> dict:
        """Set the Windows power plan. Accepts 'high', 'balanced', or 'power_saver'."""
        plan_map = {
            "high": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
            "balanced": "381b4222-f694-41df-bd58-80ba148808ac",
            "power_saver": "a1841308-3541-4fab-bc81-f71556f20b4b",
        }
        plan_lower = plan.lower()
        if plan_lower not in plan_map:
            return {"success": False, "error": f"Unknown plan: {plan!r}. Use 'high', 'balanced', or 'power_saver'."}

        if sys.platform != "win32":
            return {"success": False, "error": "Power plan control only supported on Windows"}

        try:
            guid = plan_map[plan_lower]
            result = subprocess.run(
                ["powercfg", "/setactive", guid],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("Power plan set to %s", plan_lower)
                return {"success": True, "plan": plan_lower, "guid": guid}
            else:
                return {"success": False, "error": result.stderr.strip()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def should_reduce_workload(self) -> bool:
        """Return True if on battery with less than 30% charge remaining."""
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return False
            return not battery.power_plugged and battery.percent < 30
        except Exception:
            return False

    def get_thermal_state(self) -> dict:
        """Estimate thermal level from recent CPU usage history."""
        try:
            current_cpu = psutil.cpu_percent(interval=0.1)
        except Exception:
            current_cpu = 0.0

        with self._lock:
            self._cpu_history.append(current_cpu)
            if len(self._cpu_history) > _THERMAL_WINDOW:
                self._cpu_history = self._cpu_history[-_THERMAL_WINDOW:]
            history = list(self._cpu_history)

        avg_cpu = sum(history) / len(history) if history else 0.0
        trend = 0.0
        if len(history) >= 5:
            recent = history[-5:]
            trend = (recent[-1] - recent[0]) / max(recent[0], 1.0)

        if avg_cpu > 90 or (avg_cpu > 70 and trend > 0.1):
            level = "critical"
        elif avg_cpu > 70 or trend > 0.05:
            level = "elevated"
        elif avg_cpu > 40:
            level = "warm"
        else:
            level = "normal"

        return {
            "estimated_thermal_level": level,
            "avg_cpu_usage": round(avg_cpu, 1),
            "cpu_trend": round(trend, 3),
            "history_points": len(history),
        }

    def _get_windows_power_plan(self) -> str:
        try:
            result = subprocess.run(
                ["powercfg", "/getactivescheme"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) >= 3:
                    guid = parts[1]
                    plan_names = {
                        "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "high",
                        "381b4222-f694-41df-bd58-80ba148808ac": "balanced",
                        "a1841308-3541-4fab-bc81-f71556f20b4b": "power_saver",
                    }
                    return plan_names.get(guid, guid)
        except Exception:
            pass
        return "unknown"


_power_manager: Optional[PowerManager] = None
_power_manager_lock = threading.Lock()


def get_power_manager() -> PowerManager:
    global _power_manager
    if _power_manager is None:
        with _power_manager_lock:
            if _power_manager is None:
                _power_manager = PowerManager()
    return _power_manager
