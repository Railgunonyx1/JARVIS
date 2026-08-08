"""OpenTelemetry tracing for JARVIS MK-X pipeline.

Provides structured span traces with parent-child relationships for
measuring real latency across the request pipeline.

Usage:
    from python.tracing import trace_span, get_trace_history

    with trace_span("llm_query", provider="groq", model="qwen2.5"):
        response = await router.complete(...)
"""

import time
import threading
import logging
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

logger = logging.getLogger("jarvis.tracing")

_provider: Optional[TracerProvider] = None
_tracer: Optional[trace.Tracer] = None
_exporter: Optional[InMemorySpanExporter] = None
_trace_history: List[Dict[str, Any]] = []
_history_lock = threading.Lock()
_MAX_HISTORY = 200


def init_tracing() -> None:
    """Initialize the OpenTelemetry tracer with in-memory export."""
    global _provider, _tracer, _exporter

    _exporter = InMemorySpanExporter()
    _provider = TracerProvider()
    _provider.add_span_processor(SimpleSpanProcessor(_exporter))
    trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer("jarvis-mkx")
    logger.info("OpenTelemetry tracing initialized (in-memory)")


def _export_and_record() -> None:
    """Export finished spans from the buffer and record to history."""
    if _exporter is None:
        return
    spans = _exporter.get_finished_spans()
    if not spans:
        return
    _exporter.clear()

    with _history_lock:
        for span in spans:
            attrs = dict(span.attributes) if span.attributes else {}
            record = {
                "name": span.name,
                "trace_id": format(span.context.trace_id, "032x"),
                "span_id": format(span.context.span_id, "016x"),
                "start_ms": round((span.start_time / 1e6), 1),
                "duration_ms": round((span.end_time - span.start_time) / 1e6, 1),
                "attributes": {k: v for k, v in attrs.items() if isinstance(v, (str, int, float, bool))},
            }
            _trace_history.append(record)
        if len(_trace_history) > _MAX_HISTORY:
            _trace_history[:] = _trace_history[-_MAX_HISTORY:]


@contextmanager
def trace_span(name: str, **attributes):
    """Context manager that creates an OTel span with attributes.

    Also records duration to the existing LatencyTracker.

    Usage:
        with trace_span("llm_query", provider="groq"):
            result = await call_llm()
    """
    if _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name) as span:
        for k, v in attributes.items():
            if isinstance(v, (str, int, float, bool)):
                span.set_attribute(k, v)
        try:
            yield span
        except Exception as exc:
            span.set_attribute("error", True)
            span.record_exception(exc)
            raise
        finally:
            _export_and_record()


def get_trace_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent traces from the in-memory buffer."""
    _export_and_record()
    with _history_lock:
        return list(_trace_history[-limit:])


def clear_trace_history() -> None:
    """Clear the trace history buffer."""
    with _history_lock:
        _trace_history.clear()
    if _exporter:
        _exporter.clear()
