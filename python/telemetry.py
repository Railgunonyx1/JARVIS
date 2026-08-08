"""JARVIS MK-X — System Telemetry Bridge.

Provides real-time CPU, RAM, GPU, VRAM, temperature, disk, battery, and network stats.
Can run standalone (uvicorn telemetry:app --port 8000) or be imported by the Flask backend.
"""

import psutil

try:
    import GPUtil
    _gputil_ok = True
except ImportError:
    _gputil_ok = False


def get_system_stats() -> dict:
    """Return current system telemetry."""
    gpu_load = 0.0
    gpu_temp = 0
    vram_used = 0.0

    if _gputil_ok:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                gpu_load = gpu.load * 100
                gpu_temp = gpu.temperature
                vram_used = round(gpu.memoryUsed / 1024, 1)
        except Exception:
            pass

    battery = "N/A"
    try:
        bat = psutil.sensors_battery()
        if bat:
            battery = f"{bat.percent}%"
    except Exception:
        pass

    disk = psutil.disk_usage("/")

    net = psutil.net_io_counters()

    return {
        "cpu": psutil.cpu_percent(interval=0.1),
        "ram": psutil.virtual_memory().percent,
        "gpu": round(gpu_load, 1),
        "vram": vram_used,
        "temperature": gpu_temp,
        "disk": round(disk.percent, 1),
        "battery": battery,
        "network": round(net.bytes_sent / 1024 / 1024, 2),
    }


# Standalone mode: uvicorn telemetry:app --port 8000
try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="JARVIS Telemetry")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/system")
    def system():
        return get_system_stats()

except ImportError:
    pass
