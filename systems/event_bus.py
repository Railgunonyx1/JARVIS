"""Unified Event Bus — All modules communicate through events instead of direct calls.

Single bus with logical channels (system, app, user), priority queues, and middleware pipeline.

Every event carries a trace_id for end-to-end request tracking.
"""
import asyncio
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger("jarvis.event_bus")


class EventPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class EventStatus(Enum):
    PENDING = auto()
    PROCESSING = auto()
    COMPLETED = auto()
    FAILED = auto()
    DROPPED = auto()


@dataclass
class Event:
    name: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    priority: EventPriority = EventPriority.NORMAL
    trace_id: str = ""
    parent_id: str = ""
    timestamp: float = 0.0
    event_id: str = ""
    status: EventStatus = EventStatus.PENDING
    _counter: int = 0

    def __post_init__(self):
        if not self.event_id:
            Event._counter += 1
            self.event_id = f"evt_{Event._counter}_{int(time.time() * 1000000) % 1000000}"
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        if not self.trace_id:
            self.trace_id = self.event_id


class EventBus:
    """Single event bus with logical channels, priority queues, and middleware.

    Channels are logical (not separate buses):
      system.*  — lifecycle, errors, shutdown
      app.*     — business events (intent, memory, capability)
      user.*    — per-session events (voice, chat)

    Middleware runs before handlers for matching events.
    """

    def __init__(self, max_queue_size: int = 1000):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._wildcard_subscribers: list[Callable] = []
        self._middleware: list[tuple[str, Callable]] = []
        self._queue: list[Event] = []
        self._max_queue = max_queue_size
        self._lock = threading.Lock()
        self._dispatch_count = 0
        self._drop_count = 0
        self._handler_errors = 0
        self._event_log: list[dict[str, Any]] = []
        self._max_log = 200
        self._running = True
        self._metrics: dict[str, float] = defaultdict(float)

    # ── Subscription ──────────────────────────────────────────

    def subscribe(self, event_name: str, handler: Callable) -> None:
        with self._lock:
            self._subscribers[event_name].append(handler)

    def subscribe_all(self, handler: Callable) -> None:
        with self._lock:
            self._wildcard_subscribers.append(handler)

    def unsubscribe(self, event_name: str, handler: Callable) -> None:
        with self._lock:
            if event_name in self._subscribers:
                try:
                    self._subscribers[event_name].remove(handler)
                except ValueError:
                    pass

    # ── Middleware ─────────────────────────────────────────────

    def add_middleware(self, event_pattern: str, middleware_fn: Callable) -> None:
        with self._lock:
            self._middleware.append((event_pattern, middleware_fn))

    def remove_middleware(self, event_pattern: str, middleware_fn: Callable) -> None:
        with self._lock:
            try:
                self._middleware.remove((event_pattern, middleware_fn))
            except ValueError:
                pass

    # ── Publishing ────────────────────────────────────────────

    def publish(self, event: Event) -> None:
        if not self._running:
            event.status = EventStatus.DROPPED
            return

        t0 = time.perf_counter()
        with self._lock:
            handlers = list(self._subscribers.get(event.name, []))
            handlers.extend(self._subscribers.get("*", []))
            handlers.extend(self._wildcard_subscribers)

            # Find matching middleware
            middleware = [
                fn for pattern, fn in self._middleware
                if self._match_pattern(pattern, event.name)
            ]

        # Run middleware chain
        event.status = EventStatus.PROCESSING
        for mw in middleware:
            try:
                result = mw(event)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        pass
            except Exception as e:
                logger.debug("Middleware error on '%s': %s", event.name, e)

        # Dispatch to handlers
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        pass
            except Exception as e:
                self._handler_errors += 1
                logger.debug("Handler error on '%s': %s", event.name, e)

        event.status = EventStatus.COMPLETED
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self._dispatch_count += 1
        self._metrics[event.name] += elapsed_ms

        self._event_log.append({
            "name": event.name,
            "source": event.source,
            "priority": event.priority.name,
            "trace_id": event.trace_id,
            "ms": round(elapsed_ms, 3),
            "ts": event.timestamp,
        })
        if len(self._event_log) > self._max_log:
            self._event_log = self._event_log[-self._max_log:]

    def emit(self, event_name: str, data: dict[str, Any] = None,
             source: str = "", priority: EventPriority = EventPriority.NORMAL,
             trace_id: str = "") -> Event:
        event = Event(
            name=event_name,
            data=data or {},
            source=source,
            priority=priority,
            trace_id=trace_id,
        )
        self.publish(event)
        return event

    # ── Priority Queue ────────────────────────────────────────

    def enqueue(self, event: Event) -> None:
        with self._lock:
            if len(self._queue) < self._max_queue:
                self._queue.append(event)
                self._queue.sort(key=lambda e: e.priority.value)
            else:
                self._drop_count += 1
                event.status = EventStatus.DROPPED

    def process_queue(self, max_events: int = 50) -> int:
        processed = 0
        with self._lock:
            batch = self._queue[:max_events]
            self._queue = self._queue[max_events:]
        for event in batch:
            self.publish(event)
            processed += 1
        return processed

    # ── Pattern Matching ──────────────────────────────────────

    @staticmethod
    def _match_pattern(pattern: str, event_name: str) -> bool:
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_name.startswith(prefix) and (
                len(event_name) == len(prefix) or event_name[len(prefix)] == "."
            )
        return pattern == event_name

    # ── Channel helpers ───────────────────────────────────────

    def system(self, name: str, **kwargs) -> Event:
        return self.emit(f"system.{name}", **kwargs)

    def app(self, name: str, **kwargs) -> Event:
        return self.emit(f"app.{name}", **kwargs)

    def user(self, name: str, **kwargs) -> Event:
        return self.emit(f"user.{name}", **kwargs)

    # ── Stats ─────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "dispatch_count": self._dispatch_count,
                "drop_count": self._drop_count,
                "handler_errors": self._handler_errors,
                "queue_size": len(self._queue),
                "subscriber_count": sum(len(h) for h in self._subscribers.values()),
                "event_types": len(self._subscribers),
                "middleware_count": len(self._middleware),
                "avg_dispatch_ms": round(
                    sum(self._metrics.values()) / max(len(self._metrics), 1), 3
                ),
            }

    def get_recent_events(self, count: int = 20) -> list[dict[str, Any]]:
        return self._event_log[-count:]

    def shutdown(self) -> None:
        self._running = False
        with self._lock:
            self._queue.clear()
            self._subscribers.clear()
            self._wildcard_subscribers.clear()
            self._middleware.clear()
            self._event_log.clear()


_bus_instance: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = EventBus()
    return _bus_instance
