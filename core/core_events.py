"""Versioned events for the JARVIS event-sourced core.

Every event carries:
  - seq: monotonic sequence number (replay ordering)
  - schema_version: forward-compatible evolution
  - session_id: which session this belongs to
  - timestamp: wall-clock time
  - payload: sanitized data safe for the renderer

Events are immutable.  Reducers consume them; nothing mutates them.
The bus (runtime/event_bus.py) still carries BusEvent wrappers; these
CoreEvent types are the *payload* that lives inside BusEvent.payload["core"].
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.types import (
    ConfirmationRequest,
    FailureClass,
    Mode,
    StepStatus,
    TaskStatus,
)

# ---------------------------------------------------------------------------
# Schema version — bump when CoreEvent shape changes
# ---------------------------------------------------------------------------

CURRENT_SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Event categories
# ---------------------------------------------------------------------------

class EventCategory(StrEnum):
    LIFECYCLE = "lifecycle"    # session/task start/finish/fail
    STATE = "state"            # status transitions
    PLAN = "plan"              # plan creation, step updates
    TOOL = "tool"              # tool execution
    MESSAGE = "message"        # conversation turns
    VERIFICATION = "verification"  # verification gate
    RECOVERY = "recovery"      # recovery attempts
    PERMISSION = "permission"  # permission requests
    TOKEN = "token"            # token accounting
    MODE = "mode"              # mode changes
    SYSTEM = "system"          # misc system events


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CoreEvent:
    """Base for all versioned core events.  Immutable."""
    seq: int
    category: EventCategory
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)
    schema_version: int = CURRENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Factory helpers — typed constructors for each event kind
# ---------------------------------------------------------------------------

def session_started(session_id: str, goal: str, mode: str = "agent") -> CoreEvent:
    return CoreEvent(
        seq=0, category=EventCategory.LIFECYCLE, name="session.started",
        payload={"goal": goal, "mode": mode}, session_id=session_id,
    )


def task_transitioned(session_id: str, seq: int, from_status: TaskStatus,
                       to_status: TaskStatus) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.STATE, name="task.transitioned",
        payload={"from": from_status.value, "to": to_status.value},
        session_id=session_id,
    )


def task_failed(session_id: str, seq: int, failure_class: FailureClass | str,
                error: str = "") -> CoreEvent:
    fc_val = failure_class.value if isinstance(failure_class, FailureClass) else failure_class
    return CoreEvent(
        seq=seq, category=EventCategory.STATE, name="task.failed",
        payload={"failure_class": fc_val, "error": error[:500]},
        session_id=session_id,
    )


def task_completed(session_id: str, seq: int, response: str = "") -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.LIFECYCLE, name="task.completed",
        payload={"response": response[:2000]}, session_id=session_id,
    )


def plan_created(session_id: str, seq: int, goal: str,
                 step_descriptions: tuple[str, ...]) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.PLAN, name="plan.created",
        payload={"goal": goal, "steps": list(step_descriptions)},
        session_id=session_id,
    )


def plan_step_updated(session_id: str, seq: int, step_id: str,
                       status: StepStatus | str) -> CoreEvent:
    st_val = status.value if isinstance(status, StepStatus) else status
    return CoreEvent(
        seq=seq, category=EventCategory.PLAN, name="plan.step_updated",
        payload={"step_id": step_id, "status": st_val},
        session_id=session_id,
    )


def tool_started(session_id: str, seq: int, tool_name: str,
                 arguments: str = "", tool_call_id: str = "") -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.TOOL, name="tool.started",
        payload={
            "tool": tool_name,
            "arguments": arguments[:500],
            "tool_call_id": tool_call_id or str(uuid.uuid4())[:8],
        },
        session_id=session_id,
    )


def tool_completed(session_id: str, seq: int, tool_name: str,
                    tool_call_id: str, success: bool, output: str = "",
                    error: str = "", duration_ms: float = 0.0) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.TOOL, name="tool.completed",
        payload={
            "tool": tool_name,
            "tool_call_id": tool_call_id,
            "success": success,
            "output": output[:1000],
            "error": error[:500],
            "duration_ms": round(duration_ms, 1),
        },
        session_id=session_id,
    )


def message_added(session_id: str, seq: int, role: str,
                  content: str) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.MESSAGE, name="message.added",
        payload={"role": role, "content": content[:5000]},
        session_id=session_id,
    )


def verification_started(session_id: str, seq: int) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.VERIFICATION,
        name="verification.started", session_id=session_id,
    )


def verification_step(session_id: str, seq: int, name: str,
                       passed: bool, duration_ms: float = 0.0,
                       command: str = "", error: str = "") -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.VERIFICATION,
        name="verification.step",
        payload={
            "name": name, "passed": passed,
            "duration_ms": round(duration_ms, 1),
            "command": command[:200], "error": error[:500],
        },
        session_id=session_id,
    )


def verification_passed(session_id: str, seq: int) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.VERIFICATION,
        name="verification.passed", session_id=session_id,
    )


def verification_failed(session_id: str, seq: int,
                         failures: list[dict[str, str]] | None = None) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.VERIFICATION,
        name="verification.failed",
        payload={"failures": (failures or [])[:10]},
        session_id=session_id,
    )


def recovery_started(session_id: str, seq: int, attempt: int,
                      error: str = "") -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.RECOVERY, name="recovery.started",
        payload={"attempt": attempt, "error": error[:500]},
        session_id=session_id,
    )


def recovery_completed(session_id: str, seq: int) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.RECOVERY, name="recovery.completed",
        session_id=session_id,
    )


def permission_requested(session_id: str, seq: int,
                          request: ConfirmationRequest) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.PERMISSION,
        name="permission.requested",
        payload={
            "operation": request.operation,
            "risk": request.risk.value,
            "scope": request.scope,
            "reversible": request.reversible,
            "details": request.details[:300],
        },
        session_id=session_id,
    )


def permission_responded(session_id: str, seq: int, operation: str,
                          decision: str) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.PERMISSION,
        name="permission.responded",
        payload={"operation": operation, "decision": decision},
        session_id=session_id,
    )


def tokens_updated(session_id: str, seq: int, used: int,
                    limit: int, pct: float) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.TOKEN, name="tokens.updated",
        payload={"used": used, "limit": limit, "pct": round(pct, 2)},
        session_id=session_id,
    )


def mode_changed(session_id: str, seq: int, mode: Mode) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.MODE, name="mode.changed",
        payload={"mode": mode.value}, session_id=session_id,
    )


def iteration_incremented(session_id: str, seq: int, iteration: int) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.STATE, name="iteration.incremented",
        payload={"iteration": iteration}, session_id=session_id,
    )


def files_changed(session_id: str, seq: int,
                   files: tuple[str, ...]) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.TOOL, name="files.changed",
        payload={"files": list(files)[:50]}, session_id=session_id,
    )


def status_message(session_id: str, seq: int, message: str) -> CoreEvent:
    return CoreEvent(
        seq=seq, category=EventCategory.SYSTEM, name="status.message",
        payload={"message": message[:200]}, session_id=session_id,
    )
