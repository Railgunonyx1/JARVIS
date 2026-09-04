"""General resource-lock + ownership abstraction for JARVIS MK-X.

Provides keyed, reentrant, ownership-aware locking so concurrent tool threads
and agents can operate on disjoint resources (e.g. browser tabs) in parallel
while serializing access to the same resource and surfacing a deterministic
``RESOURCE_LOCKED`` signal when ownership is contested.

This is the single general primitive that Orbit browser tools (tab ownership)
and multi-agent execution build on (G4/G5/G7). It is transport/engine-neutral.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


class ResourceLockedError(RuntimeError):
    """Raised when a resource is already owned/locked by a different owner."""

    code = "RESOURCE_LOCKED"

    def __init__(self, key: str, owner: str) -> None:
        self.key = key
        self.owner = owner
        super().__init__(f"resource '{key}' is locked by owner '{owner}'")


class _Entry:
    __slots__ = ("transition", "lock", "owner", "depth")

    def __init__(self) -> None:
        self.transition = threading.Lock()
        self.lock = threading.RLock()
        self.owner: str | None = None
        self.depth: int = 0


@dataclass
class Lease:
    """Handed to the acquirer; release via ``.release()`` or context manager."""

    lock: "ResourceLock"
    key: str
    owner: str
    reentrant: bool = field(default=False)

    def release(self) -> None:
        self.lock.release(self.key, self.owner)

    def __enter__(self) -> "Lease":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


class ResourceLock:
    """Keyed, reentrant, ownership-aware lock.

    ``acquire(key, owner)`` returns a :class:`Lease`. If ``key`` is already
    owned by a *different* owner, it raises :class:`ResourceLockedError` so the
    caller can signal ``RESOURCE_LOCKED(<key>)`` rather than silently blocking.
    Re-acquiring by the same owner is reentrant (returns immediately).
    """

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._guard = threading.Lock()

    def _entry(self, key: str) -> _Entry:
        with self._guard:
            e = self._entries.get(key)
            if e is None:
                e = _Entry()
                self._entries[key] = e
            return e

    def acquire(self, key: str, owner: str) -> Lease:
        e = self._entry(key)
        with e.transition:
            if e.owner is not None and e.owner != owner:
                raise ResourceLockedError(key, e.owner)
            e.lock.acquire()
            e.owner = owner
            e.depth += 1
            return Lease(self, key, owner, reentrant=e.depth > 1)

    def release(self, key: str, owner: str) -> None:
        e = self._entry(key)
        with e.transition:
            if e.owner is not owner:
                return
            e.depth -= 1
            if e.depth <= 0:
                e.owner = None
                e.depth = 0
                e.lock.release()

    def is_locked(self, key: str) -> bool:
        return self.owner_of(key) is not None

    def owner_of(self, key: str) -> str | None:
        e = self._entries.get(key)
        if e is None:
            return None
        with e.transition:
            return e.owner

    def locked_keys(self) -> list[str]:
        with self._guard:
            keys = list(self._entries.keys())
        return [k for k in keys if self.is_locked(k)]

    def clear(self) -> None:
        with self._guard:
            self._entries.clear()


# Owner kinds (canonical vocabulary shared with Orbit tab ownership).
OWNER_USER = "USER"
OWNER_SYSTEM = "SYSTEM"
OWNER_AGENT = "AGENT"


# Singleton for the process-wide resource-lock pool.
_resource_lock: ResourceLock | None = None
_resource_lock_guard = threading.Lock()


def get_resource_lock() -> ResourceLock:
    """Return the process-wide :class:`ResourceLock` singleton."""
    global _resource_lock
    if _resource_lock is None:
        with _resource_lock_guard:
            if _resource_lock is None:
                _resource_lock = ResourceLock()
    return _resource_lock
