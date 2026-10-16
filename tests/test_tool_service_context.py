"""ToolExecutionService session context scoping (audit follow-up).

The session contextvar must be scoped to one ``execute_tool`` call: set from
an explicit ``session_id``, visible to nested internal calls made while the
tool runs, and restored on exit -- success, denial, or exception -- so a
reused asyncio task cannot leak one session's identity into later calls.

These tests run each scenario inside a single event loop/task (the reused-task
case is exactly what the old un-scoped ``set()`` got wrong).
"""

from __future__ import annotations

import asyncio

import pytest

from core.agent.tool_service import _CURRENT_SESSION, ToolExecutionService
from providers.types import ToolCall
from tools.schema import Tool, ToolResult


class _StubLogger:
    def record_tool(self, *args, **kwargs):
        pass

    def flush(self):
        pass


class _StubPermissions:
    mode = "agent"

    async def check(self, tool, arguments, trace_id, session_id=""):
        return True, ""


class _StubExecutor:
    """Records the session_id every execution sees; can run a nested call."""

    def __init__(self) -> None:
        self.seen: list[str] = []
        self._active_cancellations: dict = {}
        self.service: ToolExecutionService | None = None
        self.nested: ToolCall | None = None
        self.raise_exc: Exception | None = None

    async def execute(self, name, arguments, trace_id="", mode="agent",
                      session_id="", tool_call_id="", timeout_budget=None):
        self.seen.append(session_id)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.nested is not None:
            call, self.nested = self.nested, None
            assert self.service is not None
            await self.service.execute_tool(call)
        return ToolResult(success=True, output="ok", metadata={"duration_ms": 1.0})

    def abandoned_count(self) -> int:
        return 0


class _StubRegistry:
    def __init__(self, tool: Tool) -> None:
        self._tool = tool

    def get(self, name):
        return self._tool if name == self._tool.name else None


def _build(session_id: str = "") -> tuple[ToolExecutionService, _StubExecutor]:
    tool = Tool(
        name="test.tool",
        description="stub",
        parameters={},
        permission="read",
        handler=lambda **_: ToolResult(success=True, output="ok"),
    )
    executor = _StubExecutor()
    service = ToolExecutionService(
        registry=_StubRegistry(tool),
        permissions=_StubPermissions(),
        executor=executor,
        decision_logger=_StubLogger(),
        session_id=session_id,
    )
    executor.service = service
    return service, executor


def _call() -> ToolCall:
    return ToolCall(name="test.tool", arguments={}, id="c1")


def test_explicit_session_is_reset_after_call():
    service, executor = _build()

    async def scenario():
        await service.execute_tool(_call(), session_id="sess-A")
        return _CURRENT_SESSION.get()

    assert asyncio.run(scenario()) == ""
    assert executor.seen == ["sess-A"]


def test_prior_value_restored_after_explicit_session_call():
    service, _ = _build()

    async def scenario():
        token = _CURRENT_SESSION.set("outer")
        try:
            await service.execute_tool(_call(), session_id="sess-A")
            return _CURRENT_SESSION.get()
        finally:
            _CURRENT_SESSION.reset(token)

    assert asyncio.run(scenario()) == "outer"


def test_no_session_uses_service_default():
    service, executor = _build(session_id="svc-default")

    async def scenario():
        await service.execute_tool(_call())
        return _CURRENT_SESSION.get()

    assert asyncio.run(scenario()) == ""
    assert executor.seen == ["svc-default"]


def test_nested_call_inherits_session_during_execution():
    service, executor = _build()
    executor.nested = _call()

    async def scenario():
        await service.execute_tool(_call(), session_id="sess-A")
        return _CURRENT_SESSION.get()

    assert asyncio.run(scenario()) == ""
    assert executor.seen == ["sess-A", "sess-A"]


def test_context_reset_even_when_execution_raises():
    service, executor = _build()
    executor.raise_exc = RuntimeError("boom")

    async def scenario():
        with pytest.raises(RuntimeError):
            await service.execute_tool(_call(), session_id="sess-A")
        return _CURRENT_SESSION.get()

    assert asyncio.run(scenario()) == ""


def test_reused_task_does_not_leak_session():
    service, executor = _build()

    async def scenario():
        await service.execute_tool(_call(), session_id="sess-A")
        await service.execute_tool(_call())
        return _CURRENT_SESSION.get()

    assert asyncio.run(scenario()) == ""
    assert executor.seen == ["sess-A", ""]
