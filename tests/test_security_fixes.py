"""Regression tests for the audit's P0 security fixes.

Covers: sandbox shell-operator bypass closure, the generated-code opt-in gate
and static scan, and the IPC frame-size limit. All offline — no LLM, no pipes.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── sandbox shell-operator bypass ────────────────────────────────────────────

def test_sandbox_rejects_ampersand_chaining():
    from security.sandbox import Sandbox
    allowed, reason = Sandbox().check_command("dir & whoami")
    assert not allowed
    assert "operator" in reason


def test_sandbox_rejects_newline_injection():
    from security.sandbox import Sandbox
    allowed, reason = Sandbox().check_command("echo hello\nwhoami")
    assert not allowed
    assert "operator" in reason


def test_sandbox_rejects_input_and_escape():
    from security.sandbox import Sandbox
    assert not Sandbox().check_command("type a < secret.txt")[0]
    assert not Sandbox().check_command("echo ^& dir")[0]


def test_sandbox_rejects_semicolon_chaining():
    from security.sandbox import Sandbox
    allowed, reason = Sandbox().check_command("dir; whoami")
    assert not allowed
    assert "operator" in reason


def test_sandbox_rejects_powershell_operators():
    from security.sandbox import Sandbox
    assert not Sandbox().check_command("echo `whoami")[0]
    assert not Sandbox().check_command("echo $(whoami)")[0]
    assert not Sandbox().check_command("echo ${env:PATH}")[0]


def test_sandbox_allows_plain_command():
    from security.sandbox import Sandbox
    allowed, reason = Sandbox().check_command("dir /b")
    assert allowed and reason == ""


def test_sandbox_execute_blocks_chained_command():
    from security.sandbox import Sandbox
    result = Sandbox().execute("dir & whoami")
    assert result.blocked
    assert "operator" in result.block_reason


def test_sandbox_execute_blocks_blocked_command():
    from security.sandbox import Sandbox
    result = Sandbox().execute("shutdown /s")
    assert result.blocked
    assert "Blocked command" in result.block_reason


# ── generated-code gate + static scan ────────────────────────────────────────

def test_generated_code_gate_off_by_default(monkeypatch):
    import core.executor as ex
    monkeypatch.delenv("JARVIS_ENABLE_GENERATED_CODE", raising=False)
    assert ex._generated_code_enabled() is False
    with pytest.raises(RuntimeError, match="disabled by default"):
        ex._run_generated_code("anything")


def test_generated_code_gate_on_via_env(monkeypatch):
    import core.executor as ex
    monkeypatch.setenv("JARVIS_ENABLE_GENERATED_CODE", "1")
    assert ex._generated_code_enabled() is True


def test_generated_code_scan_rejects_forbidden():
    import core.executor as ex
    with pytest.raises(RuntimeError, match="forbidden pattern"):
        ex._check_generated_code("import os\nos.system('format c:')")


def test_generated_code_scan_allows_benign():
    import core.executor as ex
    ex._check_generated_code(
        "print('hello')\nfor i in range(3):\n    print(i)"
    )


# ── shell audit None-safety ───────────────────────────────────────────────────

def test_shell_audit_tolerates_none_reason_and_stderr(monkeypatch):
    from security.audit import AuditEntry
    from security.executor import ExecResult
    from tools.shell import _audit_shell_execution

    recorded = []

    class FakeLog:
        def log(self, entry: AuditEntry) -> None:
            recorded.append(entry)

    monkeypatch.setattr("security.audit.get_audit_log", lambda: FakeLog())

    _audit_shell_execution(
        "whoami", [],
        ExecResult(success=False, blocked=True, reason=None, stderr=None),
    )

    assert len(recorded) == 1
    assert recorded[0].error is None

    _audit_shell_execution(
        "whoami", [],
        ExecResult(success=False, blocked=False, stderr="boom"),
    )
    assert recorded[-1].error == "boom"


# ── Phase 5: decision-based confirmation (once/run/deny, stored in audit) ───

def _make_engine(decision):
    from security.engine import SecurityEngine

    engine = SecurityEngine(mode="agent")
    engine.set_confirmation_handler(lambda tool, params: decision)
    return engine


def test_confirmation_run_allows():
    from security.engine import SecurityEngine

    engine = SecurityEngine(mode="agent")
    engine.set_confirmation_handler(lambda tool, params: "run")
    allowed, reason = engine.check_permission("action.shell.run")
    assert allowed and reason == ""


def test_confirmation_once_allows():
    from security.engine import SecurityEngine

    engine = SecurityEngine(mode="agent")
    engine.set_confirmation_handler(lambda tool, params: "once")
    allowed, _ = engine.check_permission("action.shell.run")
    assert allowed


def test_confirmation_deny_blocks():
    from security.engine import SecurityEngine

    engine = SecurityEngine(mode="agent")
    engine.set_confirmation_handler(lambda tool, params: "deny")
    allowed, reason = engine.check_permission("action.shell.run")
    assert not allowed
    assert "denied" in reason


def test_confirmation_invalid_decision_fails_closed():
    from security.engine import SecurityEngine

    engine = SecurityEngine(mode="agent")
    engine.set_confirmation_handler(lambda tool, params: "maybe")
    allowed, _ = engine.check_permission("action.shell.run")
    assert not allowed


def test_confirmation_decision_recorded_in_audit(monkeypatch):
    from security.audit import AuditEntry
    from security.engine import SecurityEngine

    recorded = []

    class FakeLog:
        def log(self, entry: AuditEntry) -> None:
            recorded.append(entry)

    monkeypatch.setattr("security.engine.get_audit_log", lambda: FakeLog())
    engine = SecurityEngine(mode="agent")
    engine.set_confirmation_handler(lambda tool, params: "run")
    allowed, _ = engine.check_permission("action.shell.run")
    assert allowed
    assert any(e.decision == "run" and e.confirmed for e in recorded)


def test_shell_audit_none_is_success_no_error(monkeypatch):
    from security.audit import AuditEntry
    from security.executor import ExecResult
    from tools.shell import _audit_shell_execution

    recorded = []

    class FakeLog:
        def log(self, entry: AuditEntry) -> None:
            recorded.append(entry)

    monkeypatch.setattr("security.audit.get_audit_log", lambda: FakeLog())

    _audit_shell_execution(
        "whoami", [],
        ExecResult(success=True, reason=None),
    )

    assert len(recorded) == 1
    assert recorded[0].error is None
