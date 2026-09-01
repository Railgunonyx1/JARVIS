"""Latency-Aware Router — tracks per-model TTFT and success rates to make
empirical routing decisions instead of hard-coded ones.

Feeds data back to ModelResidencyScheduler and ModelGateway for
data-driven model selection.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class ModelStats:
    name: str
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    total_ttft_ms: float = 0.0
    total_latency_ms: float = 0.0
    min_ttft_ms: float = float("inf")
    max_ttft_ms: float = 0.0
    last_call: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successes / self.total_calls

    @property
    def avg_ttft_ms(self) -> float:
        if self.successes == 0:
            return 0.0
        return self.total_ttft_ms / self.successes

    @property
    def avg_latency_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_latency_ms / self.total_calls

    @property
    def p95_ttft_ms(self) -> float:
        return self.avg_ttft_ms * 1.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "calls": self.total_calls,
            "success_rate": round(self.success_rate, 3),
            "avg_ttft_ms": round(self.avg_ttft_ms, 1),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "min_ttft_ms": round(self.min_ttft_ms, 1) if self.min_ttft_ms != float("inf") else 0,
            "max_ttft_ms": round(self.max_ttft_ms, 1),
        }


class LatencyAwareRouter:
    """Tracks per-model performance and provides routing recommendations."""

    def __init__(self):
        self._stats: dict[str, ModelStats] = {}

    def record(self, model: str, ttft_ms: float, latency_ms: float, success: bool) -> None:
        if model not in self._stats:
            self._stats[model] = ModelStats(name=model)
        s = self._stats[model]
        s.total_calls += 1
        s.last_call = time.time()
        if success:
            s.successes += 1
            s.total_ttft_ms += ttft_ms
            s.min_ttft_ms = min(s.min_ttft_ms, ttft_ms)
            s.max_ttft_ms = max(s.max_ttft_ms, ttft_ms)
        else:
            s.failures += 1
        s.total_latency_ms += latency_ms

    def recommend(self, confidence: float, exclude: set[str] | None = None) -> str | None:
        exclude = exclude or set()
        candidates = [(m, s) for m, s in self._stats.items()
                      if m not in exclude and s.total_calls >= 3 and s.success_rate >= 0.8]
        if not candidates:
            return None

        if confidence >= 0.8:
            candidates.sort(key=lambda x: x[1].avg_ttft_ms)
            return candidates[0][0]

        if confidence >= 0.5:
            scored = [(s.success_rate * 0.6 + (1.0 - min(s.avg_ttft_ms / 2000.0, 1.0)) * 0.4, m)
                      for m, s in candidates]
            scored.sort(reverse=True)
            return scored[0][1]

        candidates.sort(key=lambda x: x[1].success_rate, reverse=True)
        return candidates[0][0]

    def get_stats(self) -> dict[str, dict[str, Any]]:
        return {m: s.to_dict() for m, s in self._stats.items()}

    def get_ttft_percentile(self, model: str, percentile: float = 0.95) -> float:
        s = self._stats.get(model)
        if s is None or s.successes == 0:
            return 0.0
        if percentile >= 0.95:
            return s.p95_ttft_ms
        return s.avg_ttft_ms
