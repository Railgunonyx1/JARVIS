"""Continuous Benchmarking — Measure everything, reject regressions.

Every commit/session automatically measures:
- Cold start, warm start
- STT latency
- LLM first-token latency
- Total response latency
- Memory usage
- CPU/GPU utilization

Reject changes that regress performance beyond threshold.
"""
import logging
import statistics
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("benchmark.continuous")


@dataclass
class BenchmarkResult:
    """Result of a single benchmark measurement."""
    name: str
    value_ms: float
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class BenchmarkBaseline:
    """Baseline metrics for a benchmark."""
    name: str
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    sample_count: int = 0
    regression_threshold_pct: float = 20.0  # 20% regression triggers alert


class ContinuousBenchmark:
    """Continuous performance benchmarking system.

    Measures key latency metrics and detects regressions.
    """

    def __init__(self, max_history: int = 1000):
        self._benchmarks: dict[str, deque] = {}
        self._baselines: dict[str, BenchmarkBaseline] = {}
        self._max_history = max_history
        self._lock = threading.Lock()
        self._regression_callbacks: list[Callable] = []
        self._active = True

    def measure(self, name: str, value_ms: float, **metadata) -> dict[str, Any]:
        """Record a benchmark measurement. Returns regression check."""
        result = BenchmarkResult(name=name, value_ms=value_ms, metadata=metadata)

        with self._lock:
            if name not in self._benchmarks:
                self._benchmarks[name] = deque(maxlen=self._max_history)
            self._benchmarks[name].append(result)

        # Check for regression
        regression = self._check_regression(name, value_ms)
        if regression:
            logger.warning("REGRESSION detected in '%s': %.1fms vs baseline p95=%.1fms",
                           name, value_ms, regression.get("baseline_p95", 0))
            for cb in self._regression_callbacks:
                try:
                    cb(name, regression)
                except Exception:
                    pass

        return {"recorded": True, "regression": regression}

    def _check_regression(self, name: str, value_ms: float) -> dict[str, Any] | None:
        """Check if a measurement represents a regression."""
        baseline = self._baselines.get(name)
        if baseline is None or baseline.sample_count < 10:
            return None

        if value_ms > baseline.p95_ms * (1 + baseline.regression_threshold_pct / 100):
            return {
                "name": name,
                "value_ms": value_ms,
                "baseline_p50": baseline.p50_ms,
                "baseline_p95": baseline.p95_ms,
                "regression_pct": round((value_ms - baseline.p95_ms) / max(baseline.p95_ms, 1) * 100, 1),
            }
        return None

    def set_baseline(self, name: str, regression_threshold_pct: float = 20.0) -> BenchmarkBaseline:
        """Calculate and set baseline from collected data."""
        with self._lock:
            data = self._benchmarks.get(name)
            if data is None or len(data) < 5:
                return BenchmarkBaseline(name=name)

            values = sorted([r.value_ms for r in data])
            baseline = BenchmarkBaseline(
                name=name,
                p50_ms=statistics.median(values),
                p95_ms=values[int(len(values) * 0.95)] if len(values) >= 20 else values[-1],
                p99_ms=values[int(len(values) * 0.99)] if len(values) >= 100 else values[-1],
                min_ms=values[0],
                max_ms=values[-1],
                sample_count=len(values),
                regression_threshold_pct=regression_threshold_pct,
            )
            self._baselines[name] = baseline
            return baseline

    def on_regression(self, callback: Callable) -> None:
        self._regression_callbacks.append(callback)

    def get_report(self) -> dict[str, Any]:
        """Get comprehensive benchmark report."""
        report = {}
        with self._lock:
            for name, data in self._benchmarks.items():
                values = [r.value_ms for r in data]
                if values:
                    sorted_vals = sorted(values)
                    report[name] = {
                        "samples": len(values),
                        "p50_ms": round(statistics.median(sorted_vals), 1),
                        "p95_ms": round(sorted_vals[int(len(sorted_vals) * 0.95)] if len(sorted_vals) >= 20 else sorted_vals[-1], 1),
                        "min_ms": round(sorted_vals[0], 1),
                        "max_ms": round(sorted_vals[-1], 1),
                        "avg_ms": round(statistics.mean(sorted_vals), 1),
                        "stdev_ms": round(statistics.stdev(sorted_vals), 1) if len(sorted_vals) > 1 else 0,
                    }

        # Add baseline comparisons
        for name, baseline in self._baselines.items():
            if name in report:
                report[name]["baseline"] = {
                    "p50": baseline.p50_ms,
                    "p95": baseline.p95_ms,
                    "threshold_pct": baseline.regression_threshold_pct,
                }

        return report

    def get_benchmark_names(self) -> list[str]:
        with self._lock:
            return list(self._benchmarks.keys())

    def clear(self, name: str = None) -> None:
        with self._lock:
            if name:
                self._benchmarks.pop(name, None)
            else:
                self._benchmarks.clear()

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_benchmarks": len(self._benchmarks),
                "total_measurements": sum(len(d) for d in self._benchmarks.values()),
                "baselines_set": len(self._baselines),
                "benchmark_names": list(self._benchmarks.keys()),
            }


_benchmark_instance: ContinuousBenchmark | None = None


def get_continuous_benchmark() -> ContinuousBenchmark:
    global _benchmark_instance
    if _benchmark_instance is None:
        _benchmark_instance = ContinuousBenchmark()
    return _benchmark_instance
