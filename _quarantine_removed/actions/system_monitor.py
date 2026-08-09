"""System monitor — CPU, RAM, GPU, temperature tracking with caching."""

import time
import threading
import logging

import psutil

logger = logging.getLogger("jarvis.actions.system_monitor")

_cache: dict = {}
_cache_time: float = 0
_CACHE_TTL = 2.0

_wmi_cache: float = -1.0
_wmi_time: float = 0
_WMI_TTL = 30.0


def _get_cpu_temp() -> float:
    global _wmi_cache, _wmi_time
    try:
        temps = psutil.sensors_temperatures()
        for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz", "cpu-thermal"]:
            if name in temps and temps[name]:
                return temps[name][0].current
        for entries in temps.values():
            if entries:
                return entries[0].current
    except Exception:
        pass
    now = time.time()
    if now - _wmi_time < _WMI_TTL:
        return _wmi_cache
    _wmi_time = now
    try:
        import wmi
        w = wmi.WMI(namespace="root/wmi")
        tz = w.MSAcpi_ThermalZoneTemperature()
        if tz:
            _wmi_cache = (tz[0].CurrentTemperature / 10.0) - 273.15
            return _wmi_cache
    except Exception:
        pass
    return -1.0


def _get_gpu() -> float:
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)
    except Exception:
        pass
    try:
        import ctypes
        lib = ctypes.WinDLL("nvml") if hasattr(ctypes, "WinDLL") else ctypes.CDLL("libnvidia-ml.so.1")
        lib.nvmlInit_v2()
        dev = ctypes.c_void_p()
        lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
        u = type("U", (ctypes.Structure,), {"_fields_": [("gpu", ctypes.c_uint)]})()
        lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(u))
        return float(u.gpu)
    except Exception:
        return -1.0


def get_system_status() -> dict:
    global _cache, _cache_time
    now = time.time()
    if _cache and (now - _cache_time) < _CACHE_TTL:
        return _cache

    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    boot = psutil.boot_time()
    uptime_s = time.time() - boot
    _cpu_temp = _get_cpu_temp()
    _gpu_pct = _get_gpu()

    _cache = {
        "cpu_percent": round(cpu, 1),
        "ram_percent": round(ram.percent, 1),
        "ram_used_gb": round(ram.used / 1073741824, 1),
        "ram_total_gb": round(ram.total / 1073741824, 1),
        "cpu_temp_c": round(_cpu_temp, 1) if _cpu_temp > 0 else None,
        "gpu_percent": round(_gpu_pct, 1) if _gpu_pct >= 0 else None,
        "uptime": f"{int(uptime_s // 3600)}h {int((uptime_s % 3600) // 60)}m",
        "process_count": len(psutil.pids()),
    }
    _cache_time = now
    return _cache


class SystemMonitor:
    def __init__(self, thresholds: dict | None = None):
        self.thresholds = {"cpu": 90.0, "ram": 90.0, "temp": 85.0, "gpu": 95.0, **(thresholds or {})}
        self._last_alert: dict[str, float] = {}
        self._cpu_streak = 0

    def check(self) -> str | None:
        status = get_system_status()
        cpu = status["cpu_percent"]
        ram = status["ram_percent"]
        temp = status.get("cpu_temp_c") or 0
        gpu = status.get("gpu_percent") or 0
        now = time.monotonic()
        alerts = []

        if cpu >= self.thresholds["cpu"]:
            self._cpu_streak += 1
            if self._cpu_streak >= 3 and (now - self._last_alert.get("cpu", 0)) > 300:
                alerts.append(f"[SYSTEM_ALERT] CPU at {cpu:.0f}% — close heavy apps.")
                self._last_alert["cpu"] = now
                self._cpu_streak = 0
        else:
            self._cpu_streak = 0

        if ram >= self.thresholds["ram"] and (now - self._last_alert.get("ram", 0)) > 300:
            alerts.append(f"[SYSTEM_ALERT] RAM at {ram:.0f}% — free some memory.")
            self._last_alert["ram"] = now

        if temp > 0 and temp >= self.thresholds["temp"] and (now - self._last_alert.get("temp", 0)) > 300:
            alerts.append(f"[SYSTEM_ALERT] CPU temp {temp:.0f}C — check cooling.")
            self._last_alert["temp"] = now

        if gpu >= 0 and gpu >= self.thresholds["gpu"] and (now - self._last_alert.get("gpu", 0)) > 300:
            alerts.append(f"[SYSTEM_ALERT] GPU at {gpu:.0f}%.")
            self._last_alert["gpu"] = now

        return " ".join(alerts) if alerts else None
