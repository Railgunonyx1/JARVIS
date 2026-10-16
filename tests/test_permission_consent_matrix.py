"""Permission consent matrix (audit Phase 1, issue 2).

The security policy promises that consent-first modes (Controlled, Smart) fail
closed when a destructive/high-risk tool has no wired consent channel. These
tests pin that matrix so the documented guarantee matches the implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agent.permissions import PermissionEngine  # noqa: E402
from core.decision_logger import DecisionLogger  # noqa: E402
from core.mode_manager import ExecutionMode  # noqa: E402
from tools.schema import Tool  # noqa: E402


def _risky_tool() -> Tool:
    return Tool(
        name="filesystem.write",
        description="write a file",
        parameters={},
        permission="filesystem.write",
        handler=lambda **_: {"ok": True},
        risk="high",
        is_destructive=True,
    )


def _engine(mode: str, handler=None, fail_closed=None) -> PermissionEngine:
    kwargs = {"mode": mode, "confirmation_handler": handler}
    if fail_closed is not None:
        kwargs["fail_closed_risky"] = fail_closed
    return PermissionEngine(DecisionLogger(), **kwargs)


def test_consent_matrix_documents_every_mode():
    matrix = PermissionEngine.consent_matrix()
    assert matrix == {
        ExecutionMode.PLAN: False,
        ExecutionMode.CONTROLLED: True,
        ExecutionMode.SMART: True,
        ExecutionMode.AGENT: False,
    }


@pytest.mark.parametrize("mode,expected", [
    ("controlled", True),
    ("smart", True),
    ("agent", False),
    ("plan", False),
])
def test_fail_closed_default_is_mode_derived(mode, expected):
    assert _engine(mode).fail_closed_risky is expected


def test_explicit_override_wins_over_matrix():
    assert _engine("agent", fail_closed=True).fail_closed_risky is True
    assert _engine("controlled", fail_closed=False).fail_closed_risky is False


def test_controlled_risky_without_consent_channel_is_denied():
    engine = _engine("controlled")
    allowed, reason = engine._apply_risk_gate(_risky_tool(), {}, "t", "s")
    assert allowed is False
    assert "explicit operator approval" in reason


def test_agent_risky_without_consent_channel_is_allowed():
    engine = _engine("agent")
    allowed, reason = engine._apply_risk_gate(_risky_tool(), {}, "t", "s")
    assert allowed is True
    assert reason == ""


def test_consent_handler_allow_and_deny():
    allow = _engine("controlled", handler=lambda name, args: "once")
    assert allow._apply_risk_gate(_risky_tool(), {}, "t", "s")[0] is True

    deny = _engine("controlled", handler=lambda name, args: "deny")
    allowed, reason = deny._apply_risk_gate(_risky_tool(), {}, "t", "s")
    assert allowed is False
    assert "denied" in reason.lower()


@pytest.mark.parametrize("start,mode,expected", [
    ("agent", "controlled", True),
    ("agent", "smart", True),
    ("agent", "plan", False),
    ("controlled", "agent", False),
    ("controlled", "smart", True),
    ("smart", "plan", False),
    ("plan", "controlled", True),
])
def test_mode_transition_recomputes_default_posture(start, mode, expected):
    engine = _engine(start)
    engine.set_mode(mode)
    assert engine.fail_closed_risky is expected


def test_mode_transition_to_controlled_fails_closed():
    engine = _engine("agent")
    engine.set_mode("controlled")
    allowed, reason = engine._apply_risk_gate(_risky_tool(), {}, "t", "s")
    assert allowed is False
    assert "explicit operator approval" in reason


def test_explicit_override_survives_mode_transitions():
    engine = _engine("agent", fail_closed=True)
    engine.set_mode("controlled")
    engine.set_mode("agent")
    assert engine.fail_closed_risky is True

    engine = _engine("controlled", fail_closed=False)
    engine.set_mode("agent")
    engine.set_mode("controlled")
    assert engine.fail_closed_risky is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
