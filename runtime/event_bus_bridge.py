"""Event Bus Bridge -- connects Core (AgentLoop/TaskObserver) to the canonical Event Bus.

The bridge translates TaskObserver callback events into BusEvents and
publishes them on the canonical bus.  It also translates BusEvents from
the terminal into actions the agent loop understands.

Architecture:
    TaskObserver._emit(name, payload) -> Bridge -> BusEvent -> Event Bus -> Terminal Store
"""

from __future__ import annotations

import logging
from typing import Any

from core.agent.observer import TaskObserver
from core.events import (
    PERMISSION_OBSERVED,
    STEP_COMPLETED,
    STEP_FAILED,
    STEP_STARTED,
    TASK_CANCELLED,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_FINISHED,
    TASK_STARTED,
)
from runtime.event_bus import BusEvent, EventBus, get_event_bus

logger = logging.getLogger("jarvis.event_bus_bridge")

_OBSERVER_TO_BUS = {
    TASK_STARTED: "task.started",
    TASK_FINISHED: "task.finished",
    TASK_CANCELLED: "task.cancelled",
    STEP_STARTED: "step.started",
    STEP_COMPLETED: "step.completed",
    STEP_FAILED: "step.failed",
    TASK_COMPLETED: "task.completed",
    TASK_FAILED: "task.failed",
    PERMISSION_OBSERVED: "permission.observed",
}


class EventBusBridge:
    """Bridges TaskObserver events to the canonical event bus.

    Usage:
        bridge = EventBusBridge()
        bridge.attach(observer)  # observer.on_event = bridge._forward
        # Now all observer events flow through the bus automatically.
    """

    def __init__(self, bus: EventBus | None = None):
        self._bus = bus or get_event_bus()

    def attach(self, observer: TaskObserver) -> None:
        """Wire an observer so its events flow through the bus."""
        observer.on_event = self._forward  # type: ignore[attr-defined]

    def _forward(self, event_name: str, payload: dict[str, Any]) -> None:
        bus_name = _OBSERVER_TO_BUS.get(event_name, event_name)
        trace_id = payload.get("task_id", "")
        bus_event = BusEvent(
            name=bus_name,
            payload=payload,
            source="agent_loop",
            trace_id=trace_id,
        )
        self._bus.publish(bus_event)

    def publish(self, name: str, payload: dict[str, Any] | None = None,
                source: str = "", trace_id: str = "") -> None:
        """Convenience: publish directly from the bridge."""
        self._bus.publish(BusEvent(
            name=name, payload=payload or {},
            source=source, trace_id=trace_id,
        ))
