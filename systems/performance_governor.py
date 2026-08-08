"""Real-Time Performance Governor — Game-engine-style latency budget enforcement.

Every processing cycle: Measure → Predict → Adjust → Maintain Target Latency.
"""
import logging
import time
import threading
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger("systems.performance_governor")


@dataclass
class LatencyBudget:
    """Latency budget for a pipeline stage."""
    name: str
    target_ms: float
    warning_ms: float = 0.0
    critical_ms: float = 0.0
    current_ms: float = 0.0
    violations: int = 0
    total_samples: int = 0
    avg_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0

    def __post_init__(self):
        if self.warning_ms == 0.0:
            self.warning_ms = self.target_ms * 1.2
        if self.critical_ms == 0.0:
            self.critical_ms = self.target_ms * 1.5


class PerformanceGovernor:
    """Enforces latency budgets across the entire JARVIS pipeline.

    Inspired by game engine frame budgets: if one stage runs over,
    subsequent stages get reduced budgets to maintain overall target.
    """

    def __init__(self, overall_target_ms: float = 500.0):
        self._target_ms = overall_target_ms
        self._budgets: Dict[str, LatencyBudget] = {}
        self._history: deque = deque(maxlen=500)
        self._lock = threading.Lock()
        self._active = True
        self._total_frames = 0
        self._total_violations = 0

        # Default pipeline budgets
        self.register_budget("voice_input", 30)
        self.register_budget("stt", 200)
        self.register_budget("intent", 50)
        self.register_budget("planning", 100)
        self.register_budget("llm", 300)
        self.register_budget("tool_execution", 150)
        self.register_budget("tts", 100)
        self.register_budget("total", overall_target_ms)

    def register_budget(self, name: str, target_ms: float, **kwargs) -> None:
        with self._lock:
            self._budgets[name] = LatencyBudget(name=name, target_ms=target_ms, **kwargs)

    def begin_frame(self) -> "FrameContext":
        """Mark the start of a processing frame. Returns a context for tracking."""
        return FrameContext(governor=self)

    def record_stage(self, stage_name: str, elapsed_ms: float) -> Dict[str, Any]:
        """Record actual latency for a stage. Returns violation info."""
        with self._lock:
            budget = self._budgets.get(stage_name)
            if budget is None:
                return {"status": "unknown_stage"}

            budget.total_samples += 1
            budget.current_ms = elapsed_ms
            budget.avg_ms = ((budget.avg_ms * (budget.total_samples - 1)) + elapsed_ms) / budget.total_samples

            result = {"status": "ok", "stage": stage_name, "ms": elapsed_ms, "target": budget.target_ms}

            if elapsed_ms > budget.critical_ms:
                budget.violations += 1
                self._total_violations += 1
                result["status"] = "critical"
                result["overrun_ms"] = elapsed_ms - budget.target_ms
                logger.warning("CRITICAL: %s took %.0fms (target: %.0fms)", stage_name, elapsed_ms, budget.target_ms)
            elif elapsed_ms > budget.warning_ms:
                budget.violations += 1
                result["status"] = "warning"
                result["overrun_ms"] = elapsed_ms - budget.target_ms

            return result

    def end_frame(self) -> Dict[str, Any]:
        """End a processing frame. Returns overall frame stats."""
        self._total_frames += 1
        total = self._budgets.get("total")
        frame_data = {
            "frame": self._total_frames,
            "total_violations": self._total_violations,
            "budgets": {},
        }
        with self._lock:
            for name, budget in self._budgets.items():
                if budget.total_samples > 0:
                    frame_data["budgets"][name] = {
                        "target_ms": budget.target_ms,
                        "current_ms": budget.current_ms,
                        "avg_ms": round(budget.avg_ms, 1),
                        "violations": budget.violations,
                    }
            self._history.append(frame_data)
        return frame_data

    def get_headroom(self, stage_name: str) -> float:
        """Get remaining time budget for a stage in ms."""
        with self._lock:
            budget = self._budgets.get(stage_name)
            if budget is None:
                return 0.0
            return max(0, budget.target_ms - budget.current_ms)

    def should_skip(self, stage_name: str) -> bool:
        """Check if a non-critical stage should be skipped to save time."""
        with self._lock:
            budget = self._budgets.get("total")
            if budget and budget.current_ms > budget.target_ms * 0.8:
                return True
            return False

    def get_report(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "target_ms": self._target_ms,
                "total_frames": self._total_frames,
                "total_violations": self._total_violations,
                "violation_rate": round(self._total_violations / max(self._total_frames, 1) * 100, 1),
                "budgets": {
                    name: {
                        "target_ms": b.target_ms,
                        "avg_ms": round(b.avg_ms, 1),
                        "violations": b.violations,
                        "samples": b.total_samples,
                    }
                    for name, b in self._budgets.items()
                    if b.total_samples > 0
                },
            }


class FrameContext:
    """Context manager for tracking a processing frame."""

    def __init__(self, governor: PerformanceGovernor):
        self.governor = governor
        self.start_time = time.perf_counter()
        self.stages: Dict[str, float] = {}

    def stage(self, name: str) -> "StageTimer":
        return StageTimer(context=self, name=name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        elapsed_ms = (time.perf_counter() - self.start_time) * 1000
        self.governor.record_stage("total", elapsed_ms)
        self.governor.end_frame()


class StageTimer:
    """Timer for a single pipeline stage."""

    def __init__(self, context: FrameContext, name: str):
        self.context = context
        self.name = name
        self.start_time = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        elapsed_ms = (time.perf_counter() - self.start_time) * 1000
        self.context.stages[self.name] = elapsed_ms
        self.context.governor.record_stage(self.name, elapsed_ms)


_governor_instance: Optional[PerformanceGovernor] = None


def get_performance_governor() -> PerformanceGovernor:
    global _governor_instance
    if _governor_instance is None:
        _governor_instance = PerformanceGovernor()
    return _governor_instance
