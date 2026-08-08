"""Observability core — single source of truth for JARVIS performance data.

This is the measurement layer the whole system is instrumented against. It
replaces ad-hoc timers scattered across the codebase with one span-based
tracing model:

    runtime.observability.tracer   — spans, traces, contextvar propagation
    runtime.observability.spans    — Span / trace data model
    runtime.observability.metrics  — counters, gauges, histograms
    runtime.observability.exporters— SQLite persistence + query helpers
    runtime.observability.dashboard— text renderers for `jarvis perf`

Usage (in the daemon and the agent loop):

    from runtime.observability.tracer import get_tracer

    tracer = get_tracer()
    root = tracer.begin("run: fix the bug", {"goal": goal[:200]})
    try:
        with tracer.span("memory.retrieve"):
            hits = mem.retrieve(query)
        with tracer.span("provider.complete") as span:
            response = await router.complete(...)
            if span is not None:
                span.set_attribute("provider", response.provider)
    finally:
        perf = tracer.end(root)

Persistence is opt-in (the daemon process calls ``enable_perf()``); the tracer
itself is always on so a request timeline travels with every result dict even
when nothing writes to disk.
"""

from runtime.observability.exporters import (
    SqliteExporter,
    disable_perf,
    enable_perf,
    get_perf_exporter,
    perf_db_path,
    read_latest,
    read_slowest,
    read_summary,
)
from runtime.observability.metrics import (
    MetricsRegistry,
    get_metrics,
    reset_metrics,
)
from runtime.observability.tracer import (
    Tracer,
    get_tracer,
    reset_tracer,
)

__all__ = [
    "SqliteExporter",
    "MetricsRegistry",
    "Tracer",
    "disable_perf",
    "enable_perf",
    "get_metrics",
    "get_perf_exporter",
    "get_tracer",
    "perf_db_path",
    "read_latest",
    "read_slowest",
    "read_summary",
    "reset_metrics",
    "reset_tracer",
]
