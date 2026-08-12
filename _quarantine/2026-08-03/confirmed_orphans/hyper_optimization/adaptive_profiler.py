"""JARVIS MK-X Hyper-Optimization Engine — Adaptive Profiler.

Continuous profiling with self-adapting overhead control. Profiles code
blocks via context manager and maintains statistical summaries including
percentiles and standard deviation.
"""

import logging
import math
import random
import statistics
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("jarvis.hyper_opt.adaptive_profiler")


class _ProfileData:
    """Stores profiling samples and computed statistics for a single stage."""

    __slots__ = ("samples", "stats", "last_update")

    def __init__(self, maxlen: int = 10000):
        self.samples: deque = deque(maxlen=maxlen)
        self.stats: dict[str, Any] = {}
        self.last_update: float = 0.0

    def record(self, elapsed_ms: float) -> None:
        self.samples.append(elapsed_ms)
        self.last_update = time.perf_counter()
        self._recompute()

    def _recompute(self) -> None:
        if not self.samples:
            self.stats = {}
            return

        data = list(self.samples)
        count = len(data)
        sorted_data = sorted(data)
        mean_val = statistics.mean(data)
        variance = statistics.variance(data) if count > 1 else 0.0

        self.stats = {
            "count": count,
            "avg_ms": round(mean_val, 4),
            "min_ms": round(sorted_data[0], 4),
            "max_ms": round(sorted_data[-1], 4),
            "std_dev": round(math.sqrt(variance), 4),
            "p50_ms": round(_percentile(sorted_data, 50), 4),
            "p95_ms": round(_percentile(sorted_data, 95), 4),
            "p99_ms": round(_percentile(sorted_data, 99), 4),
            "last_sample_ms": round(data[-1], 4),
            "last_update": self.last_update,
        }


def _percentile(sorted_data: list[float], pct: float) -> float:
    """Calculate percentile from pre-sorted data using linear interpolation."""
    if not sorted_data:
        return 0.0
    if len(sorted_data) == 1:
        return sorted_data[0]
    k = (pct / 100.0) * (len(sorted_data) - 1)
    floor = int(math.floor(k))
    ceil = min(floor + 1, len(sorted_data) - 1)
    frac = k - floor
    return sorted_data[floor] + frac * (sorted_data[ceil] - sorted_data[floor])


class AdaptiveProfiler:
    """Continuous profiling that adapts its own overhead."""

    def __init__(self, max_samples: int = 10000):
        self._max_samples = max_samples
        self._profiles: dict[str, _ProfileData] = {}
        self._overhead_ms: float = 0.0
        self._sampling_rate: float = 1.0
        self._target_overhead_ms: float = 0.5
        self._total_profiled_blocks: int = 0
        self._total_skipped_blocks: int = 0
        self._lock = threading.RLock()
        logger.info("AdaptiveProfiler initialized (max_samples=%d)", max_samples)

    @contextmanager
    def profile(self, name: str):
        """Context manager that profiles a block. Respects sampling_rate."""
        should_sample = self._should_sample()
        if not should_sample:
            with self._lock:
                self._total_skipped_blocks += 1
            yield False
            return

        start = time.perf_counter()
        try:
            yield True
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            # Subtract the overhead of the measurement itself
            measurement_cost = self._estimate_measurement_overhead()
            adjusted = max(0.0, elapsed_ms - measurement_cost)
            self.record(name, adjusted)

    def _should_sample(self) -> bool:
        """Determine whether to sample based on current sampling rate."""
        with self._lock:
            rate = self._sampling_rate
        if rate >= 1.0:
            return True
        if rate <= 0.0:
            return False
        return random.random() < rate

    def _estimate_measurement_overhead(self) -> float:
        """Estimate the overhead of perf_counter calls."""
        with self._lock:
            return self._overhead_ms

    def record(self, name: str, elapsed_ms: float) -> None:
        """Record a timing sample."""
        with self._lock:
            if name not in self._profiles:
                self._profiles[name] = _ProfileData(maxlen=self._max_samples)
            self._profiles[name].record(elapsed_ms)
            self._total_profiled_blocks += 1

    def get_profile(self, name: str) -> dict[str, Any]:
        """Returns avg, min, max, p50, p95, p99, count, std_dev."""
        with self._lock:
            data = self._profiles.get(name)
            if data is None:
                return {"error": f"No profile data for '{name}'", "count": 0}
            return dict(data.stats)

    def get_all_profiles(self) -> dict[str, dict[str, Any]]:
        """Returns all profiles."""
        with self._lock:
            result = {}
            for name, data in self._profiles.items():
                result[name] = dict(data.stats) if data.stats else {}
            return result

    def get_bottlenecks(self, budget_ms: float = 100) -> list[dict[str, Any]]:
        """Returns stages exceeding their latency budget, sorted by severity."""
        with self._lock:
            bottlenecks: list[dict[str, Any]] = []
            for name, data in self._profiles.items():
                if not data.stats:
                    continue
                avg = data.stats.get("avg_ms", 0)
                p95 = data.stats.get("p95_ms", 0)
                if p95 > budget_ms or avg > budget_ms:
                    severity = "critical" if p95 > budget_ms * 2 else "warning"
                    bottlenecks.append({
                        "stage": name,
                        "avg_ms": data.stats["avg_ms"],
                        "p95_ms": data.stats["p95_ms"],
                        "budget_ms": budget_ms,
                        "overage_avg_ms": round(avg - budget_ms, 3),
                        "overage_p95_ms": round(p95 - budget_ms, 3),
                        "severity": severity,
                        "count": data.stats["count"],
                    })
            bottlenecks.sort(key=lambda b: b["overage_p95_ms"], reverse=True)
            return bottlenecks

    def adapt_sampling_rate(self, target_overhead_ms: float = 0.5) -> float:
        """Adjust sampling rate to keep profiling overhead under target."""
        self._target_overhead_ms = target_overhead_ms
        with self._lock:
            total_samples = sum(
                data.stats.get("count", 0) for data in self._profiles.values()
            )
            if total_samples == 0:
                self._sampling_rate = 1.0
                return self._sampling_rate

            # Estimate per-sample overhead from measurement cost
            avg_sample_count = max(
                (data.stats.get("count", 0) for data in self._profiles.values()),
                default=1,
            )
            if avg_sample_count <= 0:
                self._sampling_rate = 1.0
                return self._sampling_rate

            # Estimate overhead per block: measure timing cost
            measurement_start = time.perf_counter()
            for _ in range(100):
                _ = time.perf_counter()
            measurement_end = time.perf_counter()
            per_block_ms = ((measurement_end - measurement_start) / 100) * 1000

            # Factor in lock acquisition and dict lookup
            per_block_ms *= 3.0  # conservative multiplier

            if per_block_ms <= 0:
                self._sampling_rate = 1.0
            else:
                rate = target_overhead_ms / per_block_ms
                self._sampling_rate = max(0.01, min(1.0, rate))

            self._overhead_ms = per_block_ms
            logger.info(
                "Adapted sampling rate to %.3f (per-block cost ~%.4f ms, target %.2f ms)",
                self._sampling_rate, per_block_ms, target_overhead_ms,
            )
            return self._sampling_rate

    def get_sampling_rate(self) -> float:
        """Returns current sampling rate."""
        with self._lock:
            return self._sampling_rate

    def get_overhead_stats(self) -> dict[str, Any]:
        """Returns overhead measurement stats."""
        with self._lock:
            return {
                "sampling_rate": self._sampling_rate,
                "estimated_per_block_ms": round(self._overhead_ms, 4),
                "target_overhead_ms": self._target_overhead_ms,
                "total_profiled": self._total_profiled_blocks,
                "total_skipped": self._total_skipped_blocks,
            }

    def get_top_consumers(self, limit: int = 5) -> list[dict[str, Any]]:
        """Returns top N stages by average latency."""
        with self._lock:
            items = []
            for name, data in self._profiles.items():
                if data.stats:
                    items.append({
                        "stage": name,
                        "avg_ms": data.stats["avg_ms"],
                        "p95_ms": data.stats["p95_ms"],
                        "count": data.stats["count"],
                    })
            items.sort(key=lambda x: x["avg_ms"], reverse=True)
            return items[:limit]

    def reset(self, name: str | None = None) -> None:
        """Clear profiles. If name given, clear only that profile."""
        with self._lock:
            if name:
                if name in self._profiles:
                    del self._profiles[name]
                    logger.info("Reset profile '%s'", name)
            else:
                self._profiles.clear()
                self._total_profiled_blocks = 0
                self._total_skipped_blocks = 0
                logger.info("Reset all profiles")


_profiler_instance: AdaptiveProfiler | None = None
_profiler_lock = threading.RLock()


def get_adaptive_profiler() -> AdaptiveProfiler:
    """Singleton accessor for AdaptiveProfiler."""
    global _profiler_instance
    with _profiler_lock:
        if _profiler_instance is None:
            _profiler_instance = AdaptiveProfiler()
        return _profiler_instance
