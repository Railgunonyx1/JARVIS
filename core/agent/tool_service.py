"""Sprint 20C -- ToolExecutionService: shared tool execution for AgentLoop, MCP, ACP, Codex.

Extracted from AgentLoop._handle_call so all execution paths share the same
tool execution, permission checking, and event emission logic.

Architecture:
    AgentLoop / MCP / ACP / Codex
              │
              ▼
    ToolExecutionService
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
 Permission  Executor  Observer
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from core.agent.observer import TaskObserver
from core.agent.permissions import PermissionEngine
from core.agent.tools import AgentToolExecutor
from core.decision_logger import DecisionLogger
from providers.types import ToolCall
from security.redaction import redact_sensitive

logger = logging.getLogger("jarvis.tool_execution_service")


@dataclass
class ToolExecutionResult:
    """Result of executing a single tool call."""
    tool_name: str = ""
    call_id: str = ""
    success: bool = False
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    permission_denied: bool = False
    permission_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolExecutionService:
    """Shared service for executing tool calls with permission checks.

    Used by:
    - AgentLoop (during agent execution)
    - MCPAdapter (external MCP clients)
    - ACPAdapter (external ACP clients)
    - CodexExecAdapter (Codex-compatible callers)

    All paths go through the same permission engine, executor, and observer.
    """

    def __init__(
        self,
        registry,
        permissions: PermissionEngine | None = None,
        executor: AgentToolExecutor | None = None,
        observer: TaskObserver | None = None,
        decision_logger: DecisionLogger | None = None,
        bus=None,
        mode: str = "agent",
    ):
        self._registry = registry
        from core.decision_logger import get_decision_logger
        _logger = decision_logger or get_decision_logger()
        self._permissions = permissions or PermissionEngine(_logger, mode=mode)
        self._executor = executor or AgentToolExecutor(registry, _logger)
        self._observer = observer or TaskObserver()
        self._logger = _logger
        self._bus = bus
        self._mode = mode

    async def execute_tool(
        self,
        call: ToolCall,
        trace_id: str = "",
        session_id: str = "",
        append_to_messages: list[dict[str, Any]] | None = None,
    ) -> ToolExecutionResult:
        """Execute a single tool call with full permission + observer lifecycle.

        Returns a ToolExecutionResult.  If append_to_messages is provided,
        the tool response is appended to it (for AgentLoop compatibility).
        """
        start = time.perf_counter()

        # Look up tool
        tool = self._registry.get(call.name)
        if tool is None:
            error = f"Tool '{call.name}' is not registered"
            self._emit("tool.failed", {"tool": call.name, "error": error}, trace_id)
            if append_to_messages is not None:
                append_to_messages.append({
                    "role": "tool", "tool_call_id": call.id, "name": call.name,
                    "content": f"ERROR: {error}",
                })
            return ToolExecutionResult(
                tool_name=call.name, call_id=call.id, error=error,
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        # Permission check
        self._emit("tool.requested", {"tool": call.name}, trace_id)
        allowed, reason = await self._permissions.check(
            tool, call.arguments, trace_id, session_id,
        )
        if not allowed:
            self._emit("tool.denied", {"tool": call.name, "reason": reason}, trace_id)
            if append_to_messages is not None:
                append_to_messages.append({
                    "role": "tool", "tool_call_id": call.id, "name": call.name,
                    "content": f"PERMISSION DENIED: {reason}",
                })
            return ToolExecutionResult(
                tool_name=call.name, call_id=call.id,
                permission_denied=True, permission_reason=reason,
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        # Execute
        result = await self._executor.execute(
            call.name, call.arguments, trace_id,
            mode=self._mode, session_id=session_id,
        )
        duration_ms = result.metadata.get("duration_ms", 0.0)

        # Redact secrets
        content = result.output if result.success else f"ERROR: {result.error}"
        content = redact_sensitive(content)

        if append_to_messages is not None:
            append_to_messages.append({
                "role": "tool", "tool_call_id": call.id, "name": call.name,
                "content": content,
            })

        if result.success:
            self._emit("tool.executed", {"tool": call.name, "duration_ms": duration_ms}, trace_id)
        else:
            self._emit("tool.failed", {"tool": call.name, "error": result.error}, trace_id)

        return ToolExecutionResult(
            tool_name=call.name,
            call_id=call.id,
            success=result.success,
            output=content,
            error=result.error,
            duration_ms=duration_ms,
            metadata=result.metadata,
        )

    async def execute_tools(
        self,
        calls: list[ToolCall],
        trace_id: str = "",
        session_id: str = "",
        append_to_messages: list[dict[str, Any]] | None = None,
    ) -> list[ToolExecutionResult]:
        """Execute multiple tool calls sequentially."""
        results = []
        for call in calls:
            result = await self.execute_tool(call, trace_id, session_id, append_to_messages)
            results.append(result)
        return results

    def _emit(self, name: str, payload: dict[str, Any] | None = None,
              trace_id: str = "") -> None:
        if self._bus is None:
            return
        try:
            from runtime.event_bus import BusEvent
            self._bus.publish(BusEvent(
                name=name, payload=payload or {},
                source="tool_execution_service", trace_id=trace_id,
            ))
        except Exception:
            pass
