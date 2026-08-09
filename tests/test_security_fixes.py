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


# ── IPC frame-size limit ─────────────────────────────────────────────────────

def test_decode_line_rejects_oversized_frame():
    from runtime.transport.protocol import MAX_FRAME_SIZE, decode_line
    oversized = b" " * MAX_FRAME_SIZE + b"{}"
    with pytest.raises(ValueError, match="frame too large"):
        decode_line(oversized)


def test_decode_line_accepts_frame_at_limit():
    from runtime.transport.protocol import MAX_FRAME_SIZE, decode_line
    at_limit = b" " * (MAX_FRAME_SIZE - 2) + b"{}"
    decoded = decode_line(at_limit)
    assert decoded.payload == {}
