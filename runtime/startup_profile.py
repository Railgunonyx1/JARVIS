"""Startup profiler for JARVIS MK-X.

Records wall-clock time per startup phase (import, config, registry, project,
router, memory, kernel) so `jarvis --profile-startup` can report exactly where
startup time goes. Recording is ~1us per phase, so it runs always; only
printing is opt-in.

The profiler also bridges into the observability core: when ``begin_trace``
is active, every phase becomes a child span of a ``jarvis.cli.startup`` trace
so startup milestones show up in the same span model as requests. Every call
is defensive — profiling can never break a boot.

Lives in ``runtime`` (not ``cli``) so the persistent daemon process can also
profile its boot without importing the typer CLI.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator, List, Optional

__all__ = ["StartupProfiler", "get_profiler", "startup_report"]


class StartupProfiler:
    """Collect phase timings and render a startup report."""

    def __init__(self) -> None:
        self._started: float = time.perf_counter()
        self._phases: List[tuple[str, float, float]] = []  # (name, start, end)
        self._stack: List[tuple[str, float, object]] = []  # (name, start, span)
        self._root: object = None
        self._trace_depth = 0

    # ── observability bridge ───────────────────────────────────────────

    def begin_trace(self, command: str = "jarvis.cli.startup") -> None:
        """Open a startup trace; nested calls are balanced, not nested."""
        if self._root is not None:
            self._trace_depth += 1
            return
        try:
            from runtime.observability.tracer import get_tracer

            self._root = get_tracer().begin(command)
            self._trace_depth = 1
        except Exception:
            self._root = None

    def end_trace(self, status: str = "OK", error: str = "") -> None:
        if self._root is None:
            return
        self._trace_depth -= 1
        if self._trace_depth > 0:
            return
        root, self._root = self._root, None
        try:
            from runtime.observability.tracer import get_tracer

            get_tracer().end(root, status, error)
        except Exception:
            pass

    # ── phase timing ───────────────────────────────────────────────────

    def begin(self, name: str) -> None:
        span = None
        try:
            from runtime.observability.tracer import get_tracer

            span = get_tracer().child(name)
        except Exception:
            pass
        self._stack.append((name, time.perf_counter(), span))

    def end(self, name: str) -> None:
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == name:
                _, start, span = self._stack.pop(i)
                if span is not None:
                    try:
                        from runtime.observability.tracer import get_tracer

                        get_tracer().finish(span)
                    except Exception:
                        pass
                self._phases.append((name, start, time.perf_counter()))
                return

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        self.begin(name)
        try:
            yield
        finally:
            self.end(name)

    def elapsed_ms(self, name: str) -> Optional[float]:
        for n, start, end in self._phases:
            if n == name:
                return (end - start) * 1000.0
        return None

    @property
    def total_ms(self) -> float:
        return (time.perf_counter() - self._started) * 1000.0

    def report(self) -> str:
        """Render the startup report as text (no heavy rich dependency)."""
        phases = [(name, (end - start) * 1000.0) for name, start, end in self._phases]
        total = sum(ms for _, ms in phases)
        lines = ["JARVIS Startup Report", "──────────────────────"]
        for name, ms in sorted(phases, key=lambda item: item[1], reverse=True):
            bar_len = max(1, int(ms / max(total, 1.0) * 40))
            bar = "█" * bar_len
            lines.append(f"  {name:<24} {ms:>7.1f} ms  {bar}")
        lines.append(f"  {'total':<24} {total:>7.1f} ms")
        return "\n".join(lines)


_PROFILER = StartupProfiler()


def get_profiler() -> StartupProfiler:
    return _PROFILER


def startup_report() -> str:
    return _PROFILER.report()
