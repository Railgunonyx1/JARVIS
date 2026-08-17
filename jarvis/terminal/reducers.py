"""Sprint 9C — Pure reducers: (state, event) → new state.

Every reducer is a pure function.  They never mutate the incoming state;
they return a new frozen SessionState.
"""

from __future__ import annotations

from typing import Any

from jarvis.terminal.events import EventType, TerminalEvent
from jarvis.terminal.types import (
    ActivityEvent,
    ConfirmationRequest,
    LayoutMode,
    Message,
    Plan,
    PlanStep,
    SessionState,
    SessionStatus,
    StepStatus,
    ToolRun,
    _now,
)


def reduce(state: SessionState, event: TerminalEvent) -> SessionState:
    """Top-level dispatcher — routes to the right reducer by event type."""
    handler = _DISPATCHERS.get(event.type)
    if handler is None:
        return state
    return handler(state, event)


# ── Individual reducers ─────────────────────────────────────────────────


def _session_started(state: SessionState, event: TerminalEvent) -> SessionState:
    return SessionState(
        status=SessionStatus.RUNNING,
        session_id=event.payload.get("session_id", state.session_id),
        created_at=state.created_at,
        updated_at=_now(),
    )


def _session_idle(state: SessionState, _event: TerminalEvent) -> SessionState:
    return SessionState(
        status=SessionStatus.IDLE,
        layout=state.layout,
        model=state.model,
        provider=state.provider,
        tokens_prompt=state.tokens_prompt,
        tokens_completion=state.tokens_completion,
        latency_ms=state.latency_ms,
        plan=state.plan,
        messages=state.messages,
        activity=state.activity,
        code_files=state.code_files,
        memory_hits=state.memory_hits,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _session_error(state: SessionState, event: TerminalEvent) -> SessionState:
    return SessionState(
        status=SessionStatus.ERROR,
        error=event.payload.get("error", "unknown error"),
        layout=state.layout,
        model=state.model,
        provider=state.provider,
        plan=state.plan,
        messages=state.messages,
        activity=state.activity,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _plan_created(state: SessionState, event: TerminalEvent) -> SessionState:
    goal = event.payload.get("goal", "")
    steps_raw = event.payload.get("steps", [])
    steps = tuple(PlanStep(description=s, id=f"step-{i}") for i, s in enumerate(steps_raw))
    return SessionState(
        status=state.status,
        layout=LayoutMode.PLAN,
        model=state.model,
        provider=state.provider,
        plan=Plan(goal=goal, steps=steps),
        messages=state.messages,
        activity=state.activity,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _plan_step_started(state: SessionState, event: TerminalEvent) -> SessionState:
    step_id = event.payload.get("step_id", "")
    new_steps = []
    for s in state.plan.steps:
        if s.id == step_id:
            new_steps.append(PlanStep(
                id=s.id, description=s.description,
                status=StepStatus.RUNNING, tool_runs=s.tool_runs,
            ))
        else:
            new_steps.append(s)
    return SessionState(
        status=state.status,
        layout=state.layout,
        model=state.model,
        provider=state.provider,
        plan=Plan(goal=state.plan.goal, steps=tuple(new_steps)),
        messages=state.messages,
        activity=state.activity,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _plan_step_completed(state: SessionState, event: TerminalEvent) -> SessionState:
    step_id = event.payload.get("step_id", "")
    new_steps = []
    for s in state.plan.steps:
        if s.id == step_id:
            new_steps.append(PlanStep(
                id=s.id, description=s.description,
                status=StepStatus.COMPLETED, tool_runs=s.tool_runs,
            ))
        else:
            new_steps.append(s)
    return SessionState(
        status=state.status,
        layout=state.layout,
        model=state.model,
        provider=state.provider,
        plan=Plan(goal=state.plan.goal, steps=tuple(new_steps)),
        messages=state.messages,
        activity=state.activity,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _tool_executed(state: SessionState, event: TerminalEvent) -> SessionState:
    step_id = event.payload.get("step_id", "")
    tool = ToolRun(
        name=event.payload.get("tool_name", ""),
        args=event.payload.get("args", {}),
        status=StepStatus.COMPLETED,
        result=event.payload.get("result", ""),
        duration_ms=event.payload.get("duration_ms", 0.0),
    )
    new_steps = []
    for s in state.plan.steps:
        if s.id == step_id:
            new_steps.append(PlanStep(
                id=s.id, description=s.description,
                status=s.status, tool_runs=s.tool_runs + (tool,),
            ))
        else:
            new_steps.append(s)
    activity = state.activity + (ActivityEvent(
        name="tool.executed",
        payload={"tool": tool.name, "duration_ms": tool.duration_ms},
    ),)
    return SessionState(
        status=state.status,
        layout=state.layout,
        model=state.model,
        provider=state.provider,
        tokens_prompt=event.payload.get("tokens_prompt", state.tokens_prompt),
        tokens_completion=event.payload.get("tokens_completion", state.tokens_completion),
        latency_ms=event.payload.get("latency_ms", state.latency_ms),
        plan=Plan(goal=state.plan.goal, steps=tuple(new_steps)),
        messages=state.messages,
        activity=activity,
        code_files=state.code_files,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _message_added(state: SessionState, event: TerminalEvent) -> SessionState:
    msg = Message(
        role=event.payload.get("role", "user"),
        content=event.payload.get("content", ""),
    )
    return SessionState(
        status=state.status,
        layout=state.layout,
        model=state.model,
        provider=state.provider,
        plan=state.plan,
        messages=state.messages + (msg,),
        activity=state.activity,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _stream_chunk(state: SessionState, event: TerminalEvent) -> SessionState:
    chunk = event.payload.get("chunk", "")
    if not chunk:
        return state
    existing = state.messages[-1] if state.messages and state.messages[-1].role == "assistant" else None
    if existing:
        merged = Message(
            id=existing.id, role="assistant",
            content=existing.content + chunk,
            timestamp=existing.timestamp,
        )
        msgs = state.messages[:-1] + (merged,)
    else:
        msgs = state.messages + (Message(role="assistant", content=chunk),)
    return SessionState(
        status=state.status,
        layout=state.layout,
        model=state.model,
        provider=state.provider,
        plan=state.plan,
        messages=msgs,
        activity=state.activity,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _stream_done(state: SessionState, _event: TerminalEvent) -> SessionState:
    return state


def _layout_changed(state: SessionState, event: TerminalEvent) -> SessionState:
    mode = event.payload.get("mode")
    try:
        layout = LayoutMode(mode) if mode else state.layout
    except ValueError:
        layout = state.layout
    return SessionState(
        status=state.status,
        layout=layout,
        model=state.model,
        provider=state.provider,
        plan=state.plan,
        messages=state.messages,
        activity=state.activity,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _confirmation_requested(state: SessionState, event: TerminalEvent) -> SessionState:
    from jarvis.terminal.types import RiskLevel
    req = ConfirmationRequest(
        tool_name=event.payload.get("tool_name", ""),
        description=event.payload.get("description", ""),
        risk_level=RiskLevel(event.payload.get("risk_level", "low")),
    )
    return SessionState(
        status=SessionStatus.WAITING_CONFIRM,
        layout=state.layout,
        model=state.model,
        provider=state.provider,
        plan=state.plan,
        messages=state.messages,
        activity=state.activity,
        pending_confirmation=req,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


def _provider_switched(state: SessionState, event: TerminalEvent) -> SessionState:
    return SessionState(
        status=state.status,
        layout=state.layout,
        model=event.payload.get("model", state.model),
        provider=event.payload.get("provider", state.provider),
        plan=state.plan,
        messages=state.messages,
        activity=state.activity,
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=_now(),
    )


_DISPATCHERS = {
    EventType.SESSION_STARTED: _session_started,
    EventType.SESSION_IDLE: _session_idle,
    EventType.SESSION_ERROR: _session_error,
    EventType.PLAN_CREATED: _plan_created,
    EventType.PLAN_STEP_STARTED: _plan_step_started,
    EventType.PLAN_STEP_COMPLETED: _plan_step_completed,
    EventType.TOOL_EXECUTED: _tool_executed,
    EventType.MESSAGE_ADDED: _message_added,
    EventType.STREAM_CHUNK: _stream_chunk,
    EventType.STREAM_DONE: _stream_done,
    EventType.LAYOUT_CHANGED: _layout_changed,
    EventType.CONFIRMATION_REQUESTED: _confirmation_requested,
    EventType.PROVIDER_SWITCHED: _provider_switched,
}
