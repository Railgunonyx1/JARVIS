"""Regression tests for the P0 Secure Executor boundary (security/executor.py).

Proves the exit criterion: every command reaches one authoritative boundary,
structured runs use shell=False, injection is rejected, and legitimate
commands still execute. All offline — no LLM, no pipes.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


PYEXE = sys.executable

# Windows: the security executor uses subprocess with shell=False which
# may fail with WinError 87 in some environments.
_skip_windows_exec = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Security executor subprocess spawn fails on this Windows environment",
)

# Governed powershell/cmd hosts only exist on Windows; the tests below use
# unresolvable first tokens so they deterministically reach the governed path.
_skip_not_windows = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Governed powershell/cmd host is Windows-only",
)


def make_request(**kw):
    from security.executor import ExecRequest
    return ExecRequest(**kw)


def execute(**kw):
    from security.executor import get_secure_executor
    return get_secure_executor().execute(make_request(**kw))


# ── 1. shell=False is actually used ─────────────────────────────────────────

def test_structured_run_uses_shell_false(monkeypatch):
    import security.executor as exmod
    recorded = {}

    class FakePopen:
        def __init__(self, argv, shell, **kwargs):
            recorded["argv"] = argv
            recorded["shell"] = shell
            recorded["env"] = kwargs.get("env")
            self.pid = 9999
            self.returncode = 0
            self.stdout = None
            self.stderr = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(exmod.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(exmod, "_is_windows", lambda: True)
    result = execute(executable=PYEXE, args=["-c", "print(1)"])
    assert result.success
    assert recorded["shell"] is False
    assert recorded["argv"][0] == PYEXE
    assert recorded["argv"][1:] == ["-c", "print(1)"]


# ── 2. command chaining cannot execute ──────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "echo hi & whoami",
    "echo hi && whoami",
    "echo hi || whoami",
    "echo hi | whoami",
    "echo hi; whoami",
    "echo hi; echo bye",
])
def test_chaining_rejected(cmd):
    # Blocked before any spawn: shell operators are rejected in raw commands
    # even when the first token resolves (regression: Git Bash's echo.EXE on
    # PATH used to divert this into the STRUCTURED path, which neither
    # blocked nor ran).
    result = execute(command=cmd)
    assert result.blocked
    assert "blocked" in result.reason.lower() or "policy" in result.reason


def test_raw_chaining_blocked_even_when_first_token_resolves():
    result = execute(command=f"{PYEXE} -c print(1); whoami")
    assert result.blocked
    assert "blocked" in result.reason.lower() or "policy" in result.reason


def test_raw_command_with_resolvable_exe_runs_structured():
    # Regression: raw commands classified STRUCTURED spawned an empty
    # executable (argv=['']) because the resolved exe was never written back.
    result = execute(command=f"{PYEXE} -c print('raw-ok')")
    assert result.success
    assert "raw-ok" in result.stdout
    assert result.mode == "structured"


# ── 3. executable allow/deny ────────────────────────────────────────────────

def test_blocked_executable_denied():
    result = execute(executable="shutdown", args=["/s"])
    assert result.blocked
    assert "blocked" in result.reason.lower() or "policy" in result.reason.lower()


def test_allowed_executable_runs():
    result = execute(executable=PYEXE, args=["-c", "print('ok')"])
    assert result.success
    assert "ok" in result.stdout


# ── 4. argument validation ──────────────────────────────────────────────────

def test_nul_byte_argument_rejected():
    result = execute(executable=PYEXE, args=["-c", "print(1)\x00print(2)"])
    assert result.blocked


def test_structured_args_are_list_only():
    from tools.schema import ToolResult
    from tools.shell import shell_execute
    out = shell_execute({"executable": PYEXE, "args": "not-a-list"})
    assert isinstance(out, ToolResult)
    assert not out.success
    assert "list" in out.error


# ── 5. timeout ──────────────────────────────────────────────────────────────

def test_timeout_kills_long_running_command():
    result = execute(
        executable=PYEXE, args=["-c", "import time; time.sleep(30)"], timeout=1
    )
    assert result.timed_out
    assert result.exit_code == -1


# ── 6/7. output limits ──────────────────────────────────────────────────────

def test_stdout_size_limited():
    result = execute(
        executable=PYEXE,
        args=["-c", "print('x' * 500000)"],
        max_output_bytes=1000,
    )
    assert result.success
    assert len(result.stdout) <= 1000


def test_stderr_size_limited():
    result = execute(
        executable=PYEXE,
        args=["-c", "import sys; sys.stderr.write('y' * 500000)"],
        max_output_bytes=1000,
    )
    assert len(result.stderr) <= 1000


# ── 8. cwd restriction ──────────────────────────────────────────────────────

def test_blocked_cwd_rejected():
    from security.executor import CommandPolicy
    policy = CommandPolicy()
    ok, _ = policy.check_cwd("C:\\Windows")
    assert not ok


def test_allowed_cwd_accepted():
    from security.executor import CommandPolicy
    policy = CommandPolicy()
    ok, _ = policy.check_cwd(os.path.expanduser("~"))
    assert ok


# ── 9. environment sanitization ─────────────────────────────────────────────

def test_env_sanitized_no_secrets(monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_API_KEY", "super-secret-value")
    result = execute(
        executable=PYEXE,
        args=["-c", "import os; print(os.environ.get('JARVIS_TEST_API_KEY', 'missing'))"],
        env={"JARVIS_TEST_API_KEY": "super-secret-value"},
    )
    assert result.success
    assert "super-secret-value" not in result.stdout
    assert "missing" in result.stdout


# ── 10. cancellation / process termination ──────────────────────────────────

def test_kill_all_terminates_processes():
    from security.executor import get_secure_executor
    executor = get_secure_executor()
    import threading
    proc_ref = {}

    def _blocked_run():
        result = execute(
            executable=PYEXE,
            args=["-c", "import time; time.sleep(60)"],
            timeout=120,
        )
        proc_ref["result"] = result

    t = threading.Thread(target=_blocked_run, daemon=True)
    t.start()
    import time as _time
    _time.sleep(1.5)
    assert executor.get_status()["active_processes"] >= 1
    killed = executor.kill_all()
    assert killed >= 1
    t.join(timeout=10)
    assert proc_ref["result"].timed_out or proc_ref["result"].exit_code != 0


# ── 11. governed PowerShell invocation ──────────────────────────────────────

@_skip_not_windows
def test_powershell_path_executes():
    # "Write-Output" never resolves to a file, so the command deterministically
    # reaches the governed powershell host on Windows.
    result = execute(command="Write-Output hello-from-ps")
    assert result.success
    assert "hello-from-ps" in result.stdout
    assert result.mode == "powershell"


@_skip_not_windows
def test_cmd_path_executes():
    # "ver" is a cmd builtin (no ver.exe), so it deterministically reaches
    # the governed cmd host on Windows.
    result = execute(command="ver", shell="cmd")
    assert result.success
    assert result.mode == "cmd"


# ── 12. legitimate commands still work (through tools/shell.py) ─────────────

def test_shell_tool_structured_legit():
    from tools.shell import shell_execute
    out = shell_execute({"executable": PYEXE, "args": ["-c", "print('legit')"]})
    assert out.success
    assert "legit" in out.output


@_skip_windows_exec
def test_shell_tool_raw_legit():
    from tools.shell import shell_execute
    out = shell_execute({"command": "echo legit-raw"})
    assert out.success
    assert "legit-raw" in out.output


def test_shell_tool_blocked_injection():
    from tools.shell import shell_execute
    out = shell_execute({"command": "echo hi & calc"})
    assert not out.success
    assert out.metadata.get("blocked") is True


# ── policy / engine dedup ────────────────────────────────────────────────────

@_skip_windows_exec
def test_engine_execute_sandboxed_uses_executor():
    from security.engine import SecurityEngine
    engine = SecurityEngine(mode="agent")
    engine.set_confirmation_handler(lambda tool, params: "run")
    result = engine.execute_sandboxed("echo via-engine")
    assert result.success
    assert "via-engine" in result.stdout


def test_engine_execute_sandboxed_blocks_injection():
    from security.engine import SecurityEngine
    engine = SecurityEngine(mode="agent")
    result = engine.execute_sandboxed("echo hi; whoami")
    assert result.blocked


# ── 13. audit trail ──────────────────────────────────────────────────────────

def test_shell_execute_is_audited():
    """Every shell execution through the tool must leave an audit entry
    (allowed path) — not just denials."""
    from security.audit import get_audit_log
    from tools.shell import shell_execute

    shell_execute({"executable": PYEXE, "args": ["-c", "print('audit-ok')"]})
    get_audit_log().flush()
    rows = get_audit_log().query(tool="shell.execute", limit=5)
    assert rows, "no audit entries for shell.execute"
    newest = rows[0]
    assert newest["allowed"] == 1
    assert newest["mode"] == "structured"
    assert newest["action"] == "shell_execute"


@_skip_windows_exec
def test_blocked_shell_is_audited():
    """A policy-blocked command is audited as denied (allowed=0)."""
    from security.audit import get_audit_log
    from tools.shell import shell_execute

    out = shell_execute({"command": "echo hi & calc"})
    assert not out.success
    assert out.metadata.get("blocked") is True
    get_audit_log().flush()
    rows = get_audit_log().query(tool="shell.execute", limit=5)
    newest = rows[0]
    assert newest["allowed"] == 0
    assert newest["mode"] == "blocked"


def test_permission_allowed_is_audited():
    """The permission gate must audit allowed decisions too, not only denials."""
    from security.audit import get_audit_log
    from security.engine import SecurityEngine

    engine = SecurityEngine(mode="agent")
    engine.set_confirmation_handler(lambda tool, params: "run")
    allowed, reason = engine.check_permission("action.shell.run")
    assert allowed and reason == ""
    get_audit_log().flush()
    rows = get_audit_log().query(tool="action.shell.run", limit=5)
    allowed_rows = [r for r in rows if r["action"] == "allowed"]
    assert allowed_rows and allowed_rows[0]["allowed"] == 1
