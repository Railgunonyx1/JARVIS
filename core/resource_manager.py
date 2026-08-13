"""ResourceManager - Unified system resource monitoring, thread pooling, and pressure detection.

Absorbs ResourceGovernor (CPU/RAM throttle), GracefulDegradation monitor,
resource_predictor, and CPUAffinityManager into one service-oriented component.
"""

import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger("jarvis.core.resource_manager")

try:
    import psutil
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False


class PressureLevel(IntEnum):
    NONE = 0
    MILD = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class CpuSnapshot:
    percent: float = 0.0
    per_core: list[float] = field(default_factory=list)
    count: int = 0
    frequency_mhz: float = 0.0
    temperature_c: float | None = None


@dataclass
class MemorySnapshot:
    percent: float = 0.0
    used_gb: float = 0.0
    total_gb: float = 0.0
    swap_percent: float = 0.0
    swap_used_gb: float = 0.0
    swap_total_gb: float = 0.0


@dataclass
class DiskSnapshot:
    percent: float = 0.0
    free_gb: float = 0.0
    total_gb: float = 0.0
    read_mbs: float = 0.0
    write_mbs: float = 0.0


@dataclass
class GpuSnapshot:
    available: bool = False
    name: str = ""
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    memory_percent: float = 0.0
    utilization_percent: float = 0.0
    temperature_c: float | None = None


@dataclass
class NetworkSnapshot:
    bytes_sent: int = 0
    bytes_recv: int = 0
    is_connected: bool = True


@dataclass
class BatterySnapshot:
    available: bool = False
    percent: float = 0.0
    is_charging: bool = False
    time_left_sec: float | None = None


@dataclass
class ResourceQuota:
    max_cpu_percent: float = 90.0
    max_ram_percent: float = 85.0
    max_threads: int = 4
    max_concurrent_llm: int = 2
    max_concurrent_tts: int = 1
    # Pressure thresholds (percent). Configurable per deployment.
    pressure_critical: float = 95.0
    pressure_high: float = 90.0
    pressure_mild_cpu: float = 70.0
    pressure_mild_ram: float = 75.0

    @classmethod
    def from_config(cls, config: dict | None = None) -> "ResourceQuota":
        """Build a quota from config section, falling back to defaults."""
        cfg = config or {}
        return cls(
            max_cpu_percent=float(cfg.get("max_cpu_percent", 90.0)),
            max_ram_percent=float(cfg.get("max_ram_percent", 85.0)),
            max_threads=int(cfg.get("max_threads", 4)),
            max_concurrent_llm=int(cfg.get("max_concurrent_llm", 2)),
            max_concurrent_tts=int(cfg.get("max_concurrent_tts", 1)),
            pressure_critical=float(cfg.get("pressure_critical", 95.0)),
            pressure_high=float(cfg.get("pressure_high", 90.0)),
            pressure_mild_cpu=float(cfg.get("pressure_mild_cpu", 70.0)),
            pressure_mild_ram=float(cfg.get("pressure_mild_ram", 75.0)),
        )


@dataclass
class SystemSnapshot:
    cpu: CpuSnapshot = field(default_factory=CpuSnapshot)
    memory: MemorySnapshot = field(default_factory=MemorySnapshot)
    disk: DiskSnapshot = field(default_factory=DiskSnapshot)
    gpu: GpuSnapshot = field(default_factory=GpuSnapshot)
    network: NetworkSnapshot = field(default_factory=NetworkSnapshot)
    battery: BatterySnapshot = field(default_factory=BatterySnapshot)
    pressure: PressureLevel = PressureLevel.NONE
    process_ram_mb: float = 0.0


class ResourceManager:
    def __init__(self, check_interval: float = 5.0, config: dict | None = None):
        self._check_interval = check_interval
        self._snapshot: SystemSnapshot = SystemSnapshot()
        self._pressure: PressureLevel = PressureLevel.NONE
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Quotas (configurable via config/resource.toml [quota] section)
        self.quota = ResourceQuota.from_config(config)

        # Thread pool
        self._thread_pool = ThreadPoolExecutor(
            max_workers=self.quota.max_threads,
            thread_name_prefix="jarvis-worker",
        )

        # Pressure callbacks
        self._pressure_callbacks: dict[PressureLevel, list[Callable]] = {
            level: [] for level in PressureLevel
        }

        # GPU support (lazy)
        self._nvml_ok = False
        self._nvml_handle = None
        self._init_gpu()

        # Warm-up psutil
        if _PSUTIL_OK:
            psutil.cpu_percent(interval=None)

    def _init_gpu(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_handle = pynvml
            self._nvml_ok = True
            logger.info("GPU monitoring enabled via pynvml")
        except Exception:
            pass

    # ── Lifecycle ─────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("ResourceManager started (interval=%.0fs)", self._check_interval)

    def stop(self):
        self._running = False

    def _monitor_loop(self):
        while self._running:
            try:
                self._sample()
                self._evaluate_pressure()
            except Exception as exc:
                logger.debug("Resource monitor error: %s", exc)
            time.sleep(self._check_interval)

    # ── Sampling ──────────────────────────────

    def _sample(self):
        snap = SystemSnapshot()
        snap.cpu = self._sample_cpu()
        snap.memory = self._sample_memory()
        snap.disk = self._sample_disk()
        snap.gpu = self._sample_gpu()
        snap.network = self._sample_network()
        snap.battery = self._sample_battery()

        if _PSUTIL_OK:
            try:
                proc = psutil.Process(os.getpid())
                snap.process_ram_mb = proc.memory_info().rss / (1024 * 1024)
            except Exception:
                pass

        with self._lock:
            self._snapshot = snap

    def _sample_cpu(self) -> CpuSnapshot:
        snap = CpuSnapshot()
        if not _PSUTIL_OK:
            return snap
        try:
            snap.percent = psutil.cpu_percent(interval=0)
            snap.count = os.cpu_count() or 0
            snap.per_core = psutil.cpu_percent(interval=0, percpu=True)
            freq = psutil.cpu_freq()
            if freq:
                snap.frequency_mhz = freq.current
        except Exception:
            pass
        return snap

    def _sample_memory(self) -> MemorySnapshot:
        snap = MemorySnapshot()
        if not _PSUTIL_OK:
            return snap
        try:
            mem = psutil.virtual_memory()
            snap.percent = mem.percent
            snap.used_gb = mem.used / (1024 ** 3)
            snap.total_gb = mem.total / (1024 ** 3)
            swap = psutil.swap_memory()
            snap.swap_percent = swap.percent
            snap.swap_used_gb = swap.used / (1024 ** 3)
            snap.swap_total_gb = swap.total / (1024 ** 3)
        except Exception:
            pass
        return snap

    def _sample_disk(self) -> DiskSnapshot:
        snap = DiskSnapshot()
        if not _PSUTIL_OK:
            return snap
        try:
            usage = psutil.disk_usage("/")
            snap.percent = usage.percent
            snap.free_gb = usage.free / (1024 ** 3)
            snap.total_gb = usage.total / (1024 ** 3)
            io = psutil.disk_io_counters()
            if io:
                snap.read_mbs = io.read_bytes / (1024 * 1024)
                snap.write_mbs = io.write_bytes / (1024 * 1024)
        except Exception:
            pass
        return snap

    def _sample_gpu(self) -> GpuSnapshot:
        snap = GpuSnapshot()
        if not self._nvml_ok:
            return snap
        try:
            count = self._nvml_handle.nvmlDeviceGetCount()
            if count > 0:
                handle = self._nvml_handle.nvmlDeviceGetHandleByIndex(0)
                snap.available = True
                snap.name = self._nvml_handle.nvmlDeviceGetName(handle).decode()
                mem_info = self._nvml_handle.nvmlDeviceGetMemoryInfo(handle)
                snap.memory_used_gb = mem_info.used / (1024 ** 3)
                snap.memory_total_gb = mem_info.total / (1024 ** 3)
                snap.memory_percent = (mem_info.used / mem_info.total * 100) if mem_info.total else 0.0
                util = self._nvml_handle.nvmlDeviceGetUtilizationRates(handle)
                snap.utilization_percent = util.gpu
                temp = self._nvml_handle.nvmlDeviceGetTemperature(
                    self._nvml_handle.NVML_TEMPERATURE_GPU
                )
                snap.temperature_c = float(temp)
        except Exception as exc:
            logger.debug("GPU sample error: %s", exc)
        return snap

    def _sample_network(self) -> NetworkSnapshot:
        snap = NetworkSnapshot()
        if not _PSUTIL_OK:
            return snap
        try:
            io = psutil.net_io_counters()
            snap.bytes_sent = io.bytes_sent
            snap.bytes_recv = io.bytes_recv
            snap.is_connected = True
        except Exception:
            pass
        return snap

    def _sample_battery(self) -> BatterySnapshot:
        snap = BatterySnapshot()
        if not _PSUTIL_OK:
            return snap
        try:
            battery = psutil.sensors_battery()
            if battery:
                snap.available = True
                snap.percent = battery.percent
                snap.is_charging = battery.power_plugged or False
                snap.time_left_sec = battery.secsleft if battery.secsleft > 0 else None
        except Exception:
            pass
        return snap

    # ── Pressure ──────────────────────────────

    def _evaluate_pressure(self):
        snap = self.snapshot
        cpu = snap.cpu.percent
        mem = snap.memory.percent
        gpu_mem = snap.gpu.memory_percent

        if cpu >= self.quota.pressure_critical or mem >= self.quota.pressure_critical or gpu_mem >= self.quota.pressure_critical:
            new_level = PressureLevel.CRITICAL
        elif cpu >= self.quota.max_cpu_percent or mem >= self.quota.max_ram_percent or gpu_mem >= self.quota.pressure_high:
            new_level = PressureLevel.HIGH
        elif cpu >= self.quota.pressure_mild_cpu or mem >= self.quota.pressure_mild_ram:
            new_level = PressureLevel.MILD
        else:
            new_level = PressureLevel.NONE

        with self._lock:
            old = self._pressure
            self._pressure = new_level

        if new_level != old:
            cbs = self._pressure_callbacks.get(new_level, [])
            for cb in cbs:
                try:
                    cb(new_level, snap)
                except Exception as exc:
                    logger.warning("Pressure callback failed: %s", exc)
            if new_level >= PressureLevel.HIGH and old < PressureLevel.HIGH:
                logger.warning("Resource pressure: %s (cpu=%.0f%%, ram=%.0f%%)",
                               new_level.name, cpu, mem)

    def on_pressure(self, level: PressureLevel, callback: Callable):
        self._pressure_callbacks[level].append(callback)

    # ── Thread Pool ───────────────────────────

    def run_in_thread(self, fn: Callable, *args, **kwargs):
        return self._thread_pool.submit(fn, *args, **kwargs)

    async def run_async(self, fn: Callable, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._thread_pool, fn, *args, **kwargs)

    def resize_pool(self, max_workers: int):
        self.quota.max_threads = max_workers
        new_pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="jarvis-worker",
        )
        old = self._thread_pool
        self._thread_pool = new_pool
        old.shutdown(wait=False)

    # ── Properties ────────────────────────────

    @property
    def snapshot(self) -> SystemSnapshot:
        with self._lock:
            import copy
            return copy.deepcopy(self._snapshot)

    @property
    def pressure(self) -> PressureLevel:
        with self._lock:
            return self._pressure

    @property
    def should_throttle(self) -> bool:
        return self.pressure >= PressureLevel.HIGH

    @property
    def should_degrade_tts(self) -> bool:
        return self.pressure >= PressureLevel.CRITICAL

    @property
    def should_skip_animations(self) -> bool:
        return self.pressure >= PressureLevel.MILD

    @property
    def available_threads(self) -> int:
        # Use threading.active_count() instead of private _threads attribute
        # to avoid breaking when ThreadPoolExecutor internal changes
        active = threading.active_count() if self._thread_pool else 0
        return max(0, self.quota.max_threads - active)

    @property
    def process_ram_mb(self) -> float:
        return self.snapshot.process_ram_mb

    # ── Status / Stats ────────────────────────

    def get_status(self) -> dict:
        snap = self.snapshot
        return {
            "pressure": self.pressure.name,
            "cpu": {
                "percent": round(snap.cpu.percent, 1),
                "count": snap.cpu.count,
                "frequency_mhz": round(snap.cpu.frequency_mhz, 0),
            },
            "memory": {
                "percent": round(snap.memory.percent, 1),
                "used_gb": round(snap.memory.used_gb, 1),
                "total_gb": round(snap.memory.total_gb, 1),
            },
            "disk": {
                "percent": round(snap.disk.percent, 1),
                "free_gb": round(snap.disk.free_gb, 1),
            },
            "gpu": {
                "available": snap.gpu.available,
                "name": snap.gpu.name,
                "memory_percent": round(snap.gpu.memory_percent, 1),
                "utilization_percent": round(snap.gpu.utilization_percent, 1),
            } if snap.gpu.available else {"available": False},
            "battery": {
                "available": snap.battery.available,
                "percent": round(snap.battery.percent, 1),
                "charging": snap.battery.is_charging,
            } if snap.battery.available else {"available": False},
            "process_ram_mb": round(snap.process_ram_mb, 1),
            "thread_pool_max": self.quota.max_threads,
        }

    def get_stats(self) -> dict:
        return {
            "pressure": self.pressure.name,
            "process_ram_mb": round(self.process_ram_mb, 1),
        }

    def update_quota(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self.quota, key):
                setattr(self.quota, key, value)
        if "max_threads" in kwargs:
            self.resize_pool(kwargs["max_threads"])
