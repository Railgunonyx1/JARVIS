"""AgentState — mutable per-task state for the agent loop.

Includes a formal task status state machine:

    CREATED → CLASSIFYING → PLANNING → EXECUTING → OBSERVING → VERIFYING → COMPLETED

Failure paths:
    → RECOVERING → EXECUTING (retry with context)
    → ROLLED_BACK → FAILED
    → BLOCKED → FAILED
    → FAILED
    → CANCELLED
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    CREATED = "created"
    CLASSIFYING = "classifying"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class FailureClass(StrEnum):
    """Deterministic failure classification with explicit precedence.

    Precedence (highest first):
        CANCELLED > TIMEOUT > PERMISSION_DENIED > MALFORMED_TOOL
        > CONTEXT_OVERFLOW > PROVIDER_FAILURE > MODEL_FAILURE > TOOL_FAILURE
    """
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    MALFORMED_TOOL = "malformed_tool"
    CONTEXT_OVERFLOW = "context_overflow"
    PROVIDER_FAILURE = "provider_failure"
    MODEL_FAILURE = "model_failure"
    TOOL_FAILURE = "tool_failure"


class TerminalReason(StrEnum):
    """Why the task stopped. Not a failure class -- a termination reason."""
    VERIFICATION_FAIL = "verification_fail"
    MAX_ITERATIONS = "max_iterations"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


_FAILURE_PRECEDENCE: dict[FailureClass, int] = {
    FailureClass.CANCELLED: 0,
    FailureClass.TIMEOUT: 1,
    FailureClass.PERMISSION_DENIED: 2,
    FailureClass.MALFORMED_TOOL: 3,
    FailureClass.CONTEXT_OVERFLOW: 4,
    FailureClass.PROVIDER_FAILURE: 5,
    FailureClass.MODEL_FAILURE: 6,
    FailureClass.TOOL_FAILURE: 7,
}


def classify_failure(error: str, *, is_timeout: bool = False,
                     is_permission: bool = False, is_verification: bool = False,
                     is_cancelled: bool = False, is_context_overflow: bool = False,
                     is_provider: bool = False) -> FailureClass:
    """Deterministic failure classification. Always returns the highest-precedence match."""
    if is_cancelled:
        return FailureClass.CANCELLED
    if is_timeout:
        return FailureClass.TIMEOUT
    if is_permission:
        return FailureClass.PERMISSION_DENIED
    if is_context_overflow:
        return FailureClass.CONTEXT_OVERFLOW
    if is_provider:
        return FailureClass.PROVIDER_FAILURE
    err = error.lower()
    if "not registered" in err or "unknown tool" in err:
        return FailureClass.MALFORMED_TOOL
    return FailureClass.TOOL_FAILURE


def pick_worst_failure(a: FailureClass | None, b: FailureClass | None) -> FailureClass | None:
    """Return the higher-precedence (lower index) of two failure classes."""
    if a is None:
        return b
    if b is None:
        return a
    return a if _FAILURE_PRECEDENCE[a] <= _FAILURE_PRECEDENCE[b] else b


# Valid transitions: from → set of allowed destinations
_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.CLASSIFYING, TaskStatus.PLANNING, TaskStatus.CANCELLED},
    TaskStatus.CLASSIFYING: {TaskStatus.PLANNING, TaskStatus.EXECUTING, TaskStatus.CANCELLED},
    TaskStatus.PLANNING: {TaskStatus.EXECUTING, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.EXECUTING: {
        TaskStatus.OBSERVING, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED,
    },
    TaskStatus.OBSERVING: {
        TaskStatus.VERIFYING, TaskStatus.EXECUTING, TaskStatus.FAILED, TaskStatus.CANCELLED,
    },
    TaskStatus.VERIFYING: {
        TaskStatus.COMPLETED, TaskStatus.RECOVERING, TaskStatus.FAILED,
        TaskStatus.ROLLED_BACK, TaskStatus.CANCELLED,
    },
    TaskStatus.RECOVERING: {
        TaskStatus.EXECUTING, TaskStatus.FAILED, TaskStatus.ROLLED_BACK, TaskStatus.CANCELLED,
    },
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
    failure_class: FailureClass | None = None
    terminal_reason: TerminalReason | None = None
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
            "failure_class": self.failure_class.value if self.failure_class else None,
            "terminal_reason": self.terminal_reason.value if self.terminal_reason else None,
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
