"""Tests for the UI prototype and the hybrid full-screen views.

The prototype (``cli.ui_demo``) is a visual reference with fake events — it
must never be imported by the production REPL path. These tests only exercise
its render methods against a captured console (no Live, no sleeps).
"""

from __future__ import annotations

import io

from rich.console import Console

from cli.commands import CommandRegistry
from cli.models import AgentEvent
from cli.renderer import Renderer


def _capture(console: Console, renderable) -> str:
    console.print(renderable)
    return console.file.getvalue()


def _console(width: int = 140) -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, width=width, force_terminal=True), buf


def _demo_ui(width: int = 140):
    import cli.ui_demo as ui_demo

    console, _ = _console(width)
    ui_demo.console = console
    ui = ui_demo.JarvisTerminalUI()
    ui.state.messages.append(ui_demo.Message("user", "analyze authentication"))
    ui.state.messages.append(ui_demo.Message("assistant", "I'll inspect the auth module first."))
    tool = ui_demo.ToolEvent(
        id="1", name="repo.search", detail="rg authentication",
        status=ui_demo.ToolStatus.SUCCESS, result="8 files found", duration="0.3s",
    )
    ui.state.tools.append(tool)
    return ui_demo, ui, console


# ── prototype workspaces ─────────────────────────────────────────────────────


def test_demo_conversation_shows_messages_and_tools():
    ui_demo, ui, console = _demo_ui()
    text = _capture(console, ui.render())
    assert "analyze authentication" in text
    assert "auth module" in text
    assert "repo.search" in text
    assert "8 files found" in text


def test_demo_plan_workspace():
    ui_demo, ui, console = _demo_ui()
    ui.state.plan = ui_demo.Plan(steps=[
        ui_demo.PlanStep("Inspect token validation", ui_demo.PlanStatus.ACTIVE),
        ui_demo.PlanStep("Run authentication tests", ui_demo.PlanStatus.PENDING),
    ])
    ui.state.current_workspace = "plan"
    text = _capture(console, ui.render())
    assert "PLAN" in text
    assert "Inspect token validation" in text


def test_demo_palette_workspace():
    ui_demo, ui, console = _demo_ui()
    ui.state.current_workspace = "palette"
    text = _capture(console, ui.render())
    assert "COMMAND PALETTE" in text
    assert "/plan" in text


def test_demo_status_workspace():
    ui_demo, ui, console = _demo_ui()
    ui.state.current_workspace = "status"
    text = _capture(console, ui.render())
    assert "STATUS" in text
    assert ui.state.model in text


# ── production renderer: hybrid full-screen views ───────────────────────────


def test_renderer_task_screen_streams_conversation_and_activity():
    console, _ = _console()
    r = Renderer(console=console)
    r.add_message("user", "list the files")
    r.add_message("agent", "scanning the workspace")
    r.state.events.append(AgentEvent.tool_start("repo.search"))
    text = _capture(console, r.render_task_screen())
    assert "list the files" in text
    assert "scanning the workspace" in text
    assert "repo.search" in text


def test_renderer_task_screen_narrow_no_activity_split():
    console, _ = _console(width=90)
    r = Renderer(console=console)
    r.add_message("user", "hi")
    text = _capture(console, r.render_task_screen())
    assert "hi" in text


def test_renderer_palette_lists_entries():
    console, _ = _console()
    r = Renderer(console=console)
    text = _capture(console, r.render_palette([
        ("/help", "Show commands"),
        ("chat", "Conversation (default)"),
    ]))
    assert "COMMAND PALETTE" in text
    assert "/help" in text
    assert "Show commands" in text


def test_palette_command_uses_renderer():
    console, _ = _console()
    r = Renderer(console=console)
    reg = CommandRegistry(r)
    assert reg.dispatch("/palette") is True
    text = console.file.getvalue()
    assert "COMMAND PALETTE" in text
    assert "/help" in text
