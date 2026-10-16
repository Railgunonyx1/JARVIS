"""Concurrent-session isolation for ToolExecutionService (audit Phase 1, issue 4).

A shared ToolExecutionService can serve multiple sessions. Session identity must
never be mutable instance state that one session's call can overwrite mid-flight
for another. These tests interleave two sessions and assert every emitted
BusEvent keeps its own session id.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agent.tool_service import ToolExecutionService  # noqa: E402
from providers.types import ToolCall  # noqa: E402
from tools.registry import ToolRegistry  # noqa: E402
from tools.schema import Tool, ToolResult  # noqa: E402


class _Bus:
    def __init__(self) -> None:
        self.events: list = []

    def publish(self, event) -> None:
        self.events.append(event)


def _registry() -> ToolRegistry:
    async def echo(params=None) -> ToolResult:
        return ToolResult(success=True, output="ok")

    reg = ToolRegistry()
    reg.register(Tool(
        name="echo", description="e", parameters={},
        permission="filesystem.read", handler=echo,
    ))
    return reg


async def _flow(svc: ToolExecutionService, sid: str, tag: str) -> None:
    await svc.execute_tool(
        ToolCall(name="echo", arguments={}, id=f"{tag}-outer"),
        trace_id=tag, session_id=sid,
    )
    # Yield so the sibling session can run between this session's calls; with
    # the old shared-instance-state implementation the sibling would clobber
    # the session id before the second call. Session context is scoped to the
    # call (audit fix), so every top-level call passes its session explicitly.
    await asyncio.sleep(0)
    await svc.execute_tool(
        ToolCall(name="echo", arguments={}, id=f"{tag}-inner"),
        trace_id=tag, session_id=sid,
    )


def test_concurrent_sessions_keep_event_identity():
    bus = _Bus()
    svc = ToolExecutionService(registry=_registry(), bus=bus, mode="agent")

    async def main() -> None:
        await asyncio.gather(
            _flow(svc, "session-A", "A"),
            _flow(svc, "session-B", "B"),
        )

    asyncio.run(main())

    a_events = [e for e in bus.events if e.trace_id == "A"]
    b_events = [e for e in bus.events if e.trace_id == "B"]
    assert a_events, "no events emitted for session A"
    assert b_events, "no events emitted for session B"
    assert all(e.session_id == "session-A" for e in a_events)
    assert all(e.session_id == "session-B" for e in b_events)


def test_default_session_id_is_immutable_across_calls():
    svc = ToolExecutionService(registry=_registry(), mode="agent", session_id="boot")
    assert svc._session_id == "boot"

    async def run() -> None:
        await svc.execute_tool(
            ToolCall(name="echo", arguments={}, id="1"),
            trace_id="t", session_id="",
        )

    asyncio.run(run())
    assert svc._session_id == "boot"


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
