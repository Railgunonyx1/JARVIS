"""Resource Governor — monitors CPU/RAM and provides throttling signals.
Used by other modules to degrade gracefully under load."""

import logging
import threading
import time

from core.config import Config

logger = logging.getLogger("jarvis.resource_governor")

try:
    import psutil
    _psutil_ok = True
except ImportError:
    _psutil_ok = False


class ResourceGovernor:
    """Monitors system resources and provides throttle signals."""

    def __init__(self, check_interval: float = 5.0):
        self._check_interval = check_interval
        self._cpu_percent: float = 0.0
        self._ram_percent: float = 0.0
        self._ram_used_gb: float = 0.0
        self._ram_total_gb: float = 0.0
        self._throttle_level: int = 0  # 0=normal, 1=reduce, 2=aggressive
        self._running = False
        self._thread: threading.Thread | None = None

        # Thresholds — read from config TOML with sensible defaults
        cfg = Config.instance().get("models", "resource_governor", {})
        self.cpu_high = cfg.get("cpu_high", 85.0)
        self.cpu_reduce = cfg.get("cpu_reduce", 70.0)
        self.ram_high = cfg.get("ram_high", 85.0)

    def start(self):
        """Start background monitoring."""
        if self._running:
            return
        self._running = True
        # Warm-up call so first real check returns accurate CPU%
        if _psutil_ok:
            psutil.cpu_percent(interval=None)
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Resource governor started (interval=%.0fs)", self._check_interval)

    def stop(self):
        self._running = False

    def _monitor_loop(self):
        while self._running:
            try:
                self._check()
            except Exception:
                pass
            time.sleep(self._check_interval)

    def _check(self):
        if not _psutil_ok:
            return
        self._cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        self._ram_percent = mem.percent
        self._ram_used_gb = mem.used / (1024 ** 3)
        self._ram_total_gb = mem.total / (1024 ** 3)

        # Determine throttle level
        if self._cpu_percent > self.cpu_high or self._ram_percent > self.ram_high:
            self._throttle_level = 2
        elif self._cpu_percent > self.cpu_reduce:
            self._throttle_level = 1
        else:
            self._throttle_level = 0

    @property
    def cpu_percent(self) -> float:
        return self._cpu_percent

    @property
    def ram_percent(self) -> float:
        return self._ram_percent

    @property
    def throttle_level(self) -> int:
        return self._throttle_level

    @property
    def should_skip_animations(self) -> bool:
        return self._throttle_level >= 1

    @property
    def should_reduce_tts(self) -> bool:
        return self._throttle_level >= 2

    @property
    def status(self) -> dict:
        return {
            "cpu_percent": round(self._cpu_percent, 1),
            "ram_percent": round(self._ram_percent, 1),
            "ram_used_gb": round(self._ram_used_gb, 1),
            "ram_total_gb": round(self._ram_total_gb, 1),
            "throttle_level": self._throttle_level,
        }


# Singleton
_governor: ResourceGovernor | None = None


def get_governor() -> ResourceGovernor:
    global _governor
    if _governor is None:
        _governor = ResourceGovernor()
    return _governor
