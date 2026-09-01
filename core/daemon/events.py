"""Event types used by the JARVIS daemon event bus."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, TypedDict

import heapq


class BusEvent(TypedDict):
    """Event emitted by the daemon event bus.

    All meaningful actions emit BusEvent with schema_version and session_id.
    """

    #: Unique identifier for this event type across the system
    name: str
    #: Contextual data specific to the event name
    payload: Dict[str, Any]
    #: Originating component
    source: str
    #: Correlates all events within a single agent execution session
    session_id: str
    #: Unique identifier for tracing through the system
    trace_id: str
    #: When the event was created (unix epoch milliseconds)
    timestamp: float


#: Constant for the event schema version — increments on breaking changes
SCHEMA_VERSION = "2024.09.01"

#: Maximum number of events to keep in memory before eviction triggers
MAX_EVENTS = 5000

#: Default time-to-live for events in seconds (24 hours)
DEFAULT_TTL_SECONDS = 86400

#: Maximum age for any event before eviction, regardless of count
MAX_EVENT_AGE_SECONDS = 604800  # 7 days


def make_session_id() -> str:
    """Generate a new session ID using timestamp + random components."""
    return f"sess_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def make_trace_id() -> str:
    """Generate a new trace ID for correlating related events."""
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------


def _emit(
    name: str,
    payload: Dict[str, Any],
    *,
    source: str = "agent_loop",
    session_id: str,
    trace_id: Optional[str] = None,
) -> BusEvent:
    """Emit a BusEvent with required session context.

    Parameters
    ----------
    name:
        Event name (e.g. "intent.classified", "inference.started").
    payload:
        Event-specific data.
    source:
        Component emitting the event (default: "agent_loop").
    session_id:
        **Required** — must be the daemon's current session identifier.
    trace_id:
        Correlates related events; generated automatically if not supplied.

    Returns
    -------
    BusEvent
        A fully-populated event ready for publication.
    """
    if not session_id:
        raise ValueError("_emit requires a non-empty session_id")

    event: BusEvent = {
        "name": name,
        "payload": payload or {},
        "source": source,
        "session_id": session_id,
        "trace_id": trace_id or make_trace_id(),
        "timestamp": time.time(),
    }
    return event


# ---------------------------------------------------------------------------
# Event eviction / TTL management
# ---------------------------------------------------------------------------


class EventEvictionError(RuntimeError):
    """Raised when event eviction cannot free enough space."""


def evict_old_events(
    events: List[BusEvent],
    max_events: int = MAX_EVENTS,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    max_age_seconds: int = MAX_EVENT_AGE_SECONDS,
) -> Tuple[List[BusEvent], int]:
    """Evict old events to stay within TTL and count limits.

    Uses a min-heap keyed by timestamp for O(n log n) eviction.

    Parameters
    ----------
    events:
        Current list of events to filter.
    max_events:
        Maximum number of events to retain after eviction.
    ttl_seconds:
        Events older than this TTL will be evicted.
    max_age_seconds:
        Events older than this absolute max age will always be evicted.

    Returns
    -------
    Tuple[List[BusEvent], int]
        Filtered event list and number of events evicted.
    """
    if not events:
        return [], 0

    now = time.time()
    evicted = 0
    retained: List[BusEvent] = []

    # Quick check: if we're under the count limit and all events are fresh,
    # no eviction needed
    if len(events) <= max_events:
        # Still check TTL — evict any expired events even if under count
        for event in events:
            age = now - event["timestamp"]
            if age > max_age_seconds:
                evicted += 1
            else:
                retained.append(event)
        return retained, evicted

    # Use min-heap approach: sort by timestamp and evict oldest first
    # heap elements: (timestamp, index, event)
    heap: List[Tuple[float, int, BusEvent]] = []
    for i, event in enumerate(events):
        age = now - event["timestamp"]
        # Always evict if past max_age
        if age > max_age_seconds:
            evicted += 1
            continue
        heapq.heappush(heap, (event["timestamp"], i, event))

    # Pop oldest events until we're within limits
    while heap and len(retained) < max_events:
        _, _idx, event = heapq.heappop(heap)
        age = now - event["timestamp"]

        # If this event is still within TTL, keep it
        if age <= ttl_seconds:
            retained.append(event)
        else:
            evicted += 1

    # If we still have too many events (heap was exhausted but we have extras),
    # evict the remaining oldest ones
    if len(retained) > max_events:
        # Events still in the original list but not in retained heap were already
        # handled; any remaining need sorting
        remaining_original = [e for e in events if e not in retained]
        retained.extend(remaining_original[-max_events + len(retained):])

    return retained, evicted


def get_event_age_seconds(event: BusEvent) -> float:
    """Get the age of an event in seconds since its creation."""
    return time.time() - event["timestamp"]


def is_event_expired(
    event: BusEvent,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    max_age_seconds: int = MAX_EVENT_AGE_SECONDS,
) -> bool:
    """Check if an event should be considered expired.

    Parameters
    ----------
    event:
        The event to check.
    ttl_seconds:
        Time-to-live threshold.
    max_age_seconds:
        Absolute maximum age before always expired.

    Returns
    -------
    bool
        True if the event should be evicted.
    """
    age = get_event_age_seconds(event)
    if age > max_age_seconds:
        return True
    if age > ttl_seconds:
        return True
    return False


# ---------------------------------------------------------------------------
# Example usage pattern in the daemon
# ---------------------------------------------------------------------------

# In the daemon, maintain an events list and periodically evict:

#   from core.daemon.events import _emit, evict_old_events, is_event_expired
#
#   # During daemon initialization:
#   self._events: List[BusEvent] = []
#
#   # When emitting an event:
#   event = _emit(
#       "intent.classified",
#       {"intent": intent, "confidence": confidence},
#       session_id=self._current_session_id,
#       trace_id=make_trace_id(),
#   )
#   self._events.append(event)
#   self._events, evicted = evict_old_events(self._events, max_events=5000)
#   # Optional: log eviction for monitoring
#   if evicted > 0:
#       logger.info(f"Evicted {evicted} old events")
#
#   # Check if specific event is expired:
#   if is_event_expired(some_event):
#       # Handle expired event
#       pass


# ---------------------------------------------------------------------------
# BusEvent persistence / bridge (optional)
# ---------------------------------------------------------------------------

# If CoreEvent is used for persistence, the conversion is:

#   bus_event: BusEvent = _emit(...)
#   core_event: CoreEvent = {
#       "schema_version": SCHEMA_VERSION,
#       "session_id": bus_event["session_id"],
#       "trace_id": bus_event["trace_id"],
#       "sequence": ...,
#       "name": bus_event["name"],
#       "payload": bus_event["payload"],
#   }


# ---------------------------------------------------------------------------
# Exported symbols
# ---------------------------------------------------------------------------

__all__ = [
    "BusEvent",
    "SCHEMA_VERSION",
    "make_session_id",
    "make_trace_id",
    "_emit",
    "evict_old_events",
    "get_event_age_seconds",
    "is_event_expired",
    "EventEvictionError",
]