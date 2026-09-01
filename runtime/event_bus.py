"""Canonical Event Bus — all inter-module communication flows through here.

Architecture contract:
    Terminal UI -> UIIntent -> Event Bus -> Core Kernel
    Core owns decisions. Events describe what happened.

This is the single canonical event bus.  All subsystems publish and
subscribe here.  No direct cross-module callbacks.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jarvis.event_bus")


CURRENT_SCHEMA_VERSION = 1
EVENT_LOG_TTL_SECONDS = 3600.0  # 1 hour


@dataclass(frozen=True)
class BusEvent:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    trace_id: str = ""
    timestamp: float = field(default_factory=time.time)
    event_id: str = ""
    schema_version: int = CURRENT_SCHEMA_VERSION
    session_id: str = ""


Handler = Callable[[BusEvent], Any]


class EventBus:
    """Thread-safe, in-process pub/sub event bus with wildcard support."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._wildcards: list[tuple[str, Handler]] = []
        self._lock = threading.Lock()
        self._event_log: list[BusEvent] = []
        self._max_log = 500

    def subscribe(self, pattern: str, handler: Handler) -> None:
        """Subscribe to events matching ``pattern``.

        Patterns can contain ``*`` for single-segment wildcards and ``**``
        for multi-segment wildcards.  ``"tool.*"`` matches ``"tool.executed"``
        but not ``"tool.executed.extra"``.  ``"tool.**"`` matches both.
        """
        if "*" in pattern:
            with self._lock:
                self._wildcards.append((pattern, handler))
        else:
            with self._lock:
                self._handlers[pattern].append(handler)

    def unsubscribe(self, pattern: str, handler: Handler) -> None:
        with self._lock:
            if "*" in pattern:
                self._wildcards = [
                    (p, h) for p, h in self._wildcards
                    if not (p == pattern and h is handler)
                ]
            else:
                subs = self._handlers.get(pattern, [])
                if handler in subs:
                    subs.remove(handler)

    def _evict_expired(self, now: float) -> None:
        """Remove events older than TTL."""
        cutoff = now - EVENT_LOG_TTL_SECONDS
        # Find first event within TTL (log is ordered by insertion time)
        keep_idx = 0
        for i, ev in enumerate(self._event_log):
            if ev.timestamp >= cutoff:
                keep_idx = i
                break
        else:
            # All events expired
            keep_idx = len(self._event_log)
        if keep_idx > 0:
            self._event_log = self._event_log[keep_idx:]

    def publish(self, event: BusEvent) -> None:
        """Dispatch to all matching handlers (sync).  Never raises."""
        now = time.time()
        with self._lock:
            exact = list(self._handlers.get(event.name, []))
            wild = [
                (p, h) for p, h in self._wildcards
                if _match_pattern(p, event.name)
            ]
        for handler in exact + [h for _, h in wild]:
            try:
                handler(event)
            except Exception as e:
                logger.error("Bus handler error for %s: %s", event.name, e)
        with self._lock:
            self._event_log.append(event)
            if len(self._event_log) > self._max_log:
                self._event_log = self._event_log[-self._max_log:]
            # Periodic TTL eviction (every 100 events)
            if len(self._event_log) % 100 == 0:
                self._evict_expired(now)

    async def publish_async(self, event: BusEvent) -> None:
        """Dispatch to all matching handlers (async-aware)."""
        now = time.time()
        with self._lock:
            exact = list(self._handlers.get(event.name, []))
            wild = [
                (p, h) for p, h in self._wildcards
                if _match_pattern(p, event.name)
            ]
        for handler in exact + [h for _, h in wild]:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Bus async handler error for %s: %s", event.name, e)
        with self._lock:
            self._event_log.append(event)
            if len(self._event_log) > self._max_log:
                self._event_log = self._event_log[-self._max_log:]
            if len(self._event_log) % 100 == 0:
                self._evict_expired(now)

    def recent(self, limit: int = 50) -> list[BusEvent]:
        with self._lock:
            return list(self._event_log[-limit:])

    def clear(self) -> None:
        with self._lock:
            self._event_log.clear()

    def evict_expired(self) -> int:
        """Manually evict expired events. Returns number evicted."""
        with self._lock:
            before = len(self._event_log)
            self._evict_expired(time.time())
            return before - len(self._event_log)


def _match_pattern(pattern: str, name: str) -> bool:
    """Simple segment-level wildcard matching."""
    p_parts = pattern.split(".")
    n_parts = name.split(".")
    pi = 0
    ni = 0
    while pi < len(p_parts) and ni < len(n_parts):
        if p_parts[pi] == "**":
            return True
        if p_parts[pi] == "*":
            pi += 1
            ni += 1
            continue
        if p_parts[pi] != n_parts[ni]:
            return False
        pi += 1
        ni += 1
    return pi == len(p_parts) and ni == len(n_parts)


_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus
