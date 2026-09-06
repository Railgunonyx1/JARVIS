"""Opt-in crash-recovery hook for the agent loop (G10).

The generic :class:`AgentLoop` knows only the contract; it never imports the
browser. A task that hits a recoverable failure (currently: a browser-namespace
tool reporting a browser-daemon crash) parks in ``WAITING_BROWSER``, consults a
:class:`RecoveryProvider`, and resumes ``EXECUTING`` with structured context
when the provider recovers. Exhaustion fails the task deterministically.

The coding agent runs with ``browser_recovery=None`` and behaves exactly as
before; the Orbit path wires ``orbit.recovery.BrowserRecovery``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RecoveryOutcome:
    """Result of a recovery attempt sequence."""

    ok: bool
    attempts: int = 0
    detail: str = ""


class RecoveryProvider:
    """Contract consulted by the loop when a tool reports a browser crash."""

    def is_recoverable(self, error: str) -> bool:
        """Return True when ``error`` describes a recoverable browser crash."""
        raise NotImplementedError

    async def recover(self, trace_id: str = "", session_id: str = "") -> RecoveryOutcome:
        """Attempt to restore the dependency, bounded. Never raises."""
        raise NotImplementedError


__all__ = ["RecoveryOutcome", "RecoveryProvider"]