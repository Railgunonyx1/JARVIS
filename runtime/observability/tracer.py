"""Tracer — the span/trace engine at the heart of JARVIS observability.

Records a flat, parent-linked span tree per request. Context vars propagate
the current trace/span through ``asyncio`` task boundaries (the daemon runs
kernel work in a detached, shielded task), so a span started in one task is
correctly attributed even when the trace is ended elsewhere.

Completed traces are kept in a bounded in-memory ring and pushed to any
registered sinks (e.g. the SQLite exporter in the daemon process). Every
public method is defensive: instrumentation can never crash the agent loop.
"""

from __future__ import annotations

import contextvars
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from runtime.observability.spans import Span

__all__ = ["Tracer", "get_tracer", "reset_tracer"]

TraceSink = Callable[[dict[str, Any]], None]

_CURRENT_TRACE: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "jarvis_trace", default=None
)
_CURRENT_SPAN: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "jarvis_span", default=None
)


class Tracer:
    """Thread-safe span tracer with contextvar propagation across tasks."""

    def __init__(self, max_traces: int = 512, enabled: bool | None = None) -> None:
        if enabled is None:
            from runtime.observability.config import trace_enabled

            enabled = trace_enabled()
        self._enabled = enabled
        self._lock = threading.Lock()
        self._open: dict[str, list[Span]] = {}
        self._by_id: dict[str, Span] = {}
        self._metrics: dict[str, dict[str, float]] = {}
        self._recent: deque = deque(maxlen=max_traces)
        self._sinks: list[TraceSink] = []

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_sink(self, sink: TraceSink) -> None:
        with self._lock:
            self._sinks.append(sink)

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex[:16]

    # ── trace lifecycle ────────────────────────────────────────────────────

    def begin(self, command: str, attributes: dict[str, Any] | None = None) -> Span | None:
        """Start a new trace and return its root span (None when disabled)."""
        if not self._enabled:
            return None
        root = Span(
            name="request",
            span_id=self._new_id(),
            trace_id=self._new_id(),
            parent_id=None,
            start_ns=time.perf_counter_ns(),
            thread_id=threading.get_ident(),
            process_id=os.getpid(),
        )
        root.set_attribute("command", command)
        for key, value in (attributes or {}).items():
            root.set_attribute(key, value)
        with self._lock:
            self._open[root.trace_id] = [root]
            self._by_id[root.span_id] = root
        _CURRENT_TRACE.set(root.trace_id)
        _CURRENT_SPAN.set(root.span_id)
        return root

    def end(self, root: Span | None, status: str = "OK", error: str = "") -> dict[str, Any] | None:
        """Finish a trace and return its snapshot dict (None when already ended)."""
        if root is None:
            return None
        with self._lock:
            spans = self._open.pop(root.trace_id, None)
        if spans is None:
            return None
        root.finish()
        root.status = status
        if error:
            root.error = error[:500]
        base_ns = root.start_ns
        trace: dict[str, Any] = {
            "trace_id": root.trace_id,
            "timestamp": time.time(),
            "command": root.attributes.get("command", "request"),
            "total_ms": round(root.duration_ms(), 2),
            "status": status,
            "spans": [s.to_dict(base_ns) for s in spans],
            "metrics": self._pop_metrics(root.trace_id),
        }
        with self._lock:
            self._recent.append(trace)
            for span in spans:
                self._by_id.pop(span.span_id, None)
        for sink in list(self._sinks):
            try:
                sink(trace)
            except Exception:
                pass
        try:
            _CURRENT_TRACE.set(None)
            _CURRENT_SPAN.set(None)
        except RuntimeError:
            pass
        return trace

    # ── span lifecycle ─────────────────────────────────────────────────────

    def child(self, name: str, attributes: dict[str, Any] | None = None) -> Span | None:
        """Start a child span of the current span; None when no active trace."""
        if not self._enabled:
            return None
        trace_id = _CURRENT_TRACE.get()
        parent_id = _CURRENT_SPAN.get()
        if trace_id is None:
            return None
        span = Span(
            name=name,
            span_id=self._new_id(),
            trace_id=trace_id,
            parent_id=parent_id,
            start_ns=time.perf_counter_ns(),
            thread_id=threading.get_ident(),
            process_id=os.getpid(),
        )
        for key, value in (attributes or {}).items():
            span.set_attribute(key, value)
        with self._lock:
            spans = self._open.get(trace_id)
            if spans is None:
                return None
            spans.append(span)
            self._by_id[span.span_id] = span
        _CURRENT_SPAN.set(span.span_id)
        return span

    def finish(self, span: Span | None, status: str = "OK", error: str = "") -> None:
        if span is None:
            return
        span.finish()
        span.status = status
        if error:
            span.error = error[:500]
        try:
            _CURRENT_SPAN.set(span.parent_id)
        except RuntimeError:
            pass

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[Span | None]:
        """Context manager: time one phase under the current trace (no-op standalone)."""
        span = self.child(name, attributes)
        try:
            yield span
        except BaseException as exc:
            self.finish(span, "ERROR", str(exc)[:500])
            raise
        else:
            self.finish(span)

    @contextmanager
    def trace(self, command: str, attributes: dict[str, Any] | None = None) -> Iterator[Span | None]:
        """Context manager wrapping a whole trace; always ends the trace."""
        root = self.begin(command, attributes)
        try:
            yield root
        except BaseException as exc:
            self.end(root, "ERROR", str(exc)[:500])
            raise
        else:
            self.end(root)

    # ── per-trace metrics (persisted to the counters table) ────────────────

    def add_metric(self, name: str, value: float = 1.0) -> None:
        if not self._enabled:
            return
        trace_id = _CURRENT_TRACE.get()
        if trace_id is None:
            return
        with self._lock:
            bucket = self._metrics.setdefault(trace_id, {})
            bucket[name] = bucket.get(name, 0.0) + value

    def _pop_metrics(self, trace_id: str) -> dict[str, float]:
        with self._lock:
            return self._metrics.pop(trace_id, {})

    # ── introspection ──────────────────────────────────────────────────────

    def recent(self, n: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._recent)
        return items[-n:]

    def active(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"trace_id": spans[0].trace_id,
                 "command": spans[0].attributes.get("command", "request"),
                 "duration_ms": round(spans[0].duration_ms(), 2)}
                for spans in self._open.values()
            ]

    def reset(self) -> None:
        with self._lock:
            self._open.clear()
            self._by_id.clear()
            self._metrics.clear()
            self._recent.clear()
            self._sinks.clear()


_tracer: Tracer | None = None
_tracer_lock = threading.Lock()


def get_tracer() -> Tracer:
    """Process-wide tracer (always on; persistence is a separate sink)."""
    global _tracer
    if _tracer is None:
        with _tracer_lock:
            if _tracer is None:
                _tracer = Tracer()
    return _tracer


def reset_tracer() -> Tracer:
    """Replace the global tracer with a fresh one (tests / teardown)."""
    global _tracer
    with _tracer_lock:
        _tracer = Tracer()
    return _tracer
