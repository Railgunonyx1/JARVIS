"""TaskObserver — live progress/timeline tracker for agent runs.

Gives the terminal renderer (and any subscriber) a structured, real-time
view of a running task: steps, tool calls, permissions, failures, token
usage, iterations, and elapsed time. Evolves the legacy TaskManager into
a purpose-built observer for the AgentLoop — no transcript rewriting, no
duplicate audit store. The DecisionLogger remains the persistence layer;
this module is the in-memory, observable timeline.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core import events

EventCallback = Callable[[str, Dict[str, Any]], None]


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StepRecord:
    """One tool-execution step in the task timeline."""

    index: int
    tool: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    duration_ms: float = 0.0
    status: str = "running"  # running | ok | error | denied
    error: str = ""
    tool_call_id: str = ""


@dataclass
class TaskObservation:
    """Snapshot of a single task run, built incrementally by TaskObserver."""

    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    steps: List[StepRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    files_changed: List[str] = field(default_factory=list)
    tokens_used: int = 0
    iterations: int = 0
    provider: str = ""
    model: str = ""
    response: str = ""

    @property
    def duration_ms(self) -> float:
        end = self.finished_at or time.time()
        return round((end - self.started_at) * 1000, 1)

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        done = [s for s in self.steps if s.status != "running"]
        return round(len(done) / len(self.steps), 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "progress": self.progress,
            "iterations": self.iterations,
            "tokens_used": self.tokens_used,
            "provider": self.provider,
            "model": self.model,
            "errors": list(self.errors),
            "files_changed": list(self.files_changed),
            "steps": [s.__dict__ for s in self.steps],
            "response": self.response,
        }


class TaskObserver:
    """Collects a structured timeline for one agent run and notifies subscribers.

    Subscribe by passing ``on_event`` (event name, payload) at construction —
    the Phase B terminal renderer and other frontends attach here. One
    observer instance tracks one task at a time; ``start()`` resets it for the
    next goal.
    """

    def __init__(self, on_event: Optional[EventCallback] = None) -> None:
        self._on_event = on_event
        self.observation: Optional[TaskObservation] = None

    @property
    def is_finished(self) -> bool:
        if self.observation is None:
            return False
        return self.observation.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )

    def start(self, task_id: str, goal: str) -> TaskObservation:
        self.observation = TaskObservation(task_id=task_id, goal=goal)
        self._emit(events.TASK_STARTED, {"task_id": task_id, "goal": goal})
        return self.observation

    def step_started(self, tool: str, arguments: Dict[str, Any],
                     tool_call_id: str = "") -> StepRecord:
        obs = self._obs()
        step = StepRecord(
            index=len(obs.steps),
            tool=tool,
            arguments=dict(arguments or {}),
            started_at=time.time(),
            tool_call_id=tool_call_id,
        )
        obs.steps.append(step)
        self._emit(events.STEP_STARTED, {
            "task_id": obs.task_id, "step": step.index, "tool": tool,
        })
        return step

    def step_finished(self, step: StepRecord, status: str, duration_ms: float,
                      error: str = "") -> None:
        step.status = status
        step.duration_ms = round(duration_ms, 1)
        step.error = error
        obs = self._obs()
        if status == "error" and error:
            obs.errors.append(error)
        self._emit(events.STEP_COMPLETED, {
            "task_id": obs.task_id, "step": step.index, "tool": step.tool,
            "status": status, "duration_ms": step.duration_ms, "error": error,
        })

    def observe_permission(self, tool: str, allowed: bool, reason: str = "") -> None:
        obs = self._obs()
        self._emit(events.PERMISSION_OBSERVED, {
            "task_id": obs.task_id, "tool": tool, "allowed": allowed, "reason": reason,
        })

    def observe_error(self, message: str) -> None:
        obs = self._obs()
        obs.errors.append(message)
        self._emit(events.STEP_FAILED, {"task_id": obs.task_id, "error": message})

    def finish(self, status: TaskStatus, response: str = "", provider: str = "",
               model: str = "", tokens: int = 0, iterations: int = 0,
               files_changed: Optional[List[str]] = None) -> None:
        obs = self._obs()
        obs.status = status
        obs.response = response
        obs.provider = provider
        obs.model = model
        obs.tokens_used = tokens
        obs.iterations = iterations
        obs.finished_at = time.time()
        if files_changed:
            obs.files_changed = list(files_changed)
        self._emit(events.TASK_FINISHED, {
            "task_id": obs.task_id,
            "status": status.value,
            "duration_ms": obs.duration_ms,
            "tokens": tokens,
            "iterations": iterations,
            "progress": obs.progress,
        })

    def cancel(self) -> None:
        obs = self._obs()
        obs.status = TaskStatus.CANCELLED
        obs.finished_at = time.time()
        self._emit(events.TASK_CANCELLED, {"task_id": obs.task_id})

    def summary(self) -> Dict[str, Any]:
        return self._obs().to_dict()

    def _obs(self) -> TaskObservation:
        if self.observation is None:
            raise RuntimeError("TaskObserver.start() must be called first")
        return self.observation

    def _emit(self, event: str, payload: Dict[str, Any]) -> None:
        # The public `on_event` attribute is authoritative when set (CLI,
        # daemon, LiveTaskDisplay all assign it); the constructor param
        # `_on_event` is the fallback.
        callback = getattr(self, "on_event", None) or self._on_event
        if callback:
            try:
                callback(event, payload)
            except Exception:
                pass
