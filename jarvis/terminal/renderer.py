"""Sprint 11 -- Rich renderer: converts SessionState into Rich renderables.

Pure display layer -- never mutates state or makes I/O calls.
Each render_* method produces a self-contained Rich renderable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from rich.renderable import RenderableType

from jarvis.terminal.breakpoints import classify_width, panels_for_breakpoint
from jarvis.terminal.types import (
    Plan,
    SessionState,
    SessionStatus,
    StepStatus,
)

_STYLE_MAP = {
    SessionStatus.IDLE: ("bold green", "IDLE"),
    SessionStatus.RUNNING: ("bold cyan", "RUNNING"),
    SessionStatus.WAITING_CONFIRM: ("bold yellow", "CONFIRM?"),
    SessionStatus.PAUSED: ("bold dim", "PAUSED"),
    SessionStatus.ERROR: ("bold red", "ERROR"),
}

_STEP_STYLE = {
    StepStatus.PENDING: "dim",
    StepStatus.RUNNING: "bold cyan",
    StepStatus.COMPLETED: "bold green",
    StepStatus.FAILED: "bold red",
    StepStatus.SKIPPED: "dim",
    StepStatus.CANCELLED: "dim yellow",
}


class TerminalRenderer:
    """Renders SessionState into Rich renderables for console output."""

    def __init__(self, width: int = 80):
        self._width = width
        self._bp = classify_width(width)

    def update_width(self, width: int) -> None:
        self._width = width
        self._bp = classify_width(width)

    def render(self, state: SessionState) -> RenderableType:
        """Render the full state as a Group of panels."""
        panels: list[RenderableType] = []
        visible = panels_for_breakpoint(self._bp)

        if "status_bar" in visible:
            panels.append(self.render_status_bar(state))
        if "conversation" in visible:
            conv = self.render_conversation(state)
            if conv:
                panels.append(conv)
        if "plan" in visible and state.plan.steps:
            panels.append(self.render_plan(state.plan))
        if "activity" in visible and state.activity:
            panels.append(self.render_activity(state))
        if "code" in visible and state.code_files:
            panels.append(self.render_code(state))
        if "memory" in visible and state.memory_hits:
            panels.append(self.render_memory(state))

        if state.pending_confirmation:
            panels.append(self.render_confirmation(state))

        if state.error:
            panels.append(Panel(
                Text(state.error, style="bold red"),
                title="Error", border_style="red",
            ))

        if not panels:
            return Text("Ready.", style="dim")
        return Group(*panels)

    def render_status_bar(self, state: SessionState) -> Panel:
        style, label = _STYLE_MAP.get(state.status, ("white", state.status.value))
        parts = [Text(f" {label} ", style=style)]
        if state.provider:
            parts.append(Text(f" {state.provider}", style="dim"))
        if state.model:
            parts.append(Text(f"/{state.model}", style="dim"))
        if state.tokens_prompt or state.tokens_completion:
            parts.append(Text(
                f"  {state.tokens_prompt}+{state.tokens_completion}tok",
                style="dim",
            ))
        if state.latency_ms > 0:
            parts.append(Text(f" {state.latency_ms:.0f}ms", style="dim"))
        parts.append(Text(f"  [{state.layout.value}]", style="dim"))
        return Panel(
            Group(*parts),
            style="on grey11",
            box=None,
            expand=True,
        )

    def render_conversation(self, state: SessionState) -> Panel | None:
        if not state.messages:
            return None
        parts: list[RenderableType] = []
        for msg in state.messages[-20:]:
            if msg.role == "user":
                parts.append(Text(f"You: {msg.content}", style="bold"))
            elif msg.role == "assistant":
                parts.append(Markdown(msg.content) if "```" in msg.content or "#" in msg.content
                                 else Text(f"JARVIS: {msg.content}", style="cyan"))
            elif msg.role == "tool":
                parts.append(Text(f"  [tool] {msg.content[:200]}", style="dim"))
        if not parts:
            return None
        return Panel(Group(*parts), title="Conversation", border_style="blue")

    def render_plan(self, plan: Plan) -> Panel:
        table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        table.add_column("#", width=3)
        table.add_column("Step", ratio=3)
        table.add_column("Status", width=10)
        table.add_column("Tools", width=8)

        for i, step in enumerate(plan.steps):
            style = _STEP_STYLE.get(step.status, "")
            status_text = step.status.value.upper()
            tools = ", ".join(t.name for t in step.tool_runs) if step.tool_runs else "-"
            table.add_row(
                Text(str(i + 1), style=style),
                Text(step.description[:60], style=style),
                Text(status_text, style=style),
                Text(tools, style="dim"),
            )
        return Panel(table, title=f"Plan: {plan.goal[:60]}", border_style="magenta")

    def render_activity(self, state: SessionState) -> Panel:
        lines: list[Text] = []
        for evt in state.activity[-15:]:
            name = evt.name
            detail = ""
            if "tool" in evt.payload:
                detail = f" {evt.payload['tool']}"
            if "duration_ms" in evt.payload:
                detail += f" ({evt.payload['duration_ms']:.0f}ms)"
            lines.append(Text(f"  {name}{detail}", style="dim"))
        return Panel(Group(*lines), title="Activity", border_style="yellow")

    def render_code(self, state: SessionState) -> Panel:
        from rich.syntax import Syntax
        parts: list[RenderableType] = []
        for f in state.code_files[-3:]:
            lang = f.language or "python"
            content = f.diff if f.diff else f.content
            parts.append(Syntax(content[:500], lang, theme="monokai", line_numbers=True))
            parts.append(Text(f"  {f.path}", style="dim"))
        return Panel(Group(*parts), title="Code", border_style="green")

    def render_memory(self, state: SessionState) -> Panel:
        table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        table.add_column("Source", width=8)
        table.add_column("Content", ratio=3)
        table.add_column("Score", width=6)
        for hit in state.memory_hits[-5:]:
            table.add_row(
                Text(hit.source, style="dim"),
                Text(hit.content[:80]),
                Text(f"{hit.score:.2f}", style="dim"),
            )
        return Panel(table, title="Memory", border_style="cyan")

    def render_confirmation(self, state: SessionState) -> Panel:
        req = state.pending_confirmation
        if req is None:
            return Panel("?", title="Confirm")
        return Panel(
            Group(
                Text(f"Tool: {req.tool_name}", style="bold"),
                Text(f"  {req.description}", style="dim"),
                Text("  [Y/n] Confirm?", style="bold yellow"),
            ),
            title="Permission Required",
            border_style="yellow",
        )
