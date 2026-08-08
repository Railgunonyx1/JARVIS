"""Multi-Stage Reasoning — Use the right model for each stage.

Tiny Router → Medium Planner → Large Reasoner → Tiny Formatter
Most requests never reach the expensive model.
"""
import logging
import time
import threading
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field

logger = logging.getLogger("ai_runtime.multi_stage_reasoning")


@dataclass
class ReasoningStage:
    """A stage in multi-stage reasoning."""
    name: str
    model_tier: str  # "tiny", "small", "medium", "large"
    handler: Callable = None
    latency_ms: float = 0.0
    output: Any = None


@dataclass
class MultiStageResult:
    """Result of multi-stage reasoning."""
    stages_completed: int = 0
    total_stages: int = 0
    final_output: Any = None
    stages_used: List[str] = field(default_factory=list)
    total_latency_ms: float = 0.0
    cost_estimate: float = 0.0


class MultiStageReasoner:
    """Route through multiple model tiers, only using large models when needed.

    Stage 1: Tiny model classifies intent (100ms, free)
    Stage 2: Medium model plans approach (200ms, cheap)
    Stage 3: Large model reasons only if needed (500ms, expensive)
    Stage 4: Tiny model formats output (50ms, free)
    """

    DEFAULT_PIPELINE = [
        ReasoningStage(name="classify", model_tier="tiny"),
        ReasoningStage(name="plan", model_tier="medium"),
        ReasoningStage(name="reason", model_tier="medium"),
        ReasoningStage(name="format", model_tier="tiny"),
    ]

    # Complexity thresholds: skip expensive stages if simple
    SKIP_REASONING_THRESHOLD = 0.4

    def __init__(self, pipeline: List[ReasoningStage] = None):
        self._pipeline = pipeline or list(self.DEFAULT_PIPELINE)
        self._lock = threading.Lock()
        self._stats = {
            "total_runs": 0,
            "full_pipeline_runs": 0,
            "short_circuit_runs": 0,
            "avg_latency_ms": 0.0,
            "avg_stages_used": 0.0,
        }

    async def reason(self, query: str, complexity: float = 0.5,
                     handlers: Dict[str, Callable] = None) -> MultiStageResult:
        """Run multi-stage reasoning on a query."""
        start = time.time()
        result = MultiStageResult(total_stages=len(self._pipeline))
        handlers = handlers or {}

        current_input = query
        for stage in self._pipeline:
            # Short-circuit: skip reasoning stage if simple
            if stage.name == "reason" and complexity < self.SKIP_REASONING_THRESHOLD:
                result.stages_used.append(f"{stage.name}(skipped)")
                continue

            handler = handlers.get(stage.name) or stage.handler
            if handler:
                stage_start = time.time()
                try:
                    output = await handler(current_input) if hasattr(handler, '__call__') else None
                    stage.output = output
                    current_input = output or current_input
                except Exception as e:
                    logger.debug("Stage %s failed: %s", stage.name, e)
                    stage.output = current_input
                stage.latency_ms = (time.time() - stage_start) * 1000
            else:
                stage.output = current_input

            result.stages_completed += 1
            result.stages_used.append(f"{stage.name}({stage.model_tier})")

        result.final_output = current_input
        result.total_latency_ms = (time.time() - start) * 1000

        with self._lock:
            self._stats["total_runs"] += 1
            if len(result.stages_used) == len(self._pipeline):
                self._stats["full_pipeline_runs"] += 1
            else:
                self._stats["short_circuit_runs"] += 1
            n = self._stats["total_runs"]
            self._stats["avg_latency_ms"] = (
                (self._stats["avg_latency_ms"] * (n - 1) + result.total_latency_ms) / n
            )
            self._stats["avg_stages_used"] = (
                (self._stats["avg_stages_used"] * (n - 1) + len(result.stages_used)) / n
            )

        return result

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._stats)


_multi_stage_instance: Optional[MultiStageReasoner] = None


def get_multi_stage_reasoner() -> MultiStageReasoner:
    global _multi_stage_instance
    if _multi_stage_instance is None:
        _multi_stage_instance = MultiStageReasoner()
    return _multi_stage_instance
