"""Timeout envelope (jacobian-style phase leases) + timeout attribution.

The wall deadline is split before execution: delivery + teardown leases are
reserved and only the remainder is granted to the executor as its backend
budget. A TimeoutError raised from inside the executor is attributed as
BACKEND_TIMEOUT; the outer wall firing is OPERATION_WALL. The service also
signals the cooperative-cancellation event keyed by the tool call id.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from core.agent.state import FailureClass
from core.agent.tool_service import (
    _TIMEOUT_OWNER_BACKEND,
    _TIMEOUT_OWNER_WALL,
    ToolExecutionService,
)
from providers.types import ToolCall
from tools.schema import Tool, ToolResult


class _StubLogger:
    def record(self, *args, **kwargs):
        pass

    def record_tool(self, *args, **kwargs):
        pass

    def flush(self):
        pass


class _StubPermissions:
    mode = "agent"

    async def check(self, tool, arguments, trace_id, session_id=""):
        return True, ""


class _BehaviorExecutor:
    """Captures the granted budget and can simulate backend/wall timeouts."""

    def __init__(self, behavior: str = "ok") -> None:
        self.behavior = behavior
        self.last_budget: float | None = None
        self._active_cancellations: dict = {}
        self._abandoned = 0

    async def execute(self, name, arguments, trace_id="", mode="agent",
                      session_id="", tool_call_id="", timeout_budget=None):
        self.last_budget = timeout_budget
        if self.behavior == "backend_timeout":
            self._abandoned += 1
            raise TimeoutError("inner timeout")
        if self.behavior == "wall":
            await asyncio.sleep(5)
        return ToolResult(success=True, output="ok", metadata={"duration_ms": 1.0})

    def abandoned_count(self) -> int:
        return self._abandoned


class _StubRegistry:
    def __init__(self, tool: Tool) -> None:
        self._tool = tool

    def get(self, name):
        return self._tool if name == self._tool.name else None


def _tool(timeout_seconds: float = 1.0, max_output_chars: int = 8000) -> Tool:
    return Tool(
        name="test.tool", description="stub", parameters={},
        permission="read", handler=lambda **_: ToolResult(success=True, output="ok"),
        timeout_seconds=timeout_seconds, max_output_chars=max_output_chars,
    )


def _build(behavior: str = "ok", tool: Tool | None = None):
    tool = tool or _tool()
    executor = _BehaviorExecutor(behavior)
    service = ToolExecutionService(
        registry=_StubRegistry(tool),
        permissions=_StubPermissions(),
        executor=executor,
        decision_logger=_StubLogger(),
    )
    return service, executor


def _call() -> ToolCall:
    return ToolCall(name="test.tool", arguments={}, id="c1")


def test_executor_receives_budget_strictly_below_wall():
    service, executor = _build()

    async def scenario():
        return await service.execute_tool(_call())

    result = asyncio.run(scenario())
    assert result.success is True
    assert executor.last_budget is not None
    assert 0.0 < executor.last_budget < 1.0


def test_envelope_math_reserves_delivery_and_teardown():
    wall, budget, reserves = ToolExecutionService._timeout_envelope(_tool())
    assert wall == 1.0
    assert budget < wall
    assert budget == pytest.approx(wall - reserves["delivery_reserve_s"]
                                   - reserves["teardown_reserve_s"], abs=1e-3)
    assert reserves["delivery_reserve_s"] > 0
    assert reserves["teardown_reserve_s"] > 0


def test_larger_output_bound_shrinks_budget():
    _, small_budget, small_reserves = ToolExecutionService._timeout_envelope(
        _tool(timeout_seconds=60.0, max_output_chars=8_000),
    )
    _, big_budget, big_reserves = ToolExecutionService._timeout_envelope(
        _tool(timeout_seconds=60.0, max_output_chars=10_000_000),
    )
    assert big_budget < small_budget
    assert big_reserves["delivery_reserve_s"] > small_reserves["delivery_reserve_s"]


def test_wall_floor_is_one_second():
    wall, _, _ = ToolExecutionService._timeout_envelope(_tool(timeout_seconds=0.2))
    assert wall == 1.0


def test_backend_timeout_attribution():
    service, executor = _build(behavior="backend_timeout")

    async def scenario():
        return await service.execute_tool(_call())

    result = asyncio.run(scenario())
    assert result.success is False
    assert result.failure_class == FailureClass.TIMEOUT
    assert result.metadata["timeout_owner"] == _TIMEOUT_OWNER_BACKEND
    assert "timed out after 1s" in result.error
    assert result.metadata["timeout_wall_s"] == 1.0
    assert 0.0 < result.metadata["timeout_budget_s"] < 1.0
    assert result.metadata["delivery_reserve_s"] > 0
    assert result.metadata["teardown_reserve_s"] > 0


def test_operation_wall_attribution():
    service, _ = _build(behavior="wall")

    async def scenario():
        return await service.execute_tool(_call())

    result = asyncio.run(scenario())
    assert result.success is False
    assert result.failure_class == FailureClass.TIMEOUT
    assert result.metadata["timeout_owner"] == _TIMEOUT_OWNER_WALL


def test_service_sets_cancel_event_keyed_by_call_id():
    service, executor = _build(behavior="backend_timeout")
    event = threading.Event()
    executor._active_cancellations["c1"] = event

    async def scenario():
        return await service.execute_tool(_call())

    result = asyncio.run(scenario())
    assert result.success is False
    assert event.is_set() is True


def test_budget_kwarg_used_for_inner_timeout_margin():
    from core.agent.tools import AgentToolExecutor
    from tools.registry import ToolRegistry

    started = threading.Event()
    release = threading.Event()

    def blocking_handler(_):
        started.set()
        release.wait(5.0)
        return {"success": True, "output": "done"}

    reg = ToolRegistry()
    reg.register(Tool(
        name="test.blocking", description="b", parameters={},
        permission="filesystem.read", handler=blocking_handler,
        category="testing", timeout_seconds=60.0,
    ))
    executor = AgentToolExecutor(reg, _StubLogger())
    service = ToolExecutionService(
        registry=reg, permissions=_StubPermissions(), executor=executor,
        decision_logger=_StubLogger(),
    )
    call = ToolCall(name="test.blocking", arguments={}, id="blk-1")

    async def scenario():
        task = asyncio.create_task(service.execute_tool(call))
        await asyncio.to_thread(started.wait, 3.0)
        # Backend budget (60 - leases) − 5s thread margin ≈ 54.9s: the inner
        # wait_for must still be pending and the live event registered.
        cancel = AgentToolExecutor.current_cancellation("blk-1")
        assert cancel is not None
        assert not task.done()
        release.set()
        return await task

    result = asyncio.run(scenario())
    assert result.success is True
    assert AgentToolExecutor.current_cancellation("blk-1") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
