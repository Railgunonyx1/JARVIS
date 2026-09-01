"""Pure reducer functions for the JARVIS event-sourced core.

Architecture contract:
    new_state = reducer(old_state, event)

Reducers are pure functions:
  - No side effects
  - No I/O
  - No mutation of input state
  - Always return a new SessionState instance

The reducer registry maps event names to handler functions.  The store
calls the matching handler for each event during replay and live append.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from core.core_events import CoreEvent
from core.types import (
    ConfirmationRequest,
    FailureClass,
    Message,
    Mode,
    Plan,
    RiskLevel,
    SessionState,
    StepStatus,
    TaskStatus,
    ToolCallRecord,
    VerificationStatus,
    VerificationStep,
)

# Type alias for a reducer function
Reducer = Callable[[SessionState, CoreEvent], SessionState]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REDUCERS: dict[str, Reducer] = {}


def _on(name: str):
    """Decorator to register a reducer for a specific event name."""
    def decorator(fn: Reducer) -> Reducer:
        _REDUCERS[name] = fn
        return fn
    return decorator


def reduce(state: SessionState, event: CoreEvent) -> SessionState:
    """Dispatch to the matching reducer.  Unknown events pass through unchanged."""
    handler = _REDUCERS.get(event.name)
    if handler is None:
        return state
    return handler(state, event)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(event: CoreEvent) -> float:
    return event.timestamp


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Lifecycle reducers
# ---------------------------------------------------------------------------

@_on("session.started")
def _session_started(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    mode_str = p.get("mode", "agent")
    try:
        mode = Mode(mode_str)
    except ValueError:
        mode = Mode.AGENT
    return SessionState(
        session_id=event.session_id or state.session_id,
        goal=p.get("goal", state.goal),
        mode=mode,
        created_at=_ts(event),
        updated_at=_ts(event),
    )


@_on("task.completed")
def _task_completed(state: SessionState, event: CoreEvent) -> SessionState:
    response = event.payload.get("response", "")
    msg = Message(role="agent", content=response, timestamp=_ts(event))
    return _replace(state,
        status=TaskStatus.COMPLETED,
        messages=state.messages + (msg,),
        status_message="",
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("task.failed")
def _task_failed(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    fc_str = p.get("failure_class", "tool_failure")
    try:
        fc = FailureClass(fc_str)
    except ValueError:
        fc = FailureClass.TOOL_FAILURE
    error = p.get("error", "")
    return _replace(state,
        status=TaskStatus.FAILED,
        failure_class=fc,
        status_message=error[:200],
        updated_at=_ts(event),
        seq=event.seq,
    )


# ---------------------------------------------------------------------------
# State transition reducers
# ---------------------------------------------------------------------------

@_on("task.transitioned")
def _task_transitioned(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    to_str = p.get("to", "")
    try:
        to_status = TaskStatus(to_str)
    except ValueError:
        return state
    return _replace(state,
        status=to_status,
        updated_at=_ts(event),
        seq=event.seq,
    )


# ---------------------------------------------------------------------------
# Plan reducers
# ---------------------------------------------------------------------------

@_on("plan.created")
def _plan_created(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    goal = p.get("goal", state.goal)
    steps_desc = tuple(p.get("steps", []))
    plan = Plan.new(goal, steps_desc)
    return _replace(state,
        plan=plan,
        goal=goal,
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("plan.step_updated")
def _plan_step_updated(state: SessionState, event: CoreEvent) -> SessionState:
    if state.plan is None:
        return state
    p = event.payload
    step_id = p.get("step_id", "")
    status_str = p.get("status", "pending")
    try:
        status = StepStatus(status_str)
    except ValueError:
        return state
    new_plan = state.plan.with_step(step_id, status)
    return _replace(state,
        plan=new_plan,
        updated_at=_ts(event),
        seq=event.seq,
    )


# ---------------------------------------------------------------------------
# Tool reducers
# ---------------------------------------------------------------------------

@_on("tool.started")
def _tool_started(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    record = ToolCallRecord(
        id=p.get("tool_call_id", ""),
        name=p.get("tool", ""),
        arguments=p.get("arguments", ""),
        success=True,
        timestamp=_ts(event),
    )
    return _replace(state,
        tool_calls=state.tool_calls + (record,),
        iteration=state.iteration + 1,
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("tool.completed")
def _tool_completed(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    tool_call_id = p.get("tool_call_id", "")
    # Update the matching record
    new_tool_calls = []
    found = False
    for record in state.tool_calls:
        if record.id == tool_call_id and not found:
            record = ToolCallRecord(
                id=record.id, name=record.name, arguments=record.arguments,
                success=p.get("success", True),
                output=p.get("output", ""),
                error=p.get("error", ""),
                duration_ms=p.get("duration_ms", 0.0),
                timestamp=record.timestamp,
            )
            found = True
        new_tool_calls.append(record)
    if not found:
        # Tool completed without a matching started event
        record = ToolCallRecord(
            id=tool_call_id,
            name=p.get("tool", ""),
            success=p.get("success", True),
            output=p.get("output", ""),
            error=p.get("error", ""),
            duration_ms=p.get("duration_ms", 0.0),
            timestamp=_ts(event),
        )
        new_tool_calls.append(record)

    return _replace(state,
        tool_calls=tuple(new_tool_calls),
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("files.changed")
def _files_changed(state: SessionState, event: CoreEvent) -> SessionState:
    new_files = tuple(event.payload.get("files", []))
    # Merge with existing (deduplicate)
    combined = list(state.files_changed)
    for f in new_files:
        if f not in combined:
            combined.append(f)
    return _replace(state,
        files_changed=tuple(combined),
        updated_at=_ts(event),
        seq=event.seq,
    )


# ---------------------------------------------------------------------------
# Message reducers
# ---------------------------------------------------------------------------

@_on("message.added")
def _message_added(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    msg = Message(
        role=p.get("role", "system"),
        content=p.get("content", ""),
        timestamp=_ts(event),
    )
    return _replace(state,
        messages=state.messages + (msg,),
        updated_at=_ts(event),
        seq=event.seq,
    )


# ---------------------------------------------------------------------------
# Verification reducers
# ---------------------------------------------------------------------------

@_on("verification.started")
def _verification_started(state: SessionState, event: CoreEvent) -> SessionState:
    return _replace(state,
        verification_status=VerificationStatus.RUNNING,
        verification_steps=(),
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("verification.step")
def _verification_step(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    step = VerificationStep(
        name=p.get("name", ""),
        command=p.get("command", ""),
        passed=p.get("passed", False),
        duration_ms=p.get("duration_ms", 0.0),
        error=p.get("error", ""),
    )
    return _replace(state,
        verification_steps=state.verification_steps + (step,),
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("verification.passed")
def _verification_passed(state: SessionState, event: CoreEvent) -> SessionState:
    return _replace(state,
        verification_status=VerificationStatus.PASSED,
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("verification.failed")
def _verification_failed(state: SessionState, event: CoreEvent) -> SessionState:
    failures = event.payload.get("failures", [])
    error_summary = "; ".join(
        f"{f.get('name', '?')}: {f.get('error', '')[:80]}" for f in failures
    ) or "verification failed"
    return _replace(state,
        verification_status=VerificationStatus.FAILED,
        status_message=error_summary[:200],
        updated_at=_ts(event),
        seq=event.seq,
    )


# ---------------------------------------------------------------------------
# Recovery reducers
# ---------------------------------------------------------------------------

@_on("recovery.started")
def _recovery_started(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    return _replace(state,
        status=TaskStatus.RECOVERING,
        recovery_active=True,
        recovery_attempt=p.get("attempt", 1),
        recovery_error=p.get("error", "")[:200],
        verification_status=VerificationStatus.IDLE,
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("recovery.completed")
def _recovery_completed(state: SessionState, event: CoreEvent) -> SessionState:
    return _replace(state,
        recovery_active=False,
        recovery_error="",
        updated_at=_ts(event),
        seq=event.seq,
    )


# ---------------------------------------------------------------------------
# Permission reducers
# ---------------------------------------------------------------------------

@_on("permission.requested")
def _permission_requested(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    try:
        risk = RiskLevel(p.get("risk", "medium"))
    except ValueError:
        risk = RiskLevel.MEDIUM
    req = ConfirmationRequest(
        operation=p.get("operation", ""),
        risk=risk,
        scope=p.get("scope", ""),
        reversible=p.get("reversible", True),
        details=p.get("details", ""),
    )
    return _replace(state,
        pending_confirmation=req,
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("permission.responded")
def _permission_responded(state: SessionState, event: CoreEvent) -> SessionState:
    return _replace(state,
        pending_confirmation=None,
        updated_at=_ts(event),
        seq=event.seq,
    )


# ---------------------------------------------------------------------------
# Token / mode reducers
# ---------------------------------------------------------------------------

@_on("tokens.updated")
def _tokens_updated(state: SessionState, event: CoreEvent) -> SessionState:
    p = event.payload
    return _replace(state,
        tokens_used=p.get("used", state.tokens_used),
        tokens_limit=p.get("limit", state.tokens_limit),
        context_usage_pct=p.get("pct", state.context_usage_pct),
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("mode.changed")
def _mode_changed(state: SessionState, event: CoreEvent) -> SessionState:
    mode_str = event.payload.get("mode", "agent")
    try:
        mode = Mode(mode_str)
    except ValueError:
        return state
    return _replace(state,
        mode=mode,
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("iteration.incremented")
def _iteration_incremented(state: SessionState, event: CoreEvent) -> SessionState:
    iteration = event.payload.get("iteration", state.iteration + 1)
    return _replace(state,
        iteration=iteration,
        updated_at=_ts(event),
        seq=event.seq,
    )


@_on("status.message")
def _status_message(state: SessionState, event: CoreEvent) -> SessionState:
    return _replace(state,
        status_message=event.payload.get("message", ""),
        updated_at=_ts(event),
        seq=event.seq,
    )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _replace(state: SessionState, **kwargs) -> SessionState:
    """Create a new SessionState with overridden fields.

    Uses dataclasses.replace under the hood.  Every keyword argument
    becomes a field override on the new instance.
    """
    from dataclasses import replace as dc_replace
    return dc_replace(state, **kwargs)


# ---------------------------------------------------------------------------
# Exported reducer map (for store initialization)
# ---------------------------------------------------------------------------

def get_reducer_map() -> dict[str, Reducer]:
    """Return the event-name → reducer mapping."""
    return dict(_REDUCERS)
