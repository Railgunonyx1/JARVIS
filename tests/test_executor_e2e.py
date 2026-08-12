"""End-to-end test: the real agent execution path, offline.

Drives AgentLoop._handle_call → PermissionEngine.check → AgentToolExecutor
→ tools/shell.py shell_execute → SecureExecutor with the real default
registry. Proves the P0 exit criterion end to end: a legitimate command
executes and yields output; a malicious/chained command is rejected with no
secondary execution. No LLM and no network.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PYEXE = sys.executable


def build_context():
    from core.agent.loop import AgentLoop
    from core.agent.state import AgentState
    from tools import build_default_registry

    registry = build_default_registry()
    state = AgentState(task_id="e2e-trace", goal="e2e")
    loop = AgentLoop(router=None, registry=registry)
    loop.observer.start("e2e-trace", "e2e")
    return loop, state


def make_call(name, arguments, call_id="e2e-1"):
    from providers.types import ToolCall
    return ToolCall(name=name, arguments=arguments, id=call_id)


def run_handle(loop, state, call):
    messages = [{"role": "user", "content": "run it"}]
    asyncio.run(loop._handle_call(
        messages, call, state,
        trace_id="e2e-trace", session_id="e2e-session",
    ))
    return messages


def test_e2e_legitimate_command_executes():
    loop, state = build_context()
    call = make_call("shell.execute", {"executable": PYEXE, "args": ["-c", "print('e2e-ok')"]})
    messages = run_handle(loop, state, call)
    tool_msg = messages[-1]
    assert tool_msg["role"] == "tool"
    assert "e2e-ok" in tool_msg["content"]


def test_e2e_malicious_command_blocked():
    loop, state = build_context()
    call = make_call("shell.execute", {"command": "echo hi & whoami"})
    messages = run_handle(loop, state, call)
    tool_msg = messages[-1]
    assert tool_msg["role"] == "tool"
    assert "blocked" in tool_msg["content"].lower() or "ERROR" in tool_msg["content"]
    assert "whoami" not in tool_msg["content"]


def test_e2e_structured_shell_true_never_used():
    """Prove the agent path never invokes a shell parser (shell=False)."""
    import security.executor as exmod

    captured = {}

    class RecordingPopen:
        def __init__(self, argv, shell, **kwargs):
            captured["argv"] = argv
            captured["shell"] = shell
            self.pid = 7777
            self.returncode = 0
            self.stdout = None
            self.stderr = None

        def wait(self, timeout=None):
            return 0

    original = exmod.subprocess.Popen
    exmod.subprocess.Popen = RecordingPopen
    exmod._is_windows = lambda: True
    try:
        loop, state = build_context()
        call = make_call("shell.execute", {"executable": PYEXE, "args": ["-c", "print(1)"]})
        run_handle(loop, state, call)
    finally:
        exmod.subprocess.Popen = original

    assert captured["shell"] is False
    assert captured["argv"][0] == PYEXE
