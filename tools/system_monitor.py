"""System monitor tool — read-only host status via psutil.

Recycled from the quarantined ``actions/system_monitor.py`` into the v2 tool
contract. Read-only and dependency-light (psutil is already required).
"""

from __future__ import annotations

import time
from typing import Any

import psutil

from tools.schema import ToolResult

_cache: dict[str, Any] = {}
_cache_time: float = 0.0
_CACHE_TTL = 2.0


def _get_cpu_temp() -> float:
    try:
        temps = psutil.sensors_temperatures()
        for name in ("coretemp", "k10temp", "cpu_thermal", "acpitz", "cpu-thermal"):
            if name in temps and temps[name]:
                return temps[name][0].current
        for entries in temps.values():
            if entries:
                return entries[0].current
    except Exception:
        pass
    return -1.0


def _get_gpu() -> float:
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        return float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
    except Exception:
        return -1.0


def get_system_status() -> dict[str, Any]:
    """Current CPU/RAM/uptime snapshot (cached 2s)."""
    global _cache, _cache_time
    now = time.time()
    if _cache and (now - _cache_time) < _CACHE_TTL:
        return _cache

    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    uptime_s = time.time() - psutil.boot_time()
    temp = _get_cpu_temp()
    gpu = _get_gpu()

    _cache = {
        "cpu_percent": round(cpu, 1),
        "ram_percent": round(ram.percent, 1),
        "ram_used_gb": round(ram.used / 1073741824, 1),
        "ram_total_gb": round(ram.total / 1073741824, 1),
        "cpu_temp_c": round(temp, 1) if temp > 0 else None,
        "gpu_percent": round(gpu, 1) if gpu >= 0 else None,
        "uptime": f"{int(uptime_s // 3600)}h {int((uptime_s % 3600) // 60)}m",
        "process_count": len(psutil.pids()),
    }
    _cache_time = now
    return _cache


def system_status(args: dict[str, Any]) -> ToolResult:
    """Report read-only host health: CPU, RAM, uptime, process count."""
    status = get_system_status()
    lines = [
        f"CPU:   {status['cpu_percent']}%",
        f"RAM:   {status['ram_percent']}% ({status['ram_used_gb']} / {status['ram_total_gb']} GB)",
        f"Uptime: {status['uptime']}",
        f"Processes: {status['process_count']}",
    ]
    if status["cpu_temp_c"] is not None:
        lines.append(f"CPU temp: {status['cpu_temp_c']}C")
    if status["gpu_percent"] is not None:
        lines.append(f"GPU: {status['gpu_percent']}%")
    return ToolResult(success=True, output="\n".join(lines), metadata=status)
