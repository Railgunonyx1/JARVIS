"""Canonical Event Envelope — single event type for all inter-module communication.

BusEvent (from runtime.event_bus) is the one canonical event type.
TerminalEvent is a thin convenience adapter that creates a BusEvent with
source="terminal" and name derived from EventType.

Architecture contract:
    Terminal UI -> UIIntent -> IntentRouter -> BusEvent -> Event Bus -> Core Kernel
    Core Kernel -> BusEvent -> Event Bus -> Terminal Store (reducer)
"""

from __future__ import annotations

import enum
from typing import Any

from runtime.event_bus import BusEvent


class EventType(enum.Enum):
    """Canonical event names.  BusEvent.name should use the string value."""
    SESSION_STARTED = "session.started"
    SESSION_IDLE = "session.idle"
    SESSION_ERROR = "session.error"
    PLAN_CREATED = "plan.created"
    PLAN_STEP_STARTED = "plan.step.started"
    PLAN_STEP_COMPLETED = "plan.step.completed"
    PLAN_STEP_FAILED = "plan.step.failed"
    TOOL_REQUESTED = "tool.requested"
    TOOL_EXECUTED = "tool.executed"
    TOOL_FAILED = "tool.failed"
    CONFIRMATION_REQUESTED = "confirmation.requested"
    CONFIRMATION_RESPONDED = "confirmation.responded"
    MESSAGE_ADDED = "message.added"
    STREAM_CHUNK = "stream.chunk"
    STREAM_DONE = "stream.done"
    PROVIDER_SWITCHED = "provider.switched"
    PROVIDER_ERROR = "provider.error"
    LAYOUT_CHANGED = "layout.changed"
    ACTIVITY_EVENT = "activity.event"
    CODE_FILE_OPENED = "code.file.opened"
    MEMORY_LOADED = "memory.loaded"
    BREAKPOINT_HIT = "breakpoint.hit"
    # Intent-originated events (terminal -> core)
    INTENT_SUBMITTED = "intent.submitted"
    INTENT_CANCEL = "intent.cancel"
    INTENT_CONFIRM = "intent.confirm"
    INTENT_LAYOUT = "intent.layout"
    INTENT_MODEL_SWITCH = "intent.model_switch"
    INTENT_PROVIDER_SWITCH = "intent.provider_switch"
    INTENT_HARNESS_SWITCH = "intent.harness_switch"


def make_terminal_event(event_type: EventType,
                        payload: dict[str, Any] | None = None,
                        trace_id: str = "",
                        event_id: str = "") -> BusEvent:
    """Create a BusEvent with source='terminal' from an EventType.

    This is the ONLY way terminal code should create events.
    """
    return BusEvent(
        name=event_type.value,
        payload=payload or {},
        source="terminal",
        trace_id=trace_id,
        event_id=event_id,
    )


# Backwards-compatible alias
TerminalEvent = BusEvent
