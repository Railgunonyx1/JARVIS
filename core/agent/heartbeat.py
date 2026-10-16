"""Heartbeat under commitment queues (openclaw pattern).

Skip-don't-queue semantics with named skip reasons: the heartbeat never piles
up behind a busy main command lane; it is deferred and retried after an idle
grace. Commitments (things we said we'd do) are tracked with dedupe keys and
uncertain outcomes are *reported, never silently resent* (no double-fire).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Named skip reasons (openclaw HEARTBEAT_SKIP_* vocabulary).
HEARTBEAT_SKIP_BUSY = "HEARTBEAT_SKIP_BUSY"
HEARTBEAT_SKIP_CRON_IN_PROGRESS = "CRON_IN_PROGRESS"
HEARTBEAT_SKIP_PREEMPTED = "PREEMPTED"
HEARTBEAT_OK = "HEARTBEAT_OK"
HEARTBEAT_DISABLED = "HEARTBEAT_DISABLED"
HEARTBEAT_GRACE = "HEARTBEAT_GRACE"


class HeartbeatOutcome(StrEnum):
    OK = "ok"
    SKIPPED_BUSY = HEARTBEAT_SKIP_BUSY
    SKIPPED_GRACE = HEARTBEAT_GRACE
    SKIPPED_DISABLED = HEARTBEAT_DISABLED


@dataclass
class Commitment:
    """A durable 'we said we'd do this' record."""

    dedupe_key: str
    payload: Any
    created_at: float = field(default_factory=time.time)
    attempts: int = 0
    uncertain: bool = False   # outcome unknown -> must be reported, never resent
    outcome: str | None = None
    last_attempt_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dedupe_key": self.dedupe_key,
            "payload": self.payload,
            "created_at": self.created_at,
            "attempts": self.attempts,
            "uncertain": self.uncertain,
            "outcome": self.outcome,
            "last_attempt_at": self.last_attempt_at,
        }


class HeartbeatCoordinator:
    """Coordinates heartbeat beats under a possibly-busy main command lane."""

    def __init__(
        self,
        *,
        idle_grace: float = 2.0,
        heartbeat_interval: float = 30.0,
        main_busy_check: Callable[[], bool] | None = None,
        publisher: Callable[[str, dict[str, Any]], None] | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.idle_grace = max(0.0, idle_grace)
        self.heartbeat_interval = max(0.1, heartbeat_interval)
        self._main_busy_check = main_busy_check or (lambda: False)
        self._publisher = publisher
        self._now = now or time.time
        self._enabled = True
        self._last_beat: float | None = None
        self._next_eligible: float = 0.0
        self._commitments: dict[str, Commitment] = {}
        self._lock = threading.RLock()

    # ── enable / disable ────────────────────────────────────────
    def enable(self) -> None:
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        with self._lock:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    # ── beat gating ─────────────────────────────────────────────
    def should_beat(self, now: float | None = None) -> tuple[bool, str]:
        t = self._now() if now is None else now
        with self._lock:
            if not self._enabled:
                return False, HEARTBEAT_DISABLED
            if self._main_busy_check():
                return False, HEARTBEAT_SKIP_BUSY
            if t < self._next_eligible:
                return False, HEARTBEAT_GRACE
            return True, HEARTBEAT_OK

    def record_beat(self, now: float | None = None) -> None:
        t = self._now() if now is None else now
        with self._lock:
            self._last_beat = t
            self._next_eligible = t + self.heartbeat_interval
            if self._publisher is not None:
                try:
                    self._publisher("heartbeat.beat", {"at": t})
                except Exception:  # noqa: BLE001 - publisher failures must not crash
                    pass

    def skip(self, reason: str, now: float | None = None) -> None:
        t = self._now() if now is None else now
        with self._lock:
            # grace retry after idle window (do not queue)
            self._next_eligible = max(self._next_eligible, t + self.idle_grace)
            if self._publisher is not None:
                try:
                    self._publisher("heartbeat.skipped", {"reason": reason, "at": t})
                except Exception:  # noqa: BLE001
                    pass

    @property
    def last_beat(self) -> float | None:
        with self._lock:
            return self._last_beat

    @property
    def next_eligible(self) -> float:
        with self._lock:
            return self._next_eligible

    # ── commitments ─────────────────────────────────────────────
    def submit(self, dedupe_key: str, payload: Any = None) -> Commitment:
        with self._lock:
            existing = self._commitments.get(dedupe_key)
            if existing is not None:
                # de-dupe: never create a second in-flight commitment
                return existing
            c = Commitment(dedupe_key=dedupe_key, payload=payload)
            self._commitments[dedupe_key] = c
            return c

    def attempt(self, dedupe_key: str) -> Commitment | None:
        with self._lock:
            c = self._commitments.get(dedupe_key)
            if c is None:
                return None
            c.attempts += 1
            c.last_attempt_at = self._now()
            return c

    def settle(self, dedupe_key: str, outcome: str, *,
               uncertain: bool = False) -> bool:
        """Record an outcome. Returns False if dedupe key unknown."""
        with self._lock:
            c = self._commitments.get(dedupe_key)
            if c is None:
                return False
            if c.outcome is not None:
                # already settled — do not overwrite (idempotent)
                return True
            c.outcome = outcome
            c.uncertain = uncertain
            if self._publisher is not None:
                try:
                    self._publisher("heartbeat.commitment.settled", {
                        "dedupe_key": dedupe_key, "outcome": outcome,
                        "uncertain": uncertain,
                    })
                except Exception:  # noqa: BLE001
                    pass
            return True

    def report_uncertain(self) -> list[Commitment]:
        """Return commitments with unknown outcomes (never re-send silently)."""
        with self._lock:
            return [c for c in self._commitments.values()
                    if c.outcome is not None and c.uncertain]

    def pending(self) -> list[Commitment]:
        with self._lock:
            return [c for c in self._commitments.values() if c.outcome is None]

    def is_duplicate(self, dedupe_key: str) -> bool:
        with self._lock:
            return dedupe_key in self._commitments

    def get(self, dedupe_key: str) -> Commitment | None:
        with self._lock:
            return self._commitments.get(dedupe_key)

    def clear(self) -> None:
        with self._lock:
            self._commitments.clear()

    def new_dedupe_key(self, namespace: str = "") -> str:
        return f"{namespace}:{uuid.uuid4().hex}" if namespace else uuid.uuid4().hex


__all__ = [
    "HEARTBEAT_DISABLED", "HEARTBEAT_GRACE", "HEARTBEAT_OK",
    "HEARTBEAT_SKIP_BUSY", "HEARTBEAT_SKIP_CRON_IN_PROGRESS",
    "HEARTBEAT_SKIP_PREEMPTED",
    "Commitment", "HeartbeatCoordinator", "HeartbeatOutcome",
]
