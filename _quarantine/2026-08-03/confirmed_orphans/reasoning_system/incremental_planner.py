"""Incremental Planning — Generate next step while executing current one.

Instead of generating a complete plan upfront:
  Step 1 → Execute → Step 2 → Execute → Step 3

Reduces waiting before execution begins.
"""
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger("reasoning_system.incremental_planner")


class StepState(Enum):
    PENDING = auto()
    GENERATING = auto()
    READY = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class PlanStep:
    """A single step in an incremental plan."""
    index: int
    description: str
    state: StepState = StepState.PENDING
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def latency_ms(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return 0.0


@dataclass
class IncrementalPlan:
    """An incrementally-generated plan."""
    plan_id: str
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    current_index: int = 0
    is_complete: bool = False
    created_at: float = 0.0


class IncrementalPlanner:
    """Plan the next step while executing the current one.

    Overlaps planning latency with execution latency:
    - Step 1 executing
    - Step 2 being generated
    - Step 3 not yet needed
    """

    def __init__(self, llm_fn: Callable = None, planner_fn: Callable = None):
        self._llm_fn = llm_fn
        self._planner_fn = planner_fn
        self._active_plan: IncrementalPlan | None = None
        self._lock = threading.Lock()
        self._plans_created = 0
        self._steps_executed = 0

    def start_plan(self, goal: str) -> IncrementalPlan:
        """Start a new incremental plan."""
        self._plans_created += 1
        plan = IncrementalPlan(
            plan_id=f"incplan_{self._plans_created}",
            goal=goal,
            created_at=time.time(),
        )
        with self._lock:
            self._active_plan = plan
        return plan

    def add_step(self, description: str, tool_name: str = "",
                 tool_args: dict[str, Any] = None) -> PlanStep:
        """Add a step to the active plan."""
        with self._lock:
            plan = self._active_plan
            if plan is None:
                return None

            step = PlanStep(
                index=len(plan.steps),
                description=description,
                tool_name=tool_name,
                tool_args=tool_args or {},
                state=StepState.READY,
            )
            plan.steps.append(step)
            return step

    def get_next_step(self) -> PlanStep | None:
        """Get the next step that hasn't been executed yet."""
        with self._lock:
            plan = self._active_plan
            if plan is None:
                return None
            for step in plan.steps:
                if step.state == StepState.PENDING or step.state == StepState.READY:
                    return step
            return None

    def mark_step_running(self, index: int) -> None:
        with self._lock:
            plan = self._active_plan
            if plan and index < len(plan.steps):
                plan.steps[index].state = StepState.RUNNING
                plan.steps[index].started_at = time.time()

    def mark_step_completed(self, index: int, result: Any = None) -> None:
        with self._lock:
            plan = self._active_plan
            if plan and index < len(plan.steps):
                plan.steps[index].state = StepState.COMPLETED
                plan.steps[index].result = result
                plan.steps[index].completed_at = time.time()
                plan.current_index = index + 1
                self._steps_executed += 1

    def mark_step_failed(self, index: int, error: str = "") -> None:
        with self._lock:
            plan = self._active_plan
            if plan and index < len(plan.steps):
                plan.steps[index].state = StepState.FAILED
                plan.steps[index].error = error
                plan.steps[index].completed_at = time.time()

    def complete_plan(self) -> None:
        with self._lock:
            if self._active_plan:
                self._active_plan.is_complete = True

    def get_progress(self) -> dict[str, Any]:
        with self._lock:
            plan = self._active_plan
            if plan is None:
                return {"active": False}
            total = len(plan.steps)
            completed = sum(1 for s in plan.steps if s.state == StepState.COMPLETED)
            failed = sum(1 for s in plan.steps if s.state == StepState.FAILED)
            return {
                "active": True,
                "plan_id": plan.plan_id,
                "total_steps": total,
                "completed": completed,
                "failed": failed,
                "current_index": plan.current_index,
                "progress_pct": round(completed / max(total, 1) * 100, 1),
                "is_complete": plan.is_complete,
            }

    def get_plan(self) -> dict[str, Any] | None:
        with self._lock:
            plan = self._active_plan
            if plan is None:
                return None
            return {
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "steps": [
                    {
                        "index": s.index,
                        "description": s.description,
                        "state": s.state.name,
                        "tool": s.tool_name,
                        "latency_ms": round(s.latency_ms, 1),
                    }
                    for s in plan.steps
                ],
                "progress": self.get_progress(),
            }

    def get_stats(self) -> dict[str, Any]:
        return {
            "plans_created": self._plans_created,
            "steps_executed": self._steps_executed,
            "has_active_plan": self._active_plan is not None and not self._active_plan.is_complete,
        }


_incremental_instance: IncrementalPlanner | None = None


def get_incremental_planner(llm_fn=None) -> IncrementalPlanner:
    global _incremental_instance
    if _incremental_instance is None:
        _incremental_instance = IncrementalPlanner(llm_fn=llm_fn)
    return _incremental_instance
