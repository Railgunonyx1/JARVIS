"""Text renderers for performance data — the `jarvis perf` output layer.

Plain-string output (no Rich dependency) so the CLI stays light. Renders a
single trace as a timeline and a summary as an aggregate table.
"""

from __future__ import annotations

from typing import Any

__all__ = ["render_trace", "render_summary", "trace_table"]


def render_trace(trace: dict[str, Any]) -> str:
    """Render one trace as a compact phase timeline."""
    lines: list[str] = []
    command = str(trace.get("command") or "request")[:70]
    total = trace.get("total_ms", 0.0)
    status = trace.get("status", "OK")
    mark = "ERR" if status != "OK" else "ok "
    lines.append(f"  {command:<70} {total:>8.1f} ms  [{mark} {str(trace.get('trace_id', ''))[:8]}]")
    spans = sorted(
        trace.get("spans", []),
        key=lambda s: (s.get("offset_ms") or 0.0, s.get("duration_ms") or 0.0),
    )
    for span in spans:
        name = str(span.get("name", ""))[:22]
        ms = span.get("duration_ms", 0.0)
        attrs = span.get("attributes", {}) or {}
        extra = ""
        if attrs.get("provider"):
            extra = f"  [{attrs.get('provider')}/{attrs.get('model')}]"
        elif attrs.get("tool"):
            extra = f"  [{attrs.get('tool')}]"
        err = "" if span.get("status") == "OK" else " ERR"
        lines.append(f"    {name:<22} {ms:>9.1f} ms{err}{extra}")
    return "\n".join(lines)


def trace_table(traces: list[dict[str, Any]]) -> str:
    """Compact one-line-per-trace table (for `jarvis perf latest|slowest`)."""
    lines = [f"{'time':<19} {'total ms':>9}  command"]
    for trace in traces:
        ts = trace.get("timestamp", 0.0)
        import time as _time

        stamp = _time.strftime("%m-%d %H:%M:%S", _time.localtime(ts))
        lines.append(f"{stamp:<19} {trace.get('total_ms', 0):>9.1f}  {str(trace.get('command', ''))[:60]}")
    return "\n".join(lines)


def render_summary(summary: dict[str, Any]) -> str:
    """Render the aggregate summary (traces + phases + counters)."""
    lines: list[str] = ["JARVIS Perf Summary", "─────────────────────"]
    traces = summary.get("traces") or {}
    lines.append(
        f"  requests {traces.get('count', 0)}   avg {traces.get('avg_ms', 0):.1f} ms   "
        f"max {traces.get('max_ms', 0):.1f} ms"
    )
    lines.append("  phase                  count   avg_ms    min_ms    max_ms")
    for p in summary.get("phases", []):
        lines.append(
            f"    {str(p['name'])[:20]:<20} {p['count']:>5} {p['avg_ms']:>8.1f} "
            f"{p['min_ms']:>8.1f} {p['max_ms']:>8.1f}"
        )
    counters = summary.get("counters") or {}
    if counters:
        lines.append("  counters")
        for name, value in sorted(counters.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {str(name)[:30]:<30} {value:g}")
    return "\n".join(lines)
