"""AgentState — mutable per-task state for the agent loop.

Includes a formal task status state machine:

    CREATED → CLASSIFYING → PLANNING → EXECUTING → OBSERVING → VERIFYING → COMPLETED

Failure paths:
    → BLOCKED → ROLLED_BACK
    → FAILED
    → CANCELLED
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    CREATED = "created"
    CLASSIFYING = "classifying"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


# Valid transitions: from → set of allowed destinations
_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.CLASSIFYING, TaskStatus.PLANNING, TaskStatus.CANCELLED},
    TaskStatus.CLASSIFYING: {TaskStatus.PLANNING, TaskStatus.EXECUTING, TaskStatus.CANCELLED},
    TaskStatus.PLANNING: {TaskStatus.EXECUTING, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.EXECUTING: {TaskStatus.OBSERVING, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.OBSERVING: {TaskStatus.VERIFYING, TaskStatus.EXECUTING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.VERIFYING: {TaskStatus.COMPLETED, TaskStatus.EXECUTING, TaskStatus.FAILED, TaskStatus.ROLLED_BACK, TaskStatus.CANCELLED},
    TaskStatus.BLOCKED: {TaskStatus.EXECUTING, TaskStatus.CANCELLED},
    TaskStatus.ROLLED_BACK: {TaskStatus.FAILED, TaskStatus.EXECUTING},
    # Terminal states
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


@dataclass
class AgentState:
    """Live state for one agent task run."""

    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.CREATED
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tokens_used: int = 0
    start_time: float = field(default_factory=time.time)
    iteration: int = 0
    provider: str = ""
    model: str = ""
    context_usage: dict[str, Any] = field(default_factory=dict)
    _status_history: list[tuple[str, float]] = field(default_factory=list, repr=False)

    def transition(self, new_status: TaskStatus) -> None:
        """Validate and apply a state transition. Raises ValueError on illegal transition."""
        allowed = _TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Illegal transition: {self.status.value} → {new_status.value}. "
                f"Allowed: {sorted(s.value for s in allowed)}"
            )
        self._status_history.append((self.status.value, time.time()))
        self.status = new_status

    def record_tool(self, name: str, tool_call_id: str, success: bool,
                    duration_ms: float, output: str = "", error: str = "",
                    metadata: dict[str, Any] | None = None) -> None:
        entry = {
            "id": tool_call_id,
            "name": name,
            "success": success,
            "duration_ms": round(duration_ms, 1),
            "output": (output or "")[:160],
        }
        diff = (metadata or {}).get("diff")
        if diff:
            entry["diff"] = diff[:800]
        self.tool_calls.append(entry)
        if not success and error:
            self.errors.append(error)

    def add_tokens(self, prompt: int, completion: int) -> None:
        self.tokens_used += prompt + completion

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "tool_calls": self.tool_calls,
            "files_changed": self.files_changed,
            "errors": self.errors,
            "tokens_used": self.tokens_used,
            "iteration": self.iteration,
            "provider": self.provider,
            "model": self.model,
            "context_usage": self.context_usage,
            "duration_ms": round((time.time() - self.start_time) * 1000, 1),
        }
