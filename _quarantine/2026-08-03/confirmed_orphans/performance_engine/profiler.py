"""Performance Profiler — context-manager-based execution timing with bottleneck detection."""

import json
import logging
import math
import threading
import time
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("jarvis.performance_engine.profiler")

_MAX_ENTRIES_PER_PROFILE = 10000


class PerformanceProfiler:
    """Records execution times and arbitrary metrics, computes stats, detects bottlenecks."""

    def __init__(self) -> None:
        self._profiles: dict[str, list[float]] = {}
        self._metrics: dict[str, list[tuple[float, dict[str, str] | None]]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Context-manager profiling
    # ------------------------------------------------------------------

    @contextmanager
    def profile(self, name: str):
        """Context manager that records execution time in milliseconds."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self._record_sample(name, elapsed_ms)

    def _record_sample(self, name: str, ms: float) -> None:
        with self._lock:
            if name not in self._profiles:
                self._profiles[name] = []
            buf = self._profiles[name]
            buf.append(ms)
            if len(buf) > _MAX_ENTRIES_PER_PROFILE:
                self._profiles[name] = buf[-_MAX_ENTRIES_PER_PROFILE:]

    # ------------------------------------------------------------------
    # Arbitrary metrics
    # ------------------------------------------------------------------

    def record_metric(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record an arbitrary metric value with optional tags."""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = []
            buf = self._metrics[name]
            buf.append((value, tags))
            if len(buf) > _MAX_ENTRIES_PER_PROFILE:
                self._metrics[name] = buf[-_MAX_ENTRIES_PER_PROFILE:]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def _compute_stats(self, values: list[float]) -> dict[str, Any]:
        n = len(values)
        if n == 0:
            return {"avg": 0.0, "min": 0.0, "max": 0.0, "p95": 0.0, "count": 0}
        s = sorted(values)
        avg = sum(s) / n
        p95_idx = min(int(math.ceil(0.95 * n)) - 1, n - 1)
        return {
            "avg": round(avg, 4),
            "min": round(s[0], 4),
            "max": round(s[-1], 4),
            "p95": round(s[p95_idx], 4),
            "count": n,
        }

    def get_profile(self, name: str) -> dict[str, Any]:
        """Return stats for a single profiled stage."""
        with self._lock:
            values = list(self._profiles.get(name, []))
        stats = self._compute_stats(values)
        stats["name"] = name
        return stats

    def get_all_profiles(self) -> dict[str, dict[str, Any]]:
        """Return stats for every profiled stage."""
        with self._lock:
            names = list(self._profiles.keys())
        return {name: self.get_profile(name) for name in names}

    # ------------------------------------------------------------------
    # Bottleneck detection
    # ------------------------------------------------------------------

    def get_bottlenecks(self, threshold_ms: float = 100.0) -> list[dict[str, Any]]:
        """Return stages whose average time exceeds *threshold_ms*."""
        with self._lock:
            names = list(self._profiles.keys())
        bottlenecks: list[dict[str, Any]] = []
        for name in names:
            stats = self.get_profile(name)
            if stats["avg"] > threshold_ms:
                bottlenecks.append(stats)
        bottlenecks.sort(key=lambda s: s["avg"], reverse=True)
        return bottlenecks

    # ------------------------------------------------------------------
    # Export / reset
    # ------------------------------------------------------------------

    def export_json(self) -> str:
        """Serialize all profile data to a JSON string for debugging."""
        with self._lock:
            data = {
                "profiles": {
                    name: self._compute_stats(list(vals))
                    for name, vals in self._profiles.items()
                },
                "metrics": {
                    name: [
                        {"value": v, "tags": t} for v, t in entries
                    ]
                    for name, entries in self._metrics.items()
                },
            }
        return json.dumps(data, indent=2, default=str)

    def reset(self) -> None:
        """Clear all recorded profiles and metrics."""
        with self._lock:
            self._profiles.clear()
            self._metrics.clear()
        logger.info("Profiler data reset")


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_profiler: PerformanceProfiler | None = None
_profiler_lock = threading.Lock()


def get_profiler() -> PerformanceProfiler:
    global _profiler
    if _profiler is None:
        with _profiler_lock:
            if _profiler is None:
                _profiler = PerformanceProfiler()
    return _profiler
