"""Metrics registry — session-level counters, gauges, and histograms.

Used for aggregate facts that don't belong on a single span (provider
success/fail counts, IPC request counts, cache hit counters). Snapshot is
consumed by ``jarvis perf summary`` and the future performance dashboard.
"""

from __future__ import annotations

import threading
from typing import Any

__all__ = ["MetricsRegistry", "get_metrics", "reset_metrics"]


class MetricsRegistry:
    """Thread-safe counters / gauges / bounded histograms."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._hist: dict[str, list[float]] = {}

    def counter(self, name: str, delta: float = 1.0) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + delta

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = float(value)

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            bucket = self._hist.setdefault(name, [])
            bucket.append(float(value))
            if len(bucket) > 1024:
                del bucket[0]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            hist: dict[str, dict[str, float]] = {}
            for name, values in self._hist.items():
                if values:
                    hist[name] = {
                        "count": len(values),
                        "min": round(min(values), 2),
                        "max": round(max(values), 2),
                        "avg": round(sum(values) / len(values), 2),
                        "last": round(values[-1], 2),
                    }
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": hist,
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._hist.clear()


_metrics: MetricsRegistry | None = None
_metrics_lock = threading.Lock()


def get_metrics() -> MetricsRegistry:
    global _metrics
    if _metrics is None:
        with _metrics_lock:
            if _metrics is None:
                _metrics = MetricsRegistry()
    return _metrics


def reset_metrics() -> MetricsRegistry:
    global _metrics
    with _metrics_lock:
        _metrics = MetricsRegistry()
    return _metrics
