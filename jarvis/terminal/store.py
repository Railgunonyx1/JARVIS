"""Sprint 9D — Immutable state store backed by reducers.

The store holds a single SessionState and applies events via reducers.
Thread-safe: uses a lock around state swaps.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from jarvis.terminal.events import TerminalEvent
from jarvis.terminal.reducers import reduce
from jarvis.terminal.types import SessionState

logger = logging.getLogger("jarvis.terminal.store")


class TerminalStore:
    """Immutable state store: holds SessionState, applies events via reducers."""

    def __init__(self, initial: SessionState | None = None):
        self._state: SessionState = initial or SessionState()
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[SessionState], None]] = []

    @property
    def state(self) -> SessionState:
        return self._state

    def dispatch(self, event: TerminalEvent) -> SessionState:
        """Apply an event and return the new state.  Notifies subscribers."""
        with self._lock:
            old = self._state
            self._state = reduce(old, event)
        if self._state is not old:
            self._notify()
        return self._state

    def subscribe(self, callback: Callable[[SessionState], None]) -> Callable[[], None]:
        """Register a callback.  Returns an unsubscribe function."""
        self._subscribers.append(callback)

        def _unsub() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return _unsub

    def _notify(self) -> None:
        state = self._state
        for cb in self._subscribers:
            try:
                cb(state)
            except Exception as e:
                logger.error("Store subscriber error: %s", e)
