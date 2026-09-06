"""J-Browser — tab identity.

Tabs are addressed by stable immutable ``tab_id`` (uuid), never by index,
because tab order changes as tabs open/close. The active tab is a first-class
notion so existing single-page callers can continue to use ``tab_id=None``.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field


def new_tab_id() -> str:
    """Generate a short, stable, collision-resistant tab id."""
    return "tab_" + uuid.uuid4().hex[:8]


@dataclass
class TabContext:
    """Identity + current state of one tab.

    distinct from a positioned index: ``tab_id`` stays stable across
    reordering, so the agent can operate on a specific tab explicitly.
    """

    tab_id: str
    session_id: str
    url: str = ""
    title: str = ""
    active: bool = False
    created_at: float = field(default_factory=__import__("time").time)


class TabManager:
    """Thread-safe ownership of tab contexts.

    The backend owns the real page objects; this manager owns the lightweight
    identities and active-tab pointer used by the platform and the agent.
    """

    def __init__(self) -> None:
        self._tabs: dict[str, TabContext] = {}
        self._lock = threading.Lock()
        self._active: str | None = None

    def register(self, context: TabContext) -> TabContext:
        with self._lock:
            self._tabs[context.tab_id] = context
        return context

    def activate(self, tab_id: str) -> TabContext | None:
        with self._lock:
            ctx = self._tabs.get(tab_id)
            if ctx is None:
                return None
            self._active = tab_id
            for other in self._tabs.values():
                other.active = other.tab_id == tab_id
        return ctx

    def active(self) -> TabContext | None:
        with self._lock:
            return self._tabs.get(self._active)

    def get(self, tab_id: str) -> TabContext | None:
        with self._lock:
            return self._tabs.get(tab_id)

    def list(self, session_id: str | None = None) -> list[TabContext]:
        with self._lock:
            tabs = list(self._tabs.values())
        if session_id is None:
            return tabs
        return [t for t in tabs if t.session_id == session_id]

    def remove(self, tab_id: str) -> bool:
        with self._lock:
            removed = self._tabs.pop(tab_id, None) is not None
            if removed and self._active == tab_id:
                # point active at the newest remaining tab, if any
                remaining = sorted(self._tabs.values(), key=lambda t: t.created_at)
                if remaining:
                    nxt = remaining[-1]
                    nxt.active = True
                    self._active = nxt.tab_id
                else:
                    self._active = None
        return removed

    def __len__(self) -> int:
        with self._lock:
            return len(self._tabs)
