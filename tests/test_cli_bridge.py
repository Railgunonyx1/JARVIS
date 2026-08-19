"""Tests for cli.bridge — the Event/State Bus (Phase 4)."""

from __future__ import annotations

from types import SimpleNamespace

from cli.bridge import AgentBridge
from cli.models import (
    ConfirmationRequest,
    EventStatus,
    EventType,
    Mode,
    RiskLevel,
    StepStatus,
)
from cli.renderer import Renderer
from core import events


def _stub_loop(**overrides) -> SimpleNamespace:
    default = {
        "observer": SimpleNamespace(on_event=None),
        "permissions": SimpleNamespace(mode="agent"),
        "router": SimpleNamespace(_last_model=None, _last_provider=None),
        "mem": SimpleNamespace(),
        "_last_result": None,
    }
    default.update(overrides)
    return SimpleNamespace(**default)


def _bridge(renderer=None) -> AgentBridge:
    return AgentBridge(renderer=renderer)


def test_attach_loop_owns_observer():
    loop = _stub_loop()
    bridge = _bridge()
    bridge.attach_loop(loop)
    assert loop.observer.on_event == bridge.on_event


def test_start_run_adds_user_message_and_resets_plan():
    bridge = _bridge()
    bridge.start_run("refactor the auth module")
    assert bridge.state.messages[0].role == "user"
    assert bridge.state.messages[0].content == "refactor the auth module"
    assert bridge.state.plan is not None
    assert bridge.state.plan.goal == "refactor the auth module"
    assert bridge.state.plan.steps == []


def test_step_started_creates_running_event_and_active_plan():
    bridge = _bridge()
    bridge.start_run("do it")
    bridge.on_event(events.STEP_STARTED, {"task_id": "t1", "step": 0, "tool": "filesystem.read"})
    assert len(bridge.state.events) == 1
    ev = bridge.state.events[0]
    assert ev.type == EventType.TOOL
    assert ev.status == EventStatus.RUNNING
    assert ev.tool == "filesystem.read"
    plan_steps = bridge.state.plan.steps
    assert len(plan_steps) == 1
    assert plan_steps[0].status == StepStatus.ACTIVE


def test_step_completed_closes_event_and_plan_step():
    bridge = _bridge()
    bridge.start_run("do it")
    bridge.on_event(events.STEP_STARTED, {"task_id": "t1", "step": 0, "tool": "repo.search"})
    bridge.on_event(events.STEP_COMPLETED, {
        "task_id": "t1", "step": 0, "tool": "repo.search",
        "status": "ok", "duration_ms": 42.0, "error": "",
    })
    ev = bridge.state.events[0]
    assert ev.status == EventStatus.COMPLETED
    assert ev.duration_s == 0.042
    assert bridge.state.plan.steps[0].status == StepStatus.COMPLETED


def test_step_completed_failure_marks_event_failed():
    bridge = _bridge()
    bridge.start_run("do it")
    bridge.on_event(events.STEP_STARTED, {"task_id": "t1", "step": 0, "tool": "shell.execute"})
    bridge.on_event(events.STEP_COMPLETED, {
        "task_id": "t1", "step": 0, "tool": "shell.execute",
        "status": "error", "duration_ms": 10.0, "error": "boom",
    })
    assert bridge.state.events[0].status == EventStatus.FAILED
    assert "boom" in bridge.state.events[0].result
    assert bridge.state.plan.steps[0].status == StepStatus.COMPLETED


def test_permission_denied_emits_security_event_and_status():
    bridge = _bridge()
    bridge.start_run("do it")
    bridge.on_event(events.PERMISSION_OBSERVED, {
        "task_id": "t1", "tool": "shell.execute",
        "allowed": False, "reason": "not allowed in plan mode",
    })
    sec = [e for e in bridge.state.events if e.type == EventType.SECURITY]
    assert len(sec) == 1
    assert sec[0].status == EventStatus.FAILED
    assert "denied" in sec[0].result
    assert "blocked" in bridge.state.status_message


def test_permission_allowed_emits_security_completed():
    bridge = _bridge()
    bridge.start_run("do it")
    bridge.on_event(events.PERMISSION_OBSERVED, {
        "task_id": "t1", "tool": "repo.search",
        "allowed": True, "reason": "safe",
    })
    sec = [e for e in bridge.state.events if e.type == EventType.SECURITY]
    assert len(sec) == 1
    assert sec[0].status == EventStatus.COMPLETED


def test_finish_run_appends_agent_message_and_tokens():
    bridge = _bridge()
    bridge.start_run("do it")
    result = SimpleNamespace(
        response="done!",
        state=SimpleNamespace(tool_calls=[]),
        observation={"context_usage": {"total_tokens": 1234, "total_budget": 32000}},
    )
    bridge.finish_run(result)
    assert bridge.state.messages[-1].role == "agent"
    assert bridge.state.messages[-1].content == "done!"
    assert bridge.state.tokens_used == 1234


def test_fail_run_recovers_prompt_state():
    bridge = _bridge()
    bridge.start_run("do it")
    bridge.on_event(events.STEP_STARTED, {"task_id": "t1", "step": 0, "tool": "repo.search"})
    bridge.fail_run("provider unreachable")
    assert bridge.state.events[0].status == EventStatus.FAILED
    assert "provider unreachable" in bridge.state.status_message
    assert bridge.state.messages[0].role == "user"  # prompt remains usable


def test_engine_exception_in_translation_never_escapes():
    bridge = _bridge()

    class Boom:
        def get(self, *a):
            raise RuntimeError("boom")

    # monkeypatch the translation to force a crash
    def broken(name, payload):
        raise RuntimeError("translation crash")

    bridge._translate = broken
    bridge.on_event(events.STEP_STARTED, {"task_id": "t1", "step": 0, "tool": "x"})  # no raise


def test_pull_status_reflects_mode_and_model():
    loop = _stub_loop(
        router=SimpleNamespace(_last_model="gemini-2.0-flash", _last_provider="gemini"),
    )
    bridge = _bridge()
    bridge.attach_loop(loop)
    bridge.pull_status()
    assert bridge.state.mode == Mode.AGENT
    assert bridge.state.model == "gemini/gemini-2.0-flash"
    assert bridge.state.connection == "ONLINE"


def test_confirmation_defaults_to_deny():
    bridge = _bridge()
    decision = bridge.request_confirmation(
        'package.remove("example")', scope="system package",
        risk=RiskLevel.HIGH, reversible=False,
    )
    assert decision == "deny"


def test_confirmation_uses_handler():
    bridge = _bridge()
    decisions = []

    def handler(req: ConfirmationRequest) -> str:
        decisions.append(req)
        return "run"

    bridge.confirmation_handler = handler
    decision = bridge.request_confirmation("shell.execute", risk=RiskLevel.MEDIUM)
    assert decision == "run"
    assert len(decisions) == 1
    assert decisions[0].operation == "shell.execute"


def test_bridge_shares_renderer_state():
    renderer = Renderer()
    bridge = _bridge(renderer=renderer)
    assert bridge.state is renderer.state


def test_bridge_refresh_audit_loads_sections():
    from cli.models import AuditSection

    bridge = _bridge()
    try:
        entries = bridge.refresh_audit(limit=5)
    except Exception:
        entries = []
    assert isinstance(entries, list)
    assert any(isinstance(s, AuditSection) for s in bridge.state.audit_sections)


def test_bridge_refresh_memory_empty_without_loop():
    bridge = _bridge()
    bridge.refresh_memory("auth")
    assert bridge.state.memory_query == "auth"
    assert isinstance(bridge.state.memory_hits, list)


def test_bridge_list_models_empty_without_loop():
    bridge = _bridge()
    assert bridge.list_models() == []


def test_confirmation_call_routes_through_handler():
    bridge = _bridge()
    calls = []

    def handler(req: ConfirmationRequest) -> str:
        calls.append(req)
        return "once"

    bridge.confirmation_handler = handler
    decision = bridge.confirmation_call("shell.execute", {"command": "rm -rf"})
    assert decision == "once"
    assert calls[0].operation == "shell.execute"
    assert calls[0].risk == RiskLevel.CRITICAL
    assert "command" in calls[0].details


def test_confirmation_call_defaults_deny_no_handler():
    bridge = _bridge()
    assert bridge.confirmation_call("package.remove", {}) == "deny"


def test_confirmation_call_medium_risk_default():
    bridge = _bridge()
    seen = []

    def handler(req: ConfirmationRequest) -> str:
        seen.append(req)
        return "deny"

    bridge.confirmation_handler = handler
    bridge.confirmation_call("repo.search", {"query": "auth"})
    assert seen[0].risk == RiskLevel.MEDIUM


def test_attach_loop_then_pull_status_uses_loop_state():
    bridge = _bridge()
    loop = _stub_loop(mem=None)
    bridge.attach_loop(loop)
    bridge.pull_status()
    assert bridge.state.memory_enabled is False
