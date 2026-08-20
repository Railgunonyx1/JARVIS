"""Reactive task display for the JARVIS MK-X terminal (Phase 4 + hybrid UI).

A single Rich ``Live`` region that re-renders ONLY when the agent emits an
event through the TaskObserver callback (task.started / step.started /
step.completed / task.finished / permission.observed) or a streaming token
arrives (``stream_delta``). There is no polling and no fixed refresh loop —
``auto_refresh=False`` guarantees the terminal is untouched unless something
actually changed, and refreshes are throttled to ~12 FPS so fast streams stay
smooth without hammering the console.

Two render modes:
    - full-screen task view (``screen=True`` + ``renderable_provider``): the
      interactive REPL swaps to the alternate screen during a run and renders
      the live conversation + activity from the renderer; when the run ends the
      Live collapses back into the scrolled log (hybrid conversation-first UI).
    - compact panel (default): the Phase 4 inline summary used by one-shot runs.

Render contents (compact, keyboard-first):
    - task id + goal
    - running step chain (tool, status, duration)
    - mode / provider / model / elapsed time
    - Headroom context bars (system / memory / files / messages)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from core import events
from core.agent.observer import TaskObserver

# ~12 FPS ceiling: delta bursts only repaint every 80ms at most.
_MIN_REFRESH_S = 1.0 / 12.0

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

    def __init__(self, console: Console | None = None,
                 status_getter: Callable[[], dict[str, Any]] | None = None,
                 enable: bool = True, transient: bool = True,
                 renderable_provider: Callable[[], RenderableType] | None = None,
                 screen: bool = False) -> None:
        self.console = console or Console()
        self._status_getter = status_getter
        self._enable = enable
        self._transient = transient
        self._renderable_provider = renderable_provider
        self._screen = screen
        self._observer: TaskObserver | None = None
        self._live: Live | None = None
        self._started = 0.0
        self._goal = ""
        self._last_refresh = 0.0
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
        self._last_refresh = 0.0
        self._live = Live(
            self._content(),
            console=self.console,
            auto_refresh=False,
            transient=self._transient,
            screen=self._screen,
        )
        self._live.start()
        self._refresh(force=True)

    def stop(self) -> None:
        if self._live is not None:
            try:
                self._live.stop()
            finally:
                self._live = None

    @contextmanager
    def pause(self):
        """Suspend the alternate screen while blocking on user input (e.g. a
        security confirmation), then re-enter it and repaint on exit."""
        live = self._live
        if live is not None:
            live.stop()
            self._live = None
        try:
            yield
        finally:
            if self._enable and live is not None:
                self._live = live
                self._live.start()
                self._refresh(force=True)

    def _on_event(self, name: str, payload: dict[str, Any]) -> None:
        if not self._enable or self._live is None:
            return
        if name == events.TASK_STARTED:
            self._goal = payload.get("goal", "")
        elif name == "run.queued":
            self._goal = f"{payload.get('goal', self._goal)} (queued — previous task running)"
        self._refresh()

    def stream_delta(self, delta: str) -> None:
        """A streaming token arrived — repaint the task view (throttled)."""
        self._refresh()

    def _refresh(self, force: bool = False) -> None:
        if self._live is None:
            return
        now = time.perf_counter()
        if not force and (now - self._last_refresh) < _MIN_REFRESH_S:
            return
        self._last_refresh = now
        t0 = now
        self._live.update(self._content())
        ms = (time.perf_counter() - t0) * 1000.0
        self.renders += 1
        self.render_ms += ms
        self.last_render_ms = ms

    def _content(self) -> RenderableType:
        """Renderable source.  Lifecycle-only: delegates entirely to the provider.

        The provider (Renderer.render_task_screen) is the sole presentation
        authority.  LiveTaskDisplay owns only lifecycle (start/stop/refresh).
        """
        if self._renderable_provider is not None:
            try:
                return self._renderable_provider()
            except Exception as exc:
                import logging
                logger = logging.getLogger("jarvis.ux")
                logger.exception("renderable provider error")
                return Group(Text(f"[error] render error: {exc}", style="dim"))
        # Fallback: minimal status when no provider is wired (tests, pipes)
        return self._minimal_fallback()

    def _minimal_fallback(self) -> Group:
        """Minimal fallback when no Renderer is attached.  Not a presentation path."""
        lines: list = [Text(f"JARVIS · {self._goal or '(no goal)'}", style="bold")]
        status: dict[str, Any] = {}
        if self._status_getter is not None:
            try:
                status = self._status_getter() or {}
            except Exception:
                pass
        elapsed = time.time() - self._started if self._started else 0.0
        meta = [f"mode={status.get('mode', '?')}" , f"elapsed={int(elapsed)}s"]
        if status.get("provider"):
            meta.append(f"model={status.get('provider')}/{status.get('model', '')}")
        lines.append(Text("  ".join(meta), style="dim"))
        return Group(*lines)

    def panel(self) -> Panel:
        """Legacy panel accessor — prefer LiveTaskDisplay for new code."""
        return Panel(self._minimal_fallback(), title="JARVIS MK-X", border_style="cyan")
