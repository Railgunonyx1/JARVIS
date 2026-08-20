"""Event-sourced store for the JARVIS core.

Architecture contract:
    append(event) → reduces → new snapshot
    replay(events) → rebuilds state from scratch
    snapshot() → current immutable SessionState

The store owns:
  - the ordered event log (append-only)
  - the current SessionState snapshot (recomputed on each append)
  - serialization for persistence to disk

The store does NOT own:
  - the bus (runtime/event_bus.py) — that's a separate concern
  - the renderer — it reads snapshots, never the store directly
  - any I/O beyond in-memory state

Persistence is optional and injected via a serializer.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.core_events import CoreEvent
from core.reducers import reduce
from core.types import SessionState

logger = logging.getLogger("jarvis.store")


# ---------------------------------------------------------------------------
# Event serializer (disk persistence)
# ---------------------------------------------------------------------------

class EventSerializer:
    """Serializes/deserializes CoreEvent to/from JSON lines."""

    @staticmethod
    def serialize(event: CoreEvent) -> str:
        """One event → one JSON line."""
        return json.dumps({
            "seq": event.seq,
            "category": event.category.value,
            "name": event.name,
            "payload": event.payload,
            "event_id": event.event_id,
            "session_id": event.session_id,
            "timestamp": event.timestamp,
            "schema_version": event.schema_version,
        }, ensure_ascii=False)

    @staticmethod
    def deserialize(line: str) -> CoreEvent | None:
        """One JSON line → one CoreEvent, or None on parse failure."""
        try:
            d = json.loads(line)
            return CoreEvent(
                seq=d["seq"],
                category=d["category"],
                name=d["name"],
                payload=d.get("payload", {}),
                event_id=d.get("event_id", ""),
                session_id=d.get("session_id", ""),
                timestamp=d.get("timestamp", 0.0),
                schema_version=d.get("schema_version", 1),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to deserialize event: %s", e)
            return None

    @staticmethod
    def serialize_state(state: SessionState) -> str:
        """Snapshot → JSON string for quick restore."""
        d = asdict(state)
        # Convert enums to strings
        d["status"] = state.status.value
        d["mode"] = state.mode.value
        d["verification_status"] = state.verification_status.value
        if state.failure_class:
            d["failure_class"] = state.failure_class.value
        return json.dumps(d, ensure_ascii=False, default=str)

    @staticmethod
    def deserialize_state(data: str) -> SessionState | None:
        """JSON string → SessionState snapshot."""
        try:
            from core.types import (
                FailureClass, Mode, Plan, PlanStep, StepStatus,
                TaskStatus, VerificationStatus,
            )
            d = json.loads(data)
            d["status"] = TaskStatus(d["status"])
            d["mode"] = Mode(d["mode"])
            d["verification_status"] = VerificationStatus(d["verification_status"])
            if d.get("failure_class"):
                d["failure_class"] = FailureClass(d["failure_class"])
            else:
                d["failure_class"] = None
            # Reconstruct Plan
            if d.get("plan"):
                plan_data = d["plan"]
                steps = tuple(
                    PlanStep(
                        id=s["id"], description=s["description"],
                        status=StepStatus(s["status"]),
                        started_at=s.get("started_at"),
                        completed_at=s.get("completed_at"),
                        related_event_ids=tuple(s.get("related_event_ids", ())),
                    )
                    for s in plan_data.get("steps", [])
                )
                d["plan"] = Plan(
                    id=plan_data["id"], goal=plan_data["goal"],
                    steps=steps, revision=plan_data.get("revision", 1),
                    created_at=plan_data.get("created_at", 0.0),
                    updated_at=plan_data.get("updated_at", 0.0),
                )
            # Reconstruct tuples from lists
            for key in ("messages", "tool_calls", "files_changed",
                        "verification_steps"):
                if isinstance(d.get(key), list):
                    d[key] = tuple(d[key])
            return SessionState(**d)
        except Exception as e:
            logger.warning("Failed to deserialize state: %s", e)
            return None


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

@dataclass
class Store:
    """Event-sourced store with replay, snapshot, and optional persistence.

    Thread-safe: all mutations go through a lock.
    """

    _session_id: str = ""
    _events: list[CoreEvent] = field(default_factory=list)
    _state: SessionState = field(default_factory=SessionState)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _listeners: list[Callable[[CoreEvent], None]] = field(
        default_factory=list, repr=False
    )

    def __post_init__(self):
        if not self._session_id:
            self._session_id = self._state.session_id

    # ── public API ────────────────────────────────────────────────────────

    @property
    def state(self) -> SessionState:
        """Current immutable snapshot.  Safe to read from any thread."""
        with self._lock:
            return self._state

    @property
    def events(self) -> list[CoreEvent]:
        """Copy of the event log."""
        with self._lock:
            return list(self._events)

    @property
    def seq(self) -> int:
        """Current sequence number."""
        with self._lock:
            return self._state.seq

    def append(self, event: CoreEvent) -> SessionState:
        """Append an event and recompute the snapshot.

        Returns the new SessionState after reduction.
        """
        with self._lock:
            self._events.append(event)
            self._state = reduce(self._state, event)
            # Notify listeners
            for listener in self._listeners:
                try:
                    listener(event)
                except Exception as e:
                    logger.error("Store listener error: %s", e)
            return self._state

    def append_many(self, events: list[CoreEvent]) -> SessionState:
        """Append multiple events in one lock acquisition."""
        with self._lock:
            for event in events:
                self._events.append(event)
                self._state = reduce(self._state, event)
                for listener in self._listeners:
                    try:
                        listener(event)
                    except Exception as e:
                        logger.error("Store listener error: %s", e)
            return self._state

    def on_event(self, listener: Callable[[CoreEvent], None]) -> None:
        """Register a listener called after each append."""
        with self._lock:
            self._listeners.append(listener)

    def snapshot(self) -> SessionState:
        """Return the current immutable snapshot."""
        return self.state

    def next_seq(self) -> int:
        """Get the next sequence number (thread-safe)."""
        with self._lock:
            return self._state.seq + 1

    # ── replay ────────────────────────────────────────────────────────────

    def replay(self, events: list[CoreEvent]) -> SessionState:
        """Rebuild state from an event log.  Clears current state first."""
        with self._lock:
            self._events = []
            self._state = SessionState(session_id=self._session_id)
            for event in events:
                self._events.append(event)
                self._state = reduce(self._state, event)
            return self._state

    # ── persistence ───────────────────────────────────────────────────────

    def save_events(self, path: Path) -> None:
        """Write the event log to a JSON-lines file."""
        with self._lock:
            lines = [EventSerializer.serialize(e) for e in self._events]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
        logger.info("Saved %d events to %s", len(lines), path)

    def load_events(self, path: Path) -> int:
        """Load events from a JSON-lines file.  Returns count loaded."""
        if not path.exists():
            return 0
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            event = EventSerializer.deserialize(line)
            if event is not None:
                events.append(event)
        with self._lock:
            self._events = []
            self._state = SessionState(session_id=self._session_id)
            for event in events:
                self._events.append(event)
                self._state = reduce(self._state, event)
        logger.info("Loaded %d events from %s", len(events), path)
        return len(events)

    def save_snapshot(self, path: Path) -> None:
        """Write the current snapshot to a JSON file."""
        with self._lock:
            data = EventSerializer.serialize_state(self._state)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        logger.info("Saved snapshot to %s", path)

    def load_snapshot(self, path: Path) -> bool:
        """Load a snapshot from a JSON file.  Returns True on success."""
        if not path.exists():
            return False
        data = path.read_text(encoding="utf-8")
        state = EventSerializer.deserialize_state(data)
        if state is None:
            return False
        with self._lock:
            self._state = state
            self._session_id = state.session_id
        logger.info("Loaded snapshot from %s", path)
        return True

    # ── helpers ───────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Reset the store to empty."""
        with self._lock:
            self._events = []
            self._state = SessionState(session_id=self._session_id)

    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    def recent_events(self, limit: int = 50) -> list[CoreEvent]:
        with self._lock:
            return list(self._events[-limit:])
