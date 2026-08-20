"""Smoke tests for the terminal UI layer (v2, terminal-first architecture)."""

from __future__ import annotations

from cli.commands import CommandRegistry
from cli.layout import LayoutManager, LayoutMode
from cli.models import (
    AgentEvent,
    ConfirmationRequest,
    EventStatus,
    Mode,
    Plan,
    RiskLevel,
    StepStatus,
)
from cli.renderer import Renderer
from cli.theme import build_rich_theme, get_symbols


def test_layout_modes():
    lm = LayoutManager()
    lm.set_mode("minimal")
    assert lm.detect_mode() == LayoutMode.MINIMAL
    lm.set_mode("code")
    assert lm.detect_mode() == LayoutMode.CODE


def test_panel_toggle():
    lm = LayoutManager()
    assert lm.config.panels["plan"].visible is True
    lm.toggle_panel("plan")
    assert lm.config.panels["plan"].visible is False


def test_plan_model():
    plan = Plan.new("Fix auth", ["Understand", "Locate", "Fix"])
    assert plan.steps[0].status == StepStatus.ACTIVE
    assert plan.revision == 1
    plan.advance(plan.steps[0].id, StepStatus.COMPLETED)
    assert plan.steps[0].status == StepStatus.COMPLETED
    assert plan.revision == 2


def test_agent_event_lifecycle():
    e = AgentEvent.tool_start("shell.execute", "pytest -q")
    assert e.status == EventStatus.RUNNING
    e.complete("184 passed", duration_s=18.4)
    assert e.status == EventStatus.COMPLETED
    assert e.duration_s == 18.4


def test_renderer_plan_and_events():
    r = Renderer()
    plan = Plan.new("Test", ["A", "B", "C"])
    plan.steps[0].status = StepStatus.COMPLETED
    plan.steps[1].status = StepStatus.ACTIVE
    r.set_plan(plan)
    assert r.render_plan() is not None

    e = AgentEvent.tool_start("repo.search", "auth")
    r.push_event(e)
    assert r.state.tools_active == 1
    e.complete("8 results", duration_s=1.2)
    r.update_event(e)
    assert r.state.tools_active == 0
    assert r.render_activity() is not None


def test_status_collapse_smoke():
    from rich.console import Console
    console = Console(width=120, force_terminal=True)
    r = Renderer(console=console)
    r.set_mode(Mode.AGENT)
    r.set_model("gemini")
    r.set_tokens(8200, 32000)
    text = r.render_status()
    assert "JARVIS" in text.plain
    assert "agent" in text.plain.lower()
    assert "gemini" in text.plain
    assert "8.2K/32K" in text.plain


def test_status_collapse_narrow():
    from rich.console import Console
    console = Console(width=60, force_terminal=True)
    r = Renderer(console=console)
    r.set_mode(Mode.AGENT)
    r.set_model("gemini")
    r.set_tokens(8200, 32000)
    text = r.render_status()
    assert "JARVIS" not in text.plain
    assert "agent" in text.plain.lower()
    assert "8.2K/32K" in text.plain


def test_task_screen_uses_responsive_layout():
    from io import StringIO
    from rich.console import Console
    out = StringIO()
    console = Console(width=120, force_terminal=True, file=out)
    r = Renderer(console=console)
    r.set_model("gemini")
    r.set_tokens(1000, 32000)
    r.add_message("user", "fix the tests")
    r.add_message("agent", "Running pytest now.")
    r.state.events.append(AgentEvent.tool_start("shell.execute", "pytest"))
    screen = r.render_task_screen()
    console.print(screen)
    captured = out.getvalue()
    assert "fix the tests" in captured
    assert "JARVIS" in captured


def test_confirmation_model():
    req = ConfirmationRequest(
        operation='package.remove("example")',
        risk=RiskLevel.HIGH,
        scope="system package",
        reversible=False,
    )
    r = Renderer()
    r.set_confirmation(req)
    panel = r.render_confirmation()
    assert panel is not None


def test_commands_help():
    r = Renderer()
    reg = CommandRegistry(r)
    assert "help" in reg.list_commands()
    assert "workspace" in reg.list_commands()
    assert "palette" in reg.list_commands()
    assert reg.dispatch("/nonexistent") is True


def test_commands_wired_backends_registered():
    r = Renderer()
    reg = CommandRegistry(r)
    for name in ("model", "context", "sessions", "resume", "permissions",
                 "audit", "memory", "tools"):
        assert name in reg.list_commands(), f"missing wired command /{name}"


def test_commands_model_uses_renderer_state():
    r = Renderer()
    r.set_model("gemini/exp")
    r.set_tokens(4100, 32000)
    reg = CommandRegistry(r)
    assert reg.dispatch("/model") is True


def test_commands_unknown_mode_rejected():
    r = Renderer()
    reg = CommandRegistry(r)
    assert reg.dispatch("/mode nope") is True
    assert r.state.mode == Mode.AGENT


def test_symbols_ascii_fallback():
    uni = get_symbols(True)
    ascii_ = get_symbols(False)
    assert uni["done"] != ascii_["done"]
    assert ascii_["done"] == "+"


def test_theme_builds():
    t = build_rich_theme()
    assert t is not None


def test_modes_are_policies():
    r = Renderer()
    r.set_mode("controlled")
    assert r.state.mode == Mode.CONTROLLED
    r.set_mode(Mode.SMART)
    assert r.state.mode == Mode.SMART
