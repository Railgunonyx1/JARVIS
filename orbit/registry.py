"""JARVIS Orbit — CDP target registry + tab ownership.

Maps stable JARVIS tab ids (uuid, never positional) to Chromium CDP target
ids, and tracks tab ownership (USER / AGENT / SYSTEM) using the general
resource-lock primitive from ``core.locks``.

Ownership contract
------------------
* A tab has exactly one owner at a time.
* ``acquire`` by a competing owner fails with ``RESOURCE_LOCKED`` (deterministic
  signal for concurrency errors) unless the owner already holds the tab.
* The registry is the single source of truth for tab identity; the CDP backend
  holds target-level state.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from core.locks import (
    OWNER_AGENT,
    OWNER_SYSTEM,
    OWNER_USER,
    ResourceLockedError,
)


def new_orbit_tab_id() -> str:
    return "tab_" + uuid.uuid4().hex[:10]


@dataclass
class OrbitTarget:
    """One Chromium target mapped to a stable JARVIS tab identity."""

    tab_id: str
    target_id: str
    session_id: str
    owner: str
    ws_url: str = ""
    created_at: float = field(default_factory=time.time)
    url: str = ""
    title: str = ""
    active: bool = False
    started_ws: bool = False


class TargetRegistry:
    """Map stable tab ids <-> CDP target ids, with ownership enforcement."""

    def __init__(self, locks=None) -> None:
        self._targets: dict[str, OrbitTarget] = {}      # tab_id -> target
        self._by_target: dict[str, str] = {}            # target_id -> tab_id
        self._active: str | None = None                 # active tab_id
        self._guard = threading.RLock()
        self._locks = locks

    # ------------------------------------------------------------- identity
    def register(self, target_id: str, session_id: str, owner: str,
                 url: str = "", title: str = "") -> OrbitTarget:
        with self._guard:
            existing = self._by_target.get(target_id)
            if existing:
                return self._targets[existing]
            tab_id = new_orbit_tab_id()
            t = OrbitTarget(
                tab_id=tab_id, target_id=target_id, session_id=session_id,
                owner=owner, url=url, title=title,
            )
            self._targets[tab_id] = t
            self._by_target[target_id] = tab_id
            if self._active is None:
                self._active = tab_id
                t.active = True
            return t

    def lookup(self, tab_id: str) -> OrbitTarget | None:
        with self._guard:
            return self._targets.get(tab_id)

    def by_target(self, target_id: str) -> OrbitTarget | None:
        with self._guard:
            tid = self._by_target.get(target_id)
            return self._targets.get(tid) if tid else None

    def all(self) -> list[OrbitTarget]:
        with self._guard:
            return list(self._targets.values())

    def list(self, session_id: str | None = None, owner: str | None = None) -> list[OrbitTarget]:
        with self._guard:
            out = list(self._targets.values())
        if session_id is not None:
            out = [t for t in out if t.session_id == session_id]
        if owner is not None:
            out = [t for t in out if t.owner == owner]
        return out

    def remove(self, tab_id: str) -> bool:
        with self._guard:
            t = self._targets.pop(tab_id, None)
            if t is None:
                return False
            self._by_target.pop(t.target_id, None)
            if self._active == tab_id:
                remaining = sorted(self._targets.values(), key=lambda x: x.created_at)
                if remaining:
                    self._active = remaining[-1].tab_id
                    remaining[-1].active = True
                else:
                    self._active = None
            return True

    def active(self) -> OrbitTarget | None:
        with self._guard:
            return self._targets.get(self._active)

    def activate(self, tab_id: str) -> OrbitTarget | None:
        with self._guard:
            t = self._targets.get(tab_id)
            if t is None:
                return None
            if self._active and self._active in self._targets:
                self._targets[self._active].active = False
            self._active = tab_id
            t.active = True
            return t

    def touch(self, tab_id: str) -> None:
        t = self.lookup(tab_id)
        if t:
            t.url = t.url
            t.created_at = time.time()

    # ------------------------------------------------------------- ownership
    def own(self, tab_id: str, owner: str):
        """Acquire ownership of a tab; raises ResourceLockedError if contested."""
        t = self.lookup(tab_id)
        if t is None:
            raise KeyError(f"tab not found: {tab_id}")
        if self._locks is not None:
            lease = self._locks.acquire(tab_id, owner)
            t.owner = owner
            return lease
        if t.owner not in (owner, OWNER_SYSTEM):
            raise ResourceLockedError(tab_id, t.owner)
        t.owner = owner
        return None

    def release(self, tab_id: str, owner: str) -> None:
        if self._locks is not None:
            self._locks.release(tab_id, owner)
        t = self.lookup(tab_id)
        if t is not None and t.owner == owner:
            t.owner = OWNER_SYSTEM

    def owner_of(self, tab_id: str) -> str | None:
        t = self.lookup(tab_id)
        return t.owner if t else None

    def is_owned_by(self, tab_id: str, owner: str) -> bool:
        t = self.lookup(tab_id)
        return t is not None and t.owner == owner

    # ------------------------------------------------------------- state
    def status(self) -> dict:
        tabs = self.all()
        return {
            "targets": len(tabs),
            "active": self._active,
            "pages": [t.target_id for t in tabs if t.url],
            # ownership summary by owner
            "owners": {o: len(self.list(owner=o)) for o in
                       {t.owner for t in tabs}},
        }


# Canonical owner vocabulary re-exported for convenience.
__all__ = [
    "OWNER_SYSTEM", "OWNER_USER", "OWNER_AGENT",
    "OrbitTarget", "TargetRegistry", "new_orbit_tab_id",
]