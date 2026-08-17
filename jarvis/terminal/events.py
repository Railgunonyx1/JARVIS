"""Sprint 9B — Terminal event types.

Events describe what happened.  They flow from Core → Event Bus → Terminal.
The terminal never emits events directly; it emits UIIntents instead.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from jarvis.terminal.types import _uuid, _now


class EventType(enum.Enum):
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


@dataclass(frozen=True)
class TerminalEvent:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=_uuid)
    timestamp: float = field(default_factory=_now)
    trace_id: str = ""
