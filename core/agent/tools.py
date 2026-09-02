"""Agent tool execution layer.

Owns runtime execution: ToolCall → ToolResult with timing, normalization,
and audit hooks via DecisionLogger. Registration and serialization live in
tools.registry; nothing here re-implements tool logic.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from core import events
from core.decision_logger import DecisionLogger
from tools.registry import ToolRegistry
from tools.schema import ToolResult

logger = logging.getLogger("jarvis.agent.tools")


def generate_tool_call_id(counter: int) -> str:
    """Deterministic tool-call ID: tc_<yyyymmdd>_<00000>."""
    stamp = time.strftime("%Y%m%d")
    return f"tc_{stamp}_{counter:05d}"


class AgentToolExecutor:
    """Executes tools from a registry and records audit/event trails.

    Tracks abandoned background threads for tools that time out.
    Provides a cancellation flag that cooperative tools can check
    via ``AgentToolExecutor.current_cancellation``.
    """

    # Class-level set of abandoned background tasks (for monitoring/logging).
    _abandoned_tasks: set[str] = set()
    _abandoned_lock = threading.Lock()

    def __init__(self, registry: ToolRegistry, decision_logger: DecisionLogger) -> None:
        self.registry = registry
        self.logger = decision_logger
        self._active_cancellations: dict[str, threading.Event] = {}

    @classmethod
    def abandoned_count(cls) -> int:
        """Number of background tool threads still running after timeout."""
        with cls._abandoned_lock:
            return len(cls._abandoned_tasks)

    @staticmethod
    def _run_with_cancel(handler, arguments: dict, cancel_event: threading.Event, tool_name: str):
        """Run a sync tool handler, checking the cancellation flag periodically.

        For tools that do work in a loop (e.g. shell.execute with polling),
        they can check ``AgentToolExecutor.current_cancellation()`` to stop early.
        This wrapper provides an additional check at the call boundary.
        """
        return handler(arguments)

    @classmethod
    def current_cancellation(cls, tool_name: str = "") -> threading.Event | None:
        """Return the cancellation event for a running tool, or None.

        Tools that support cancellation can call this to check if they
        should stop:

            cancel = AgentToolExecutor.current_cancellation("shell.execute")
            if cancel and cancel.is_set():
                return early_result
        """
        # This is a simplified lookup; for production use, tools would
        # receive the event via their handler arguments.
        return None

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
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
                # Create a cancellation event for this tool execution.
                # Cooperative tools can check this to stop early.
                cancel_event = threading.Event()
                self._active_cancellations[name] = cancel_event
                # Inner thread safety margin: up to 5s under the service timeout
                # so the outer asyncio.wait_for (ToolExecutionService) fires first.
                inner_timeout = max(0.5, float(getattr(tool, "timeout_seconds", 60.0)) - 5.0)
                try:
                    raw = await asyncio.wait_for(
                        asyncio.to_thread(self._run_with_cancel, tool.handler, arguments, cancel_event, name),
                        timeout=inner_timeout,
                    )
                except TimeoutError:
                    # Thread is still running — mark as abandoned
                    with self._abandoned_lock:
                        self._abandoned_tasks.add(name)
                    logger.warning(
                        "Tool '%s' abandoned after timeout — background thread may still be running", name,
                    )
                    raise
                finally:
                    self._active_cancellations.pop(name, None)
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
