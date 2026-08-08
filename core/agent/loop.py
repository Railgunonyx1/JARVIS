"""AgentLoop — the tool-calling agent runtime for JARVIS MK-X.

Owns the observe → decide → act cycle: sends the message history with the
tool catalog to the router, executes requested tool calls through the
permission engine + executor, and closes the task with a final answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core import events
from core.agent.context import AgentContextBuilder
from core.agent.observer import TaskObserver, TaskStatus
from core.agent.permissions import PermissionEngine
from core.agent.state import AgentState
from core.agent.tools import AgentToolExecutor, generate_tool_call_id
from core.context.budget import estimate_tokens
from core.context.manager import ContextManager
from core.decision_logger import DecisionLogger, get_decision_logger
from core.project import ProjectContext
from providers.router import ProviderRouter
from runtime.observability.tracer import get_tracer
from tools.registry import ToolRegistry


@dataclass
class AgentResult:
    """Outcome of a single agent run."""

    success: bool
    response: str
    trace_id: str
    state: AgentState
    error: str = ""
    observation: Dict[str, Any] = field(default_factory=dict)
    perf: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "response": self.response,
            "trace_id": self.trace_id,
            "error": self.error,
            "state": self.state.to_dict(),
            "observation": self.observation,
            "perf": self.perf,
        }


class AgentLoop:
    """Executes a goal end-to-end using the tool-calling provider chain."""

    def __init__(
        self,
        router: ProviderRouter,
        registry: ToolRegistry,
        project: Optional[ProjectContext] = None,
        decision_logger: Optional[DecisionLogger] = None,
        mode: str = "agent",
        max_iterations: int = 10,
        max_tokens: Optional[int] = None,
        temperature: float = 0.4,
        confirmation_handler: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        observer: Optional[TaskObserver] = None,
        context_manager: Optional[ContextManager] = None,
        mem=None,
    ) -> None:
        self.router = router
        self.registry = registry
        self.project = project or ProjectContext.discover()
        self.logger = decision_logger or get_decision_logger()
        self.context_builder = AgentContextBuilder(registry)
        self.permissions = PermissionEngine(self.logger, mode=mode, confirmation_handler=confirmation_handler)
        self.executor = AgentToolExecutor(registry, self.logger)
        self.observer = observer or TaskObserver()
        self.context_manager = context_manager or ContextManager()
        self.mem = mem
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._tool_counter = 0

    def _next_tool_id(self) -> str:
        self._tool_counter += 1
        return generate_tool_call_id(self._tool_counter)

    async def run(self, goal: str, session_id: str = "") -> AgentResult:
        tracer = get_tracer()
        root = tracer.begin(f"run: {goal[:80]}", {"goal": goal[:200]})
        try:
            trace_id = self.logger.begin_task(goal, source="agent_loop")
            self.logger.record(trace_id, events.AGENT_REASONING_STARTED, {"goal": goal[:200]})
            self.observer.start(trace_id, goal)
            state = AgentState(task_id=trace_id, goal=goal)
            with tracer.span("context.build", {"project": str(self.project.root_path)}):
                messages, system_prompt = self.context_builder.build(goal, self.project, self.mem)
            tools = self.registry.to_openai_tools()

            for iteration in range(1, self.max_iterations + 1):
                state.iteration = iteration
                with tracer.span("context.fit"):
                    messages, report = self.context_manager.fit_for_loop(
                        messages, self._system_tokens(system_prompt, tools),
                    )
                state.context_usage = report.to_dict()
                with tracer.span("provider.complete") as span:
                    response = await self.router.complete(
                        messages,
                        system_prompt,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                        tools=tools,
                    )
                    if span is not None:
                        span.set_attribute("provider", response.provider)
                        span.set_attribute("model", response.model)
                        span.set_attribute("latency_ms", response.latency_ms)
                        span.set_attribute("tokens", response.tokens_used)
                state.add_tokens(response.tokens_prompt, response.tokens_completion)
                state.provider = response.provider
                state.model = response.model

                if not response.has_tool_calls:
                    final = response.text.strip()
                    if not final:
                        error = "provider returned an empty response"
                        if response.finish_reason and response.finish_reason != "stop":
                            error += f" (finish_reason={response.finish_reason})"
                        state.errors.append(error)
                        self.logger.record(trace_id, events.TASK_FAILED, {
                            "goal": goal[:200], "error": error,
                        })
                        self._finish_observation(False, "", state, iteration)
                        return AgentResult(
                            success=False, response="", trace_id=trace_id, state=state,
                            error=error, observation=self._result_observation(state),
                            perf=self._end_perf(tracer, root),
                        )
                    self.logger.record(trace_id, events.TASK_COMPLETED, {
                        "goal": goal[:200],
                        "iterations": iteration,
                        "tokens": state.tokens_used,
                        "provider": response.provider,
                    })
                    self._finish_observation(True, final, state, iteration)
                    return AgentResult(
                        success=True, response=final, trace_id=trace_id, state=state,
                        observation=self._result_observation(state),
                        perf=self._end_perf(tracer, root),
                    )

                for call in response.tool_calls:
                    if not call.id:
                        call.id = self._next_tool_id()

                messages.append({
                    "role": "assistant",
                    "content": response.text or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                        }
                        for call in response.tool_calls
                    ],
                })

                for call in response.tool_calls:
                    with tracer.span("tool.execute", {"tool": call.name}):
                        await self._handle_call(messages, call, state, trace_id, session_id)
        except Exception as e:
            error = str(e)[:500]
            state.errors.append(error)
            self.logger.record(trace_id, events.TASK_FAILED, {"goal": goal[:200], "error": error})
            self._finish_observation(False, "", state, state.iteration)
            return AgentResult(
                success=False, response="", trace_id=trace_id, state=state, error=error,
                observation=self._result_observation(state),
                perf=self._end_perf(tracer, root, "ERROR", error),
            )
        finally:
            if not self.observer.is_finished:
                self.observer.cancel()

        self.logger.record(trace_id, events.TASK_FAILED, {
            "goal": goal[:200], "error": "max iterations reached",
        })
        self._finish_observation(False, "", state, state.iteration)
        return AgentResult(
            success=False,
            response="",
            trace_id=trace_id,
            state=state,
            error=f"Max iterations ({self.max_iterations}) reached without a final answer",
            observation=self._result_observation(state),
            perf=self._end_perf(tracer, root),
        )

    @staticmethod
    def _end_perf(tracer, root, status: str = "OK", error: str = "") -> Dict[str, Any]:
        trace = tracer.end(root, status=status, error=error)
        return trace or {}

    def _finish_observation(self, success: bool, response: str, state: AgentState,
                            iteration: int) -> None:
        self.observer.finish(
            TaskStatus.COMPLETED if success else TaskStatus.FAILED,
            response=response,
            provider=state.provider,
            model=state.model,
            tokens=state.tokens_used,
            iterations=iteration,
            files_changed=state.files_changed,
        )
        self._record_decision(success, response, state)

    def _record_decision(self, success: bool, response: str, state: AgentState) -> None:
        """Persist a decision-memory entry for the finished task (opt-in)."""
        if self.mem is None:
            return
        try:
            outcome = response[:200] if response else ""
            if not outcome and state.errors:
                outcome = state.errors[-1][:200]
            self.mem.record_decision(
                goal=state.goal,
                decision="completed" if success else "failed",
                rationale=f"iterations={state.iteration} tokens={state.tokens_used} provider={state.provider}",
                outcome=outcome,
                project=str(self.project.root_path),
            )
        except Exception:
            pass

    def _result_observation(self, state: AgentState) -> Dict[str, Any]:
        observation = self.observer.summary()
        observation["context_usage"] = state.context_usage
        return observation

    @staticmethod
    def _system_tokens(system_prompt: str, tools: Optional[list]) -> int:
        tokens = estimate_tokens(system_prompt)
        if tools:
            tokens += estimate_tokens(json.dumps(tools))
        return tokens

    async def _handle_call(self, messages: List[Dict[str, Any]], call, state: AgentState,
                           trace_id: str, session_id: str) -> None:
        step = self.observer.step_started(call.name, call.arguments, call.id)
        tool = self.registry.get(call.name)
        if tool is None:
            error = f"Tool '{call.name}' is not registered"
            self.logger.record(trace_id, events.TOOL_FAILED, {"tool": call.name, "error": error})
            self.observer.step_finished(step, "error", 0.0, error)
            messages.append({
                "role": "tool", "tool_call_id": call.id, "name": call.name,
                "content": f"ERROR: {error}",
            })
            return

        self.logger.record(trace_id, events.TOOL_REQUESTED, {"tool": call.name})
        allowed, reason = await self.permissions.check(tool, call.arguments, trace_id, session_id)
        self.observer.observe_permission(call.name, allowed, reason)
        if not allowed:
            self.logger.record(trace_id, events.TOOL_FAILED, {"tool": call.name, "error": reason})
            self.observer.step_finished(step, "denied", 0.0, reason)
            messages.append({
                "role": "tool", "tool_call_id": call.id, "name": call.name,
                "content": f"PERMISSION DENIED: {reason}",
            })
            return

        result = await self.executor.execute(
            call.name, call.arguments, trace_id,
            mode=self.permissions.mode, session_id=session_id,
        )
        self.observer.step_finished(
            step, "ok" if result.success else "error",
            result.metadata.get("duration_ms", 0.0), result.error,
        )
        state.record_tool(
            call.name, call.id, result.success,
            result.metadata.get("duration_ms", 0.0),
            result.output, result.error, result.metadata,
        )
        path = result.metadata.get("path")
        if isinstance(path, str) and result.success:
            state.files_changed.append(path)
        content = result.output if result.success else f"ERROR: {result.error}"
        messages.append({
            "role": "tool", "tool_call_id": call.id, "name": call.name,
            "content": content,
        })
