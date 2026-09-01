"""Per-Model Performance Tracker — learns from historical latency and
success data to make routing decisions that improve over time.

Unlike LatencyAwareRouter (which tracks live), this module persists
metrics and computes rolling statistics for long-term learning.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jarvis.perf_learning")


@dataclass
class ModelPerfMetrics:
    model: str
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    ttft_samples: list[float] = field(default_factory=list)
    latency_samples: list[float] = field(default_factory=list)
    tool_success_samples: list[bool] = field(default_factory=list)
    last_updated: float = 0.0
    first_seen: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successes / self.total_calls

    @property
    def avg_ttft_ms(self) -> float:
        if not self.ttft_samples:
            return 0.0
        return sum(self.ttft_samples) / len(self.ttft_samples)

    @property
    def p50_ttft_ms(self) -> float:
        if not self.ttft_samples:
            return 0.0
        s = sorted(self.ttft_samples)
        mid = len(s) // 2
        return s[mid]

    @property
    def p95_ttft_ms(self) -> float:
        if not self.ttft_samples:
            return 0.0
        s = sorted(self.ttft_samples)
        idx = max(0, int(len(s) * 0.95) - 1)
        return s[idx]

    @property
    def avg_latency_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        return sum(self.latency_samples) / len(self.latency_samples)

    @property
    def tool_success_rate(self) -> float:
        if not self.tool_success_samples:
            return 1.0
        return sum(self.tool_success_samples) / len(self.tool_success_samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "calls": self.total_calls,
            "success_rate": round(self.success_rate, 3),
            "tool_success_rate": round(self.tool_success_rate, 3),
            "avg_ttft_ms": round(self.avg_ttft_ms, 1),
            "p50_ttft_ms": round(self.p50_ttft_ms, 1),
            "p95_ttft_ms": round(self.p95_ttft_ms, 1),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


class PerfTracker:
    """Tracks per-model performance metrics for routing intelligence."""

    MAX_SAMPLES = 100

    def __init__(self):
        self._metrics: dict[str, ModelPerfMetrics] = {}

    def record(
        self, model: str, ttft_ms: float, latency_ms: float,
        success: bool, tool_success: bool | None = None,
    ) -> None:
        now = time.time()
        if model not in self._metrics:
            self._metrics[model] = ModelPerfMetrics(
                model=model, first_seen=now,
            )
        m = self._metrics[model]
        m.total_calls += 1
        m.last_updated = now
        if success:
            m.successes += 1
            if len(m.ttft_samples) < self.MAX_SAMPLES:
                m.ttft_samples.append(ttft_ms)
            if len(m.latency_samples) < self.MAX_SAMPLES:
                m.latency_samples.append(latency_ms)
        else:
            m.failures += 1
        if tool_success is not None:
            if len(m.tool_success_samples) < self.MAX_SAMPLES:
                m.tool_success_samples.append(tool_success)

    def recommend(self, task_type: str = "") -> str | None:
        candidates = []
        for model, m in self._metrics.items():
            if m.total_calls < 3:
                continue
            candidates.append((model, m))
        if not candidates:
            return None

        scored = []
        for model, m in candidates:
            score = m.success_rate * 40
            score += m.tool_success_rate * 20
            if m.avg_ttft_ms > 0:
                score += max(0, (2000 - m.avg_ttft_ms) / 100)
            if task_type == "coding" and m.tool_success_rate > 0.8:
                score += 10
            scored.append((score, model))
        scored.sort(reverse=True)
        return scored[0][1] if scored else None

    def get_metrics(self) -> dict[str, dict[str, Any]]:
        return {m: pm.to_dict() for m, pm in self._metrics.items()}

    def get_model_summary(self, model: str) -> dict[str, Any] | None:
        m = self._metrics.get(model)
        return m.to_dict() if m else None

    def reset(self, model: str | None = None) -> None:
        if model:
            self._metrics.pop(model, None)
        else:
            self._metrics.clear()
