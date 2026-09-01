"""Span data model for the JARVIS observability core.

A :class:`Span` is one measured unit of work (a phase such as ``memory.retrieve``
or ``provider.complete``) inside a trace. Timing uses ``time.perf_counter_ns``
integer nanoseconds to avoid float precision loss; durations are converted to
floats (ms) only at export time. Thread/process ids capture which executor the
work ran on, and ``error`` carries the failure reason when a phase errored.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Span"]


@dataclass
class Span:
    """A single timed phase within a trace."""

    name: str
    span_id: str
    trace_id: str
    parent_id: str | None
    start_ns: int
    end_ns: int = 0
    status: str = "OK"
    error: str | None = None
    thread_id: int | None = None
    process_id: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def finish(self) -> None:
        self.end_ns = time.perf_counter_ns()

    @property
    def finished(self) -> bool:
        return self.end_ns > 0

    def duration_ms(self) -> float:
        if not self.finished:
            return 0.0
        return (self.end_ns - self.start_ns) / 1_000_000.0

    def record_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append({"name": name, "attributes": dict(attributes or {})})

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def to_dict(self, base_ns: int) -> dict[str, Any]:
        return {
            "name": self.name,
            "span_id": self.span_id,
            "duration_ms": round(self.duration_ms(), 2),
            "offset_ms": round((self.start_ns - base_ns) / 1_000_000.0, 2),
            "status": self.status,
            "error": self.error,
            "parent_id": self.parent_id,
            "thread_id": self.thread_id,
            "process_id": self.process_id,
            "attributes": self.attributes,
            "events": self.events,
        }
