"""J-Browser — EventBus integration.

J-Browser publishes ``browser.*`` events on the canonical EventBus so any
consumer (JARVIS agent, TUI, or a future side panel) can subscribe with a
single ``browser.**`` wildcard without coupling to the browser internals.

Every event carries the originating ``session_id`` and a ``trace_id`` so it
associates with the correct agent task (Phase A session-identity invariant).
"""

from __future__ import annotations

from typing import Any

from runtime.event_bus import BusEvent, get_event_bus

# Canonical browser event names.
TAB_CREATED = "browser.tab.created"
TAB_CLOSED = "browser.tab.closed"
TAB_ACTIVATED = "browser.tab.activated"
NAVIGATION_STARTED = "browser.navigation.started"
NAVIGATION_COMPLETED = "browser.navigation.completed"
PAGE_LOADED = "browser.page.loaded"
PAGE_CHANGED = "browser.page.changed"
DOWNLOAD_STARTED = "browser.download.started"
AGENT_ACTION = "browser.agent.action"
APPROVAL_REQUIRED = "browser.agent.approval_required"
ACTION_COMPLETED = "browser.agent.action.completed"

ALL_EVENTS = (
    TAB_CREATED, TAB_CLOSED, TAB_ACTIVATED,
    NAVIGATION_STARTED, NAVIGATION_COMPLETED, PAGE_LOADED, PAGE_CHANGED,
    DOWNLOAD_STARTED, AGENT_ACTION, APPROVAL_REQUIRED, ACTION_COMPLETED,
)


def emit_browser_event(name: str, payload: dict[str, Any], *,
                       session_id: str = "", trace_id: str = "") -> None:
    """Publish a browser event, stamped with session/trace identity."""
    bus = get_event_bus()
    event = BusEvent(
        name=name,
        payload=payload or {},
        source="jbrowser",
        session_id=session_id,
        trace_id=trace_id,
    )
    try:
        bus.publish(event)
    except Exception:
        # Event delivery must never break the tool call that caused it.
        pass
