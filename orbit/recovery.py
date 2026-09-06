"""G10 — crash recovery for Orbit's Chromium control path.

A browser daemon crash mid-task surfaces inside tool results as a tell-tale
error string (CDP connection closed, Chromium exited, ...). When the agent loop
hits one, the task parks in ``WAITING_BROWSER`` and this :class:`BrowserRecovery`
relaunches Chromium through the single controller path, then the loop resumes
``EXECUTING`` with a structured recovery observation. Exhaustion fails the task
deterministically (TOOL_FAILURE) instead of surfacing raw exceptions.

This module is the browser-specific implementation of the generic
``core.agent.recovery.RecoveryProvider`` contract the loop consults; the coding
agent's loop (no provider) is untouched.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from core.agent.recovery import RecoveryOutcome, RecoveryProvider

# Tell-tale markers a crashed/absent browser leaves in tool error text.
BROWSER_DOWN_MARKERS: tuple[str, ...] = (
    "cdp connection closed",
    "connection closed for",
    "chromium exited",
    "chromium did not expose cdp",
    "browser not launched",
    "did not expose cdp",
    "failed to connect",
    "no unbranded chromium runtime",
    "target was closed",
    "target closed",
    "unexpected eof",
    "websocket connection",
    "browser disassociated",
)

_MAX_DETAIL = 200


def is_browser_down_error(error: str) -> bool:
    """Return True when ``error`` describes a recoverable browser crash."""
    err = (error or "").lower()
    return any(m in err for m in BROWSER_DOWN_MARKERS)


class BrowserRecovery(RecoveryProvider):
    """Bounded relaunch-and-probe recovery for the Orbit browser.

    Recovery is: shutdown the backend (kills the process tree, clears stale
    flags/connections) then launch() it again and probe status(). Bounded by
    ``max_attempts`` with a fixed backoff between attempts. All native calls
    are synchronous; ``recover`` runs them in a worker thread so the async
    agent loop never blocks on a subprocess spawn.
    """

    def __init__(
        self,
        controller_getter: Callable[[], object] | None = None,
        max_attempts: int = 3,
        backoff: float = 0.4,
    ) -> None:
        from orbit.controller import get_orbit_controller

        self._controller_getter = controller_getter or get_orbit_controller
        self.max_attempts = max(1, max_attempts)
        self.backoff = max(0.0, backoff)

    def is_recoverable(self, error: str) -> bool:
        return is_browser_down_error(error)

    # ------------------------------------------------------------- internals
    def _restart(self) -> None:
        """Tear down and relaunch the backend via the single controller path."""
        controller = self._controller_getter()
        backend = getattr(controller, "backend", None)
        if backend is None:
            raise RuntimeError("controller has no backend to recover")
        shutdown = getattr(backend, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:  # noqa: BLE001 - teardown is best-effort
                pass
        launch = getattr(backend, "launch", None)
        if not callable(launch):
            raise RuntimeError("backend cannot be relaunched")
        launch()

    def _probe(self) -> bool:
        """Return True when the backend reports a healthy, launched browser."""
        controller = self._controller_getter()
        backend = getattr(controller, "backend", None)
        status = getattr(backend, "status", None)
        if not callable(status):
            return False
        st = status() or {}
        return bool(st.get("launched") or st.get("available"))

    def _sync_recover(self) -> RecoveryOutcome:
        last_error = "probe failed"
        for attempt in range(1, self.max_attempts + 1):
            try:
                self._restart()
                if self._probe():
                    return RecoveryOutcome(
                        ok=True,
                        attempts=attempt,
                        detail=f"relaunched Chromium (attempt {attempt}/{self.max_attempts})",
                    )
                last_error = "browser relaunched but status probe failed"
            except Exception as exc:  # noqa: BLE001 - bounded recovery must not raise
                last_error = str(exc)[:_MAX_DETAIL] or type(exc).__name__
                if attempt < self.max_attempts and self.backoff:
                    time.sleep(self.backoff)
        return RecoveryOutcome(ok=False, attempts=self.max_attempts, detail=last_error)

    async def recover(self, trace_id: str = "", session_id: str = "") -> RecoveryOutcome:
        return await asyncio.to_thread(self._sync_recover)


__all__ = [
    "BROWSER_DOWN_MARKERS",
    "BrowserRecovery",
    "is_browser_down_error",
]