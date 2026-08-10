"""Reactive task display for the JARVIS MK-X terminal (Phase 4).

A single Rich ``Live`` region that re-renders ONLY when the agent emits an
event through the TaskObserver callback (task.started / step.started /
step.completed / task.finished / permission.observed). There is no polling
and no fixed refresh loop — ``auto_refresh=False`` guarantees the terminal
is untouched unless something actually changed.

Render contents (compact, keyboard-first):
    - task id + goal
    - running step chain (tool, status, duration)
    - mode / provider / model / elapsed time
    - Headroom context bars (system / memory / files / messages)
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from core import events
from core.agent.observer import TaskObserver

_STATUS_MARK = {"ok": "+", "error": "!", "denied": "x", "running": ">"}

_SECTION_LABELS = [
    ("system_tokens", "System"),
    ("memory_tokens", "Memory"),
    ("files_tokens", "Files"),
    ("messages_tokens", "Conv"),
]


def _bar(ratio: float, width: int = 12) -> Text:
    filled = max(0, min(width, int(round(ratio * width))))
    style = "green" if ratio < 0.8 else ("yellow" if ratio < 1.0 else "red")
    return Text("█" * filled + "░" * (width - filled), style=style)


class LiveTaskDisplay:
    """Event-driven Live region bound to a TaskObserver."""

    def __init__(self, console: Optional[Console] = None,
                 status_getter: Optional[Callable[[], Dict[str, Any]]] = None,
                 enable: bool = True, transient: bool = True) -> None:
        self.console = console or Console()
        self._status_getter = status_getter
        self._enable = enable
        self._transient = transient
        self._observer: Optional[TaskObserver] = None
        self._live: Optional[Live] = None
        self._started = 0.0
        self._goal = ""
        self.renders = 0
        self.render_ms = 0.0
        self.last_render_ms = 0.0

    def attach(self, observer: TaskObserver) -> None:
        """Hook into the observer's event stream (no-op when disabled)."""
        self._observer = observer
        observer.on_event = self._on_event

    def start(self) -> None:
        # Rich's Live already degrades gracefully on non-terminals (a single
        # plain print, no ANSI redraw), so no extra is_terminal gate here.
        if not self._enable:
            return
        self._started = time.time()
        self._live = Live(
            Group(Text("starting…")),
            console=self.console,
            auto_refresh=False,
            transient=self._transient,
        )
        self._live.start()
        self._refresh()

    def stop(self) -> None:
        if self._live is not None:
            try:
                self._live.stop()
            finally:
                self._live = None

    def _on_event(self, name: str, payload: Dict[str, Any]) -> None:
        if not self._enable or self._live is None:
            return
        if name == events.TASK_STARTED:
            self._goal = payload.get("goal", "")
        elif name == "run.queued":
            self._goal = f"{payload.get('goal', self._goal)} (queued — previous task running)"
        self._refresh()

    def _refresh(self) -> None:
        if self._live is None:
            return
        t0 = time.perf_counter()
        self._live.update(self._render())
        ms = (time.perf_counter() - t0) * 1000.0
        self.renders += 1
        self.render_ms += ms
        self.last_render_ms = ms

    def _render(self) -> Group:
        try:
            summary = self._observer.summary() if self._observer else {}
        except RuntimeError:
            summary = {}
        lines: list = []

        goal = self._goal or summary.get("goal", "")
        lines.append(Text(f"task {summary.get('task_id', '')} · {goal[:80]}",
                          style="bold"))

        steps = summary.get("steps", [])
        if steps:
            chain = "  ".join(
                f"{_STATUS_MARK.get(s.get('status'), '?')} {s.get('tool', '')}"
                + (f" {s.get('duration_ms', 0):.0f}ms" if s.get("duration_ms") else "")
                for s in steps
            )
            lines.append(Text("steps  " + chain))
        else:
            lines.append(Text("steps  (awaiting model…)", style="dim"))

        status: Dict[str, Any] = {}
        if self._status_getter is not None:
            try:
                status = self._status_getter() or {}
            except Exception:
                status = {}

        elapsed = time.time() - self._started if self._started else 0.0
        meta_bits = []
        meta_bits.append(f"mode={status.get('mode', '?')}")
        if status.get("provider"):
            meta_bits.append(f"model={status.get('provider')}/{status.get('model', '')}")
        if summary.get("tokens_used"):
            meta_bits.append(f"tokens={summary['tokens_used']}")
        meta_bits.append(f"elapsed={int(elapsed)}s")
        lines.append(Text("  ".join(meta_bits), style="dim"))

        usage = summary.get("context_usage") or {}
        if usage:
            budget = usage.get("budget") or {}
            bars = []
            for field, label in _SECTION_LABELS:
                tokens = usage.get(field, 0)
                section_budget = budget.get(field.replace("_tokens", ""), 0)
                ratio = (tokens / section_budget) if section_budget else 0.0
                bars.append(Text(f"{label} {tokens} "))
                bars.append(_bar(ratio))
            compact = " [compacted]" if usage.get("compacted") else ""
            bars.append(Text(f"  {usage.get('total_tokens', 0)}/{usage.get('total_budget', 0)} tokens{compact}", style="dim"))
            lines.append(Group(*bars))

        return Group(*lines)

    def panel(self) -> Panel:
        return Panel(self._render(), title="JARVIS MK-X", border_style="cyan")
