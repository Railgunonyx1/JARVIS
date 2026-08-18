"""Sprint 13/14B -- Session persistence, replay, resume, and event-sourced recording.

Saves session state + events to SQLite.  EventBusPersistenceSubscriber
hooks the canonical event bus so events are recorded automatically without
manual record_event calls.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from jarvis.terminal.events import EventType, TerminalEvent
from jarvis.terminal.reducers import reduce
from jarvis.terminal.store import TerminalStore
from jarvis.terminal.types import SessionState
from runtime.event_bus import BusEvent, EventBus, get_event_bus

logger = logging.getLogger("jarvis.terminal.persistence")

_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    timestamp REAL NOT NULL,
    seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_events_session ON session_events(session_id);
CREATE INDEX IF NOT EXISTS idx_session_events_seq ON session_events(session_id, seq);
"""


class SessionPersistence:
    """SQLite-backed persistence for terminal sessions."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or (Path.home() / ".jarvis" / "data" / "sessions.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
                self._conn.execute("PRAGMA journal_mode = WAL")
            return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_DDL)
        conn.commit()

    def save_state(self, state: SessionState) -> None:
        """Persist the current session state snapshot."""
        conn = self._get_conn()
        state_json = json.dumps(_serialize_state(state), ensure_ascii=False)
        now = time.time()
        conn.execute(
            """INSERT INTO sessions (session_id, state_json, created_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 state_json=excluded.state_json, updated_at=excluded.updated_at""",
            (state.session_id, state_json, state.created_at, now),
        )
        conn.commit()

    def load_state(self, session_id: str) -> SessionState | None:
        """Load a persisted session state snapshot."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT state_json FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return _deserialize_state(json.loads(row[0]))

    def record_event(self, session_id: str, event: TerminalEvent, seq: int) -> None:
        """Append an event to the session event log."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO session_events (session_id, event_type, payload_json, timestamp, seq)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, event.name, json.dumps(event.payload, ensure_ascii=False),
             event.timestamp, seq),
        )
        conn.commit()

    def replay_events(self, session_id: str) -> SessionState | None:
        """Replay all events for a session to reconstruct the final state."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT event_type, payload_json, timestamp
               FROM session_events WHERE session_id = ?
               ORDER BY seq ASC""",
            (session_id,),
        ).fetchall()
        if not rows:
            return None
        state = SessionState(session_id=session_id)
        for event_type_str, payload_json, timestamp in rows:
            event = BusEvent(
                name=event_type_str,
                payload=json.loads(payload_json),
                timestamp=timestamp,
                source="replay",
            )
            state = reduce(state, event)
        return state

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent sessions with their metadata."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT session_id, created_at, updated_at, state_json
               FROM sessions ORDER BY updated_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        sessions = []
        for sid, created, updated, state_json in rows:
            state = _deserialize_state(json.loads(state_json))
            sessions.append({
                "session_id": sid,
                "created_at": created,
                "updated_at": updated,
                "status": state.status.value if state else "unknown",
                "messages": len(state.messages) if state else 0,
            })
        return sessions

    def delete_session(self, session_id: str) -> bool:
        conn = self._get_conn()
        conn.execute("DELETE FROM session_events WHERE session_id = ?", (session_id,))
        cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None


def _serialize_state(state: SessionState) -> dict[str, Any]:
    """Convert SessionState to a JSON-serializable dict."""
    return {
        "status": state.status.value,
        "layout": state.layout.value,
        "model": state.model,
        "provider": state.provider,
        "tokens_prompt": state.tokens_prompt,
        "tokens_completion": state.tokens_completion,
        "latency_ms": state.latency_ms,
        "messages": [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in state.messages
        ],
        "activity": [
            {"name": a.name, "payload": a.payload, "timestamp": a.timestamp}
            for a in state.activity
        ],
        "error": state.error,
        "session_id": state.session_id,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


def _deserialize_state(data: dict[str, Any]) -> SessionState:
    """Reconstruct SessionState from a serialized dict."""
    from jarvis.terminal.types import ActivityEvent, LayoutMode, Message, SessionStatus

    messages = tuple(
        Message(role=m["role"], content=m["content"], timestamp=m.get("timestamp", 0))
        for m in data.get("messages", [])
    )
    activity = tuple(
        ActivityEvent(name=a["name"], payload=a.get("payload", {}), timestamp=a.get("timestamp", 0))
        for a in data.get("activity", [])
    )
    try:
        status = SessionStatus(data.get("status", "idle"))
    except ValueError:
        status = SessionStatus.IDLE
    try:
        layout = LayoutMode(data.get("layout", "normal"))
    except ValueError:
        layout = LayoutMode.NORMAL

    return SessionState(
        status=status,
        layout=layout,
        model=data.get("model", ""),
        provider=data.get("provider", ""),
        tokens_prompt=data.get("tokens_prompt", 0),
        tokens_completion=data.get("tokens_completion", 0),
        latency_ms=data.get("latency_ms", 0.0),
        messages=messages,
        activity=activity,
        error=data.get("error", ""),
        session_id=data.get("session_id", ""),
        created_at=data.get("created_at", 0.0),
        updated_at=data.get("updated_at", 0.0),
    )


class EventBusPersistenceSubscriber:
    """Automatically records BusEvents to persistence via the event bus.

    Subscribes to all ``**`` events on the bus and records them to the
    session event log.  This replaces manual ``record_event()`` calls.

    Usage::

        persistence = SessionPersistence()
        subscriber = EventBusPersistenceSubscriber(persistence, session_id="s1")
        subscriber.start()
        # ... now all bus events are automatically recorded ...
        subscriber.stop()
    """

    def __init__(self, persistence: SessionPersistence, session_id: str,
                 bus: EventBus | None = None):
        self._persistence = persistence
        self._session_id = session_id
        self._bus = bus or get_event_bus()
        self._seq = 0
        self._handler = self._on_event

    def start(self) -> None:
        """Subscribe to all bus events."""
        self._bus.subscribe("**", self._handler)

    def stop(self) -> None:
        """Unsubscribe from the bus."""
        self._bus.unsubscribe("**", self._handler)

    def _on_event(self, event: BusEvent) -> None:
        """Record every bus event to the persistence log."""
        try:
            self._persistence.record_event(self._session_id, event, self._seq)
            self._seq += 1
        except Exception as e:
            logger.error("Failed to record event %s: %s", event.name, e)
