"""Performance diagnostics for JARVIS Desktop.

Measures startup time, CPU/RAM usage, voice latency, gesture tracking
FPS, and 3D workspace FPS. Results feed the optimization budget (§10).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger("jarvis.desktop.diagnostics")


@dataclass
class PerformanceSnapshot:
    """Single performance measurement."""
    timestamp: float
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    events: dict[str, float] = field(default_factory=dict)


class PerformanceMonitor:
    """Background monitor for CPU/RAM usage.

    Samples every interval seconds. Provides the metrics for the
    idle/active performance budget.
    """

    def __init__(self, interval: float = 1.0):
        self._interval = interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._snapshots: list[PerformanceSnapshot] = []
        self._max_snapshots = 3600

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="jarvis-diagnostics")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def record_event(self, name: str, duration_ms: float) -> None:
        """Record a named event latency."""
        with self._lock:
            if self._snapshots:
                self._snapshots[-1].events[name] = duration_ms

    def _loop(self) -> None:
        try:
            import psutil
            process = psutil.Process()
        except ImportError:
            logger.warning("psutil unavailable — diagnostics will be empty")
            return

        while self._running:
            try:
                cpu = process.cpu_percent(interval=0.1)
                mem = process.memory_info()
                ram_percent = psutil.virtual_memory().percent
                snapshot = PerformanceSnapshot(
                    timestamp=time.time(),
                    cpu_percent=cpu,
                    ram_percent=ram_percent,
                    ram_used_gb=mem.rss / (1024**3),
                    events={},
                )
                with self._lock:
                    self._snapshots.append(snapshot)
                    if len(self._snapshots) > self._max_snapshots:
                        self._snapshots = self._snapshots[-self._max_snapshots:]
            except Exception:
                pass
            time.sleep(self._interval)

    def get_average_cpu(self, last_n: int = 60) -> float:
        with self._lock:
            recent = self._snapshots[-last_n:]
        if not recent:
            return 0.0
        return sum(s.cpu_percent for s in recent) / len(recent)

    def get_average_ram(self, last_n: int = 60) -> float:
        with self._lock:
            recent = self._snapshots[-last_n:]
        if not recent:
            return 0.0
        return sum(s.ram_percent for s in recent) / len(recent)

    def get_peak_ram_gb(self) -> float:
        with self._lock:
            snapshots = list(self._snapshots)
        if not snapshots:
            return 0.0
        return max(s.ram_used_gb for s in snapshots)

    def get_event_latencies(self, name: str) -> list[float]:
        with self._lock:
            return [s.events.get(name, 0.0) for s in self._snapshots if name in s.events]


class BenchmarkResult:
    """Result of a single benchmark measurement."""
    def __init__(self, name: str, value: float, unit: str, target: float | None = None,
                 passed: bool | None = None):
        self.name = name
        self.value = value
        self.unit = unit
        self.target = target
        self.passed = passed

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "target": self.target,
            "passed": self.passed,
        }


class PerformanceBenchmarker:
    """Runs performance measurements against the §10 budget targets.

    Targets (from master plan §10):
      - Idle CPU: < 2%
      - Idle RAM: < 1 GB
      - Voice STT→TTS round-trip: < 3 s
      - Tool execution: < 1 s
      - Workspace FPS: >= 30 when visible
    """

    # Performance targets
    TARGET_IDLE_CPU = 2.0       # percent
    TARGET_IDLE_RAM_GB = 1.0    # gigabytes
    TARGET_VOICE_ROUNDTRIP_S = 3.0
    TARGET_TOOL_EXEC_S = 1.0
    TARGET_WORKSPACE_FPS = 30.0

    def __init__(self, monitor: PerformanceMonitor | None = None):
        self._monitor = monitor or PerformanceMonitor()
        self._results: list[BenchmarkResult] = []

    def measure_startup_time(self, start_fn: Callable, *args, **kwargs) -> BenchmarkResult:
        """Measure application startup time."""
        start = time.perf_counter()
        start_fn(*args, **kwargs)
        elapsed = time.perf_counter() - start
        result = BenchmarkResult("startup_time", elapsed, "s", target=3.0,
                                 passed=elapsed < 3.0)
        self._results.append(result)
        return result

    def measure_idle_resources(self, duration_s: float = 10.0) -> tuple[BenchmarkResult, BenchmarkResult]:
        """Measure idle CPU and RAM over a duration."""
        self._monitor.start()
        time.sleep(duration_s)
        self._monitor.stop()

        avg_cpu = self._monitor.get_average_cpu()
        avg_ram = self._monitor.get_average_ram()

        cpu_result = BenchmarkResult("idle_cpu_percent", avg_cpu, "%",
                                     target=self.TARGET_IDLE_CPU,
                                     passed=avg_cpu < self.TARGET_IDLE_CPU)
        ram_result = BenchmarkResult("idle_ram_gb", avg_ram / 100.0, "GB",
                                     target=self.TARGET_IDLE_RAM_GB,
                                     passed=avg_ram / 100.0 < self.TARGET_IDLE_RAM_GB)
        self._results.extend([cpu_result, ram_result])
        return cpu_result, ram_result

    def measure_voice_roundtrip(self, stt_fn: Callable, agent_fn: Callable,
                                 tts_fn: Callable) -> BenchmarkResult:
        """Measure STT → agent → TTS round-trip latency."""
        start = time.perf_counter()
        text = stt_fn() if stt_fn else "hello"
        agent_fn(text) if agent_fn else None
        tts_fn(text) if tts_fn else None
        elapsed = time.perf_counter() - start
        result = BenchmarkResult("voice_roundtrip_s", elapsed, "s",
                                 target=self.TARGET_VOICE_ROUNDTRIP_S,
                                 passed=elapsed < self.TARGET_VOICE_ROUNDTRIP_S)
        self._results.append(result)
        return result

    def measure_tool_execution(self, tool_fn: Callable, *args, **kwargs) -> BenchmarkResult:
        """Measure a single tool execution latency."""
        start = time.perf_counter()
        tool_fn(*args, **kwargs)
        elapsed = time.perf_counter() - start
        result = BenchmarkResult("tool_exec_s", elapsed, "s",
                                 target=self.TARGET_TOOL_EXEC_S,
                                 passed=elapsed < self.TARGET_TOOL_EXEC_S)
        self._results.append(result)
        return result

    def measure_workspace_fps(self, get_fps_fn: Callable, duration_s: float = 5.0) -> BenchmarkResult:
        """Measure 3D workspace average FPS."""
        samples = []
        start = time.perf_counter()
        while time.perf_counter() - start < duration_s:
            fps = get_fps_fn()
            if fps:
                samples.append(fps)
            time.sleep(0.2)
        avg_fps = sum(samples) / len(samples) if samples else 0.0
        result = BenchmarkResult("workspace_fps", avg_fps, "fps",
                                 target=self.TARGET_WORKSPACE_FPS,
                                 passed=avg_fps >= self.TARGET_WORKSPACE_FPS)
        self._results.append(result)
        return result

    def get_results(self) -> list[dict]:
        return [r.to_dict() for r in self._results]

    def get_summary(self) -> dict:
        results = self._results
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        return {
            "total_measurements": total,
            "passed": passed,
            "failed": total - passed,
            "all_passed": passed == total and total > 0,
        }

    def save_report(self, path: str | Path) -> None:
        """Save benchmark results to JSON."""
        import json
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "results": self.get_results(),
            "summary": self.get_summary(),
        }
        path.write_text(json.dumps(report, indent=2))
