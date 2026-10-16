"""Two-key MCP trust gate (qwen-code pattern).

A tool from an external MCP server may only ride its declared low-risk /
read-only status to auto-approval when BOTH keys are present: the server is
explicitly trusted AND the workspace is trusted. Missing either key degrades
the call to explicit consent; with no consent channel wired it fails closed —
independent of execution mode.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agent import permissions as permissions_mod  # noqa: E402
from core.agent.permissions import PermissionEngine  # noqa: E402
from core.decision_logger import DecisionLogger  # noqa: E402
from tools.schema import Tool  # noqa: E402


def _mcp_tool(name: str = "calendar.list_events", risk: str = "low") -> Tool:
    return Tool(
        name=name, description="x", parameters={},
        permission="mcp.call", handler=lambda **_: {"ok": True},
        risk=risk, is_destructive=False, source="mcp:calendar",
    )


def _native_tool() -> Tool:
    return Tool(
        name="web.search", description="x", parameters={},
        permission="web.search", handler=lambda **_: {"ok": True},
        risk="low",
    )


def _engine(servers=None, workspace=None, mode="agent", handler=None) -> PermissionEngine:
    kwargs: dict = {"mode": mode, "confirmation_handler": handler}
    if servers is not None:
        kwargs["trusted_mcp_servers"] = servers
    if workspace is not None:
        kwargs["trusted_workspace"] = workspace
    return PermissionEngine(DecisionLogger(), **kwargs)


def test_both_keys_allow_auto_approval():
    engine = _engine(servers=["calendar"], workspace=True)
    allowed, reason = engine._apply_mcp_trust_gate(_mcp_tool(), {}, "t")
    assert allowed is True
    assert reason == ""


def test_missing_workspace_key_fails_closed_without_channel():
    engine = _engine(servers=["calendar"], workspace=False)
    allowed, reason = engine._apply_mcp_trust_gate(_mcp_tool(), {}, "t")
    assert allowed is False
    assert "workspace is not trusted" in reason
    assert "fail closed" in reason


def test_missing_server_key_fails_closed_without_channel():
    engine = _engine(servers=[], workspace=True)
    allowed, reason = engine._apply_mcp_trust_gate(_mcp_tool(), {}, "t")
    assert allowed is False
    assert "not trusted" in reason


def test_prompt_when_channel_wired_and_allow_decision():
    engine = _engine(servers=[], workspace=False, handler=lambda n, a: "once")
    allowed, reason = engine._apply_mcp_trust_gate(_mcp_tool(), {}, "t")
    assert allowed is True
    assert reason == ""


def test_prompt_denial_blocks():
    engine = _engine(servers=[], workspace=True, handler=lambda n, a: "deny")
    allowed, reason = engine._apply_mcp_trust_gate(_mcp_tool(), {}, "t")
    assert allowed is False
    assert "denied" in reason.lower()


def test_native_tool_is_not_gated():
    engine = _engine(servers=[], workspace=False)
    allowed, _ = engine._apply_mcp_trust_gate(_native_tool(), {}, "t")
    assert allowed is True


def test_risky_mcp_tool_delegates_to_risk_gate():
    engine = _engine(servers=[], workspace=False)
    allowed, _ = engine._apply_mcp_trust_gate(_mcp_tool(risk="high"), {}, "t")
    assert allowed is True


def test_risky_mcp_tool_denied_by_risk_gate_when_fail_closed():
    import asyncio

    engine = PermissionEngine(DecisionLogger(), mode="agent", fail_closed_risky=True)
    allowed, reason = asyncio.run(engine.check(_mcp_tool(risk="high"), {}, "t", "s"))
    assert allowed is False
    assert "explicit operator approval" in reason


def test_env_opt_in_trusts_workspace(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_TRUST_MCP_WORKSPACE", "1")
    engine = _engine(servers=["calendar"])
    allowed, _ = engine._apply_mcp_trust_gate(_mcp_tool(), {}, "t")
    assert allowed is True


def test_explicit_workspace_false_wins_over_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_TRUST_MCP_WORKSPACE", "1")
    engine = _engine(servers=["calendar"], workspace=False)
    allowed, reason = engine._apply_mcp_trust_gate(_mcp_tool(), {}, "t")
    assert allowed is False
    assert "workspace is not trusted" in reason


def test_config_file_trust_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path / "mcp_servers.json"
    config.write_text(json.dumps([
        {"name": "calendar", "command": "x", "trusted": True},
        {"name": "sketchy", "command": "y"},
    ]), encoding="utf-8")
    monkeypatch.setattr(permissions_mod, "_MCP_CONFIG_PATH", config)

    engine = _engine(workspace=True)
    allowed, _ = engine._apply_mcp_trust_gate(_mcp_tool(), {}, "t")
    assert allowed is True

    sketchy = _mcp_tool("sketchy.do_thing")
    sketchy.source = "mcp:sketchy"
    allowed, reason = engine._apply_mcp_trust_gate(sketchy, {}, "t")
    assert allowed is False
    assert "not trusted" in reason


def test_missing_config_file_yields_no_trusted_servers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(permissions_mod, "_MCP_CONFIG_PATH", tmp_path / "nope.json")
    engine = _engine(workspace=True)
    allowed, reason = engine._apply_mcp_trust_gate(_mcp_tool(), {}, "t")
    assert allowed is False
    assert "not trusted" in reason


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
