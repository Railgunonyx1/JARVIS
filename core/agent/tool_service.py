"""ToolExecutionService -- single tool execution boundary for JARVIS.

All tool execution MUST pass through this service. No protocol, adapter,
or agent path may bypass it.

Architecture:
    Terminal ----|
    MCP ---------|
    ACP ---------|---> ToolExecutionService ---> Permission ---> Executor ---> Result
    Codex -------|
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from core.agent.observer import TaskObserver
from core.agent.permissions import PermissionEngine
from core.agent.state import FailureClass
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
    failure_class: Any | None = None


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
        state: Any | None = None,
    ) -> ToolExecutionResult:
        """Execute a single tool call with full permission + observer lifecycle.

        Returns a ToolExecutionResult.  If append_to_messages is provided,
        the tool response is appended to it (for AgentLoop compatibility).
        """
        start = time.perf_counter()
        has_obs = self._observer.observation is not None
        step = self._observer.step_started(call.name, call.arguments, call.id) if has_obs else None

        # Look up tool
        tool = self._registry.get(call.name)
        if tool is None:
            error = f"Tool '{call.name}' is not registered"
            self._emit("tool.failed", {"tool": call.name, "error": error}, trace_id)
            if step is not None:
                self._observer.step_finished(step, "error", 0.0, error)
            if append_to_messages is not None:
                append_to_messages.append({
                    "role": "tool", "tool_call_id": call.id, "name": call.name,
                    "content": f"ERROR: {error}",
                })
            return ToolExecutionResult(
                tool_name=call.name, call_id=call.id, error=error,
                failure_class=FailureClass.MALFORMED_TOOL,
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        # Permission check
        self._emit("tool.requested", {"tool": call.name}, trace_id)
        allowed, reason = await self._permissions.check(
            tool, call.arguments, trace_id, session_id,
        )
        self._observer.observe_permission(call.name, allowed, reason) if has_obs else None
        if not allowed:
            self._emit("tool.denied", {"tool": call.name, "reason": reason}, trace_id)
            if step is not None:
                self._observer.step_finished(step, "denied", 0.0, reason)
            if append_to_messages is not None:
                append_to_messages.append({
                    "role": "tool", "tool_call_id": call.id, "name": call.name,
                    "content": f"PERMISSION DENIED: {reason}",
                })
            return ToolExecutionResult(
                tool_name=call.name, call_id=call.id,
                permission_denied=True, permission_reason=reason,
                failure_class=FailureClass.PERMISSION_DENIED,
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        # Execute (with a per-tool timeout from declarative metadata)
        _tool_timeout = max(1.0, float(getattr(tool, "timeout_seconds", 60.0)))
        try:
            result = await asyncio.wait_for(
                self._executor.execute(
                    call.name, call.arguments, trace_id,
                    mode=self._mode, session_id=session_id,
                ),
                timeout=_tool_timeout,
            )
        except TimeoutError:
            error = f"Tool '{call.name}' timed out after {_tool_timeout:.0f}s"
            # Signal cancellation to the background thread (cooperative tools check this)
            cancel_event = self._executor._active_cancellations.get(call.name)
            if cancel_event is not None:
                cancel_event.set()
            # Log abandoned task for monitoring
            abandoned = self._executor.abandoned_count()
            logger.warning(
                "Tool '%s' timed out — background thread abandoned (%d total abandoned)",
                call.name, abandoned + 1,
            )
            self._emit("tool.failed", {"tool": call.name, "error": error}, trace_id)
            if step is not None:
                self._observer.step_finished(step, "error", _tool_timeout * 1000, error)
            if append_to_messages is not None:
                append_to_messages.append({
                    "role": "tool", "tool_call_id": call.id, "name": call.name,
                    "content": f"ERROR: {error}",
                })
            return ToolExecutionResult(
                tool_name=call.name, call_id=call.id, error=error,
                failure_class=FailureClass.TIMEOUT,
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        duration_ms = result.metadata.get("duration_ms", 0.0)

        # Observer: step finished
        status = "ok" if result.success else "error"
        if step is not None:
            self._observer.step_finished(step, status, duration_ms, result.error)

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

        # Record tool result in AgentState if provided
        if state is not None:
            state.record_tool(
                call.name, call.id, result.success, duration_ms,
                result.output, result.error, result.metadata,
            )
            path = result.metadata.get("path")
            if isinstance(path, str) and result.success:
                state.files_changed.append(path)

        result_fc = None
        if not result.success:
            result_fc = FailureClass.TIMEOUT if result.metadata.get("timed_out") else FailureClass.TOOL_FAILURE

        return ToolExecutionResult(
            tool_name=call.name,
            call_id=call.id,
            success=result.success,
            output=content,
            error=result.error,
            duration_ms=duration_ms,
            metadata=result.metadata,
            failure_class=result_fc,
        )

    async def execute_tools(
        self,
        calls: list[ToolCall],
        trace_id: str = "",
        session_id: str = "",
        append_to_messages: list[dict[str, Any]] | None = None,
        state: Any | None = None,
        *,
        parallel: bool = True,
    ) -> list[ToolExecutionResult]:
        """Execute multiple tool calls.

        When ``parallel`` is set (default), independent tool calls run
        concurrently (bounded by ``Policy.max_concurrent_actions``) and their
        tool messages are appended to ``append_to_messages`` in the original
        input order so the model sees deterministic results. Pass
        ``parallel=False`` to force strict sequential execution (used when a
        caller must never overlap side effects).
        """
        # Resolve the concurrency cap from the active security policy. This is
        # the enforcement of Policy.max_concurrent_actions, which was previously
        # declared but unused. Falls back to a sane default.
        concurrency = self._max_concurrency()
        if not parallel or concurrency <= 1 or len(calls) <= 1:
            results: list[ToolExecutionResult] = []
            for call in calls:
                result = await self.execute_tool(
                    call, trace_id, session_id, append_to_messages, state,
                )
                results.append(result)
            return results

        sem = asyncio.Semaphore(concurrency)

        async def _run(call: ToolCall) -> ToolExecutionResult:
            async with sem:
                # No append here — appends are re-applied in order below.
                return await self.execute_tool(
                    call, trace_id, session_id, None, state,
                )

        results = await asyncio.gather(*(_run(call) for call in calls))
        if append_to_messages is not None:
            for call, res in zip(calls, results, strict=True):
                # Mirror execute_tool's append semantics (including secret
                # redaction) so parallel results are identical to sequential.
                content = res.output if res.success else f"ERROR: {res.error}"
                content = redact_sensitive(content)
                append_to_messages.append({
                    "role": "tool", "tool_call_id": res.call_id,
                    "name": res.tool_name, "content": content,
                })
        return list(results)

    def _max_concurrency(self) -> int:
        """Concurrency cap for parallel tool execution from the security policy."""
        try:
            from security.engine import get_security_engine
            eng = get_security_engine()
            raw = getattr(eng.policy, "max_concurrent_actions", 5)
            return max(1, int(raw))
        except Exception:
            return 5

    def list_tools(self) -> list[dict]:
        """Return the tool catalog in OpenAI function-calling format."""
        if self._registry is None:
            return []
        return self._registry.to_openai_tools()

    # ── Mode management (exposed so CLI/protocols don't bypass the service) ──

    @property
    def mode(self) -> str:
        """Current execution mode."""
        return str(self._permissions.mode)

    def set_mode(self, mode: str) -> bool:
        """Switch execution mode (agent, plan, smart, controlled)."""
        return self._permissions.set_mode(mode)

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
