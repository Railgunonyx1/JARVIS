"""Agent tool execution layer.

Owns runtime execution: ToolCall → ToolResult with timing, normalization,
and audit hooks via DecisionLogger. Registration and serialization live in
tools.registry; nothing here re-implements tool logic.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from core import events
from core.decision_logger import DecisionLogger
from tools.registry import ToolRegistry
from tools.schema import Tool, ToolResult


def generate_tool_call_id(counter: int) -> str:
    """Deterministic tool-call ID: tc_<yyyymmdd>_<00000>."""
    stamp = time.strftime("%Y%m%d")
    return f"tc_{stamp}_{counter:05d}"


class AgentToolExecutor:
    """Executes tools from a registry and records audit/event trails."""

    def __init__(self, registry: ToolRegistry, decision_logger: DecisionLogger) -> None:
        self.registry = registry
        self.logger = decision_logger

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        trace_id: str,
        mode: str = "",
        session_id: str = "",
    ) -> ToolResult:
        tool = self.registry.get(name)
        start = time.time()

        if tool is None:
            duration_ms = (time.time() - start) * 1000
            result = ToolResult(
                success=False,
                error=f"Unknown tool: {name}",
                metadata={"tool": name, "duration_ms": round(duration_ms, 1)},
            )
            self.logger.record(trace_id, events.TOOL_FAILED, {
                "tool": name, "error": result.error, "duration_ms": round(duration_ms, 1),
            })
            return result

        try:
            if asyncio.iscoroutinefunction(tool.handler):
                raw = await tool.handler(arguments)
            else:
                raw = await asyncio.to_thread(tool.handler, arguments)
            duration_ms = (time.time() - start) * 1000
            result = self._normalize(raw, tool.name, duration_ms)

            self.logger.record(trace_id, events.TOOL_EXECUTED, {
                "tool": name,
                "success": result.success,
                "duration_ms": round(duration_ms, 1),
            })
            self.logger.record_tool(
                trace_id, tool.permission, arguments,
                allowed=True, success=result.success,
                duration_ms=duration_ms, error=result.error,
                mode=mode, session_id=session_id,
            )
            return result
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            error = str(e)[:500]
            result = ToolResult(
                success=False,
                error=error,
                metadata={"tool": name, "duration_ms": round(duration_ms, 1)},
            )
            self.logger.record(trace_id, events.TOOL_FAILED, {
                "tool": name, "error": error[:300], "duration_ms": round(duration_ms, 1),
            })
            self.logger.record_tool(
                trace_id, tool.permission, arguments,
                allowed=True, success=False,
                duration_ms=duration_ms, error=error,
                mode=mode, session_id=session_id,
            )
            return result

    @staticmethod
    def _normalize(raw: Any, name: str, duration_ms: float) -> ToolResult:
        if isinstance(raw, ToolResult):
            raw.metadata.setdefault("duration_ms", round(duration_ms, 1))
            raw.metadata.setdefault("tool", name)
            return raw
        if isinstance(raw, dict):
            success = raw.get("success", True)
            output = raw.get("output", raw.get("message", ""))
            return ToolResult(
                success=success,
                output=str(output),
                error=raw.get("error", ""),
                metadata={"tool": name, "duration_ms": round(duration_ms, 1)},
            )
        return ToolResult(
            success=True,
            output=str(raw),
            metadata={"tool": name, "duration_ms": round(duration_ms, 1)},
        )
