"""AgentLoop — the tool-calling agent runtime for JARVIS MK-X.

Owns the observe → decide → act cycle: sends the message history with the
tool catalog to the router, executes requested tool calls through the
permission engine + executor, and closes the task with a final answer.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from core import events
from core.agent.context import AgentContextBuilder
from core.agent.intent import Intent, IntentClassifier
from core.agent.latency_router import LatencyAwareRouter
from core.agent.model_residency import ModelResidencyScheduler
from core.agent.observer import TaskObserver
from core.agent.partial_stt import PartialSTTRouter
from core.agent.perf_tracker import PerfTracker
from core.agent.permissions import PermissionEngine
from core.agent.quality_evaluator import QualityEvaluator
from core.agent.speculative import SpeculativeExecutor
from core.agent.state import AgentState, TaskStatus, classify_failure, pick_worst_failure
from core.agent.tool_verifier import ToolResultVerifier
from core.agent.tools import AgentToolExecutor, generate_tool_call_id
from core.context.budget import estimate_tokens
from core.context.manager import ContextManager
from core.decision_logger import DecisionLogger, get_decision_logger
from core.project import ProjectContext
from providers.router import ProviderRouter
from providers.types import LLMResponse, ProviderError, ToolCall
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
    observation: dict[str, Any] = field(default_factory=dict)
    perf: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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

    # Matches <tool.name>{json}</function> (closing tag optional/mismatched,
    # as weak models emit) — full-match only so prose is never misread.
    _TEXT_TOOL_CALL_RE = re.compile(
        r"\s*<\s*([a-zA-Z0-9_.-]+)\s*>\s*(\{.*?\})\s*<\s*/\s*[a-zA-Z0-9_.-]*\s*>\s*",
        re.DOTALL,
    )

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Strip <think>...</think>...</think><think> tags from model output."""
        import re
        return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    @classmethod
    def _parse_text_tool_call(cls, text: str, registry: ToolRegistry):
        """Recover a tool call from plain text when the provider refused
        structured calls. Returns a ToolCall or None."""
        if not text:
            return None
        match = cls._TEXT_TOOL_CALL_RE.fullmatch(text)
        if not match:
            return None
        raw_name, raw_args = match.group(1), match.group(2)
        name = raw_name
        if registry.get(name) is None and "_" in name:
            dotted = name.replace("_", ".")
            if registry.get(dotted) is not None:
                name = dotted
        if registry.get(name) is None:
            return None
        try:
            # LLMs often emit Unicode curly quotes; JSON needs ASCII ones.
            normalized = raw_args.replace("\u201c", '"').replace("\u201d", '"')
            args = json.loads(normalized)
        except Exception:
            return None
        if not isinstance(args, dict):
            return None
        from providers.types import ToolCall
        return ToolCall(name=name, arguments=args, id="")

    def __init__(
        self,
        router: ProviderRouter,
        registry: ToolRegistry,
        project: ProjectContext | None = None,
        decision_logger: DecisionLogger | None = None,
        mode: str = "agent",
        max_iterations: int = 10,
        max_tokens: int | None = None,
        temperature: float = 0.4,
        max_tool_calls_per_step: int = 6,
        confirmation_handler: Callable[[str, dict[str, Any]], str] | None = None,
        observer: TaskObserver | None = None,
        context_manager: ContextManager | None = None,
        mem=None,
        event_bus=None,
        harness=None,
        model_gateway=None,
        tool_service=None,
    ) -> None:

        self.router = router
        self.registry = registry
        self.project = project or ProjectContext.discover()
        self.logger = decision_logger or get_decision_logger()
        self.context_builder = AgentContextBuilder(registry)
        self.intent_classifier = IntentClassifier(registry)
        self._speculative = SpeculativeExecutor(self.intent_classifier)
        self._partial_stt = PartialSTTRouter(self.intent_classifier)
        self._latency_router = LatencyAwareRouter()
        self._residency = ModelResidencyScheduler()
        self._quality_eval = QualityEvaluator()
        self._perf_tracker = PerfTracker()
        self._tool_verifier = ToolResultVerifier()
        self.observer = observer or TaskObserver()
        self.context_manager = context_manager or ContextManager()
        self.mem = mem
        self._bus = event_bus
        self._model_gateway = model_gateway
        self.max_tokens = max_tokens

        # Harness integration: harness overrides scalar config when present
        self._harness = harness
        if harness is not None:
            hc = harness.config
            self.max_iterations = hc.max_iterations
            self.temperature = hc.temperature
            self.max_tool_calls_per_step = hc.max_tool_calls_per_step
            self._verification_enabled = hc.enable_verification
            self._planning_enabled = hc.enable_planning
        else:
            self.max_iterations = max_iterations
            self.temperature = temperature
            self.max_tool_calls_per_step = max_tool_calls_per_step
            self._verification_enabled = True
            self._planning_enabled = True

        self._tool_counter = 0
        self._preferred_model: str | None = None  # request-scoped model override

        # Single tool execution boundary -- permissions and executor live
        # inside ToolExecutionService; nothing outside may access them.
        if tool_service is not None:
            self._tool_service = tool_service
        else:
            from core.agent.tool_service import ToolExecutionService
            _permissions = PermissionEngine(
                self.logger, mode=mode, confirmation_handler=confirmation_handler,
            )
            _executor = AgentToolExecutor(registry, self.logger)
            self._tool_service = ToolExecutionService(
                registry=registry,
                permissions=_permissions,
                executor=_executor,
                observer=self.observer,
                decision_logger=self.logger,
                bus=event_bus,
                mode=mode,
            )

    # ── Mode management (delegates to ToolExecutionService) ────────────────

    @property
    def mode(self) -> str:
        """Current execution mode."""
        return self._tool_service.mode

    def set_mode(self, mode: str) -> bool:
        """Switch execution mode (agent, plan, smart, controlled)."""
        return self._tool_service.set_mode(mode)

    def _next_tool_id(self) -> str:
        self._tool_counter += 1
        return generate_tool_call_id(self._tool_counter)

    def _emit(self, name: str, payload: dict[str, Any] | None = None,
              trace_id: str = "") -> None:
        """Publish a lifecycle event on the bus (if wired).  Never raises."""
        if self._bus is None:
            return
        try:
            from runtime.event_bus import BusEvent
            self._bus.publish(BusEvent(
                name=name,
                payload=payload or {},
                source="agent_loop",
                trace_id=trace_id,
            ))
        except Exception:
            pass

    async def run(
        self,
        goal: str,
        session_id: str = "",
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> AgentResult:
        tracer = get_tracer()
        root = tracer.begin(f"run: {goal[:80]}", {"goal": goal[:200]})
        try:
            trace_id = self.logger.begin_task(goal, source="agent_loop")
            self.logger.record(trace_id, events.AGENT_REASONING_STARTED, {"goal": goal[:200]})
            self.observer.start(trace_id, goal)
            self._emit("task.started", {"goal": goal[:200], "session_id": session_id}, trace_id)
            state = AgentState(task_id=trace_id, goal=goal)

            # Pipeline latency tracker
            _latency_log: list[tuple[str, float]] = []

            # ── Stage 1: Intent classification ──
            _t0 = time.time()
            classified = self.intent_classifier.classify(goal)
            _latency_log.append(("intent", (time.time() - _t0) * 1000))
            self.logger.record(trace_id, "intent.classified", {
                "goal": goal[:200],
                "intent": classified.intent.value,
                "confidence": classified.confidence,
                "tool": classified.tool_name,
                "latency_ms": _latency_log[-1][1],
            })

            # INSTANT: response-only (greetings, questions) — return immediately
            if classified.intent == Intent.INSTANT and classified.response and not classified.tool_name:
                final = classified.response
                self._emit("task.completed", {
                    "goal": goal[:200], "iterations": 0,
                    "tokens": 0, "provider": "direct", "response": final,
                }, trace_id)
                self._finish_observation(True, final, state, 0)
                return AgentResult(
                    success=True, response=final, trace_id=trace_id, state=state,
                    observation=self._result_observation(state),
                    perf=self._end_perf(tracer, root),
                )

            # INSTANT: tool dispatch — execute directly without LLM
            if classified.intent == Intent.INSTANT and classified.tool_name:
                _instant_call = ToolCall(
                    name=classified.tool_name,
                    arguments=classified.tool_args or {},
                    id=self._next_tool_id(),
                )
                tool_result = await self._tool_service.execute_tool(
                    _instant_call,
                    trace_id=trace_id,
                )
                final = tool_result.output if tool_result.success else f"Tool error: {tool_result.error}"
                self._emit("task.completed", {
                    "goal": goal[:200], "iterations": 0,
                    "tokens": 0, "provider": "direct",
                    "tool": classified.tool_name, "response": final[:500],
                }, trace_id)
                self._finish_observation(True, final, state, 0)
                return AgentResult(
                    success=tool_result.success, response=final, trace_id=trace_id, state=state,
                    error="" if tool_result.success else tool_result.error,
                    observation=self._result_observation(state),
                    perf=self._end_perf(tracer, root),
                )

            # SIMPLE / COMPLEX: continue to LLM pipeline
            # SIMPLE uses minimal context; COMPLEX uses full context+memory

            # Model Gateway: select model based on harness requirements
            if self._model_gateway is not None:
                _t_ms = time.time()
                requirements = set()
                if self._harness is not None:
                    for pref in self._harness.config.model_preference:
                        from providers.model_gateway import Capability
                        try:
                            requirements.add(Capability(pref))
                        except ValueError:
                            pass
                profile = self._model_gateway.select(
                    requirements=requirements or None,
                    session_id=session_id or None,
                    confidence=classified.confidence,
                )
                _latency_log.append(("model_select", (time.time() - _t_ms) * 1000))
                if profile is not None:
                    state.provider = profile.provider
                    state.model = profile.name
                    self._emit("model.selected", {
                        "provider": profile.provider,
                        "model": profile.name,
                    }, trace_id)

            state.transition(TaskStatus.CLASSIFYING)
            state.transition(TaskStatus.EXECUTING)

            # Context levels: instant (just the goal), session (minimal), deep (full)
            context_level = classified.context_level
            _t_ctx = time.time()
            with tracer.span("context.build", {
                "project": str(self.project.root_path), "level": context_level,
            }):
                if context_level == "instant":
                    messages = [{"role": "user", "content": goal}]
                    system_prompt = "You are JARVIS, an engineering assistant. Be concise."
                elif context_level == "session":
                    messages = [{"role": "user", "content": goal}]
                    system_prompt = "You are JARVIS, an engineering assistant."
                else:
                    messages, system_prompt = self.context_builder.build(goal, self.project, self.mem)
            _latency_log.append(("context_build", (time.time() - _t_ctx) * 1000))
            tools = self.registry.to_openai_tools()

            # Semantic tool selection: for LLM-bound requests, only expose
            # tools relevant to the user's intent. Reduces prompt tokens,
            # model confusion, and inference time.
            if classified.intent in (Intent.SIMPLE, Intent.COMPLEX):
                tools = self.intent_classifier.select_tools(goal, tools)

            # Adaptive context budgets: scale context window to task complexity
            _context_budget_multiplier = {
                "instant": 0.25,
                "session": 0.5,
                "deep": 1.0,
            }
            _ctx_mult = _context_budget_multiplier.get(context_level, 1.0)

            # Harness: filter tools and append system prompt addendum
            if self._harness is not None:
                tools = self._harness.filter_tools(tools)
                addendum = self._harness.build_system_prompt_addendum()
                if addendum:
                    system_prompt = (system_prompt or "") + addendum

            _run_start = time.time()
            # Latency budgets (seconds) — configurable via harness or defaults
            _budgets = {
                "intent": 0.05,
                "routing": 0.01,
                "context": 0.10,
                "llm_call": 15.0,
                "tool": 0.50,
                "total": 30.0,
            }
            if self._harness is not None:
                hb = getattr(self._harness.config, "latency_budgets", None)
                if hb:
                    _budgets.update(hb)

            for iteration in range(1, self.max_iterations + 1):
                # Hard wall-time timeout — prevents infinite tool-call loops
                elapsed = time.time() - _run_start
                if elapsed > _budgets["total"]:
                    self._emit("task.failed", {
                        "goal": goal[:200],
                        "error": f"timeout after {elapsed:.0f}s",
                    }, trace_id)
                    state.transition(TaskStatus.FAILED)
                    final = self._extract_final(messages)
                    self._finish_observation(False, final or "", state, iteration)
                    return AgentResult(
                        success=False, response=final, trace_id=trace_id,
                        state=state, error=f"timeout after {elapsed:.0f}s",
                        observation=self._result_observation(state),
                        perf=self._end_perf(tracer, root),
                    )
                state.iteration = iteration
                _t_compress = time.time()
                # Adaptive context budget: use request-local copy (never mutate shared state)
                from dataclasses import replace
                _request_budget = replace(self.context_manager.budget, messages=int(self.context_manager.budget.messages * _ctx_mult))
                _orig_budget = self.context_manager.budget
                self.context_manager.budget = _request_budget
                with tracer.span("context.fit"):
                    messages, report = self.context_manager.fit_for_loop(
                        messages, self._system_tokens(system_prompt, tools),
                    )
                self.context_manager.budget = _orig_budget
                _latency_log.append(("context_compress", (time.time() - _t_compress) * 1000))
                state.context_usage = report.to_dict()
                if report.compacted:
                    self._emit("context.compacted", {
                        "messages_tokens": report.messages_tokens,
                        "budget": report.budget.messages,
                    }, trace_id)
                remaining = max(3.0, _budgets["total"] - (time.time() - _run_start))
                _call_timeout = min(_budgets["llm_call"], remaining)
                _t_llm = time.time()
                with tracer.span("provider.complete") as span:
                    try:
                        response = await asyncio.wait_for(
                            self._complete(messages, system_prompt, tools, on_chunk),
                            timeout=_call_timeout,
                        )
                    except TimeoutError:
                        # Provider didn't respond in time — treat as provider failure
                        from providers.types import LLMResponse
                        response = LLMResponse(
                            text='', model='', provider='timeout',
                            latency_ms=_call_timeout * 1000,
                        )
                    if span is not None:
                        span.set_attribute("provider", response.provider)
                        span.set_attribute("model", response.model)
                        span.set_attribute("latency_ms", response.latency_ms)
                        span.set_attribute("tokens", response.tokens_used)
                _latency_log.append(("llm_call", (time.time() - _t_llm) * 1000))
                self._latency_router.record(
                    response.model, response.latency_ms,
                    (time.time() - _t_llm) * 1000, response.has_tool_calls or bool(response.text),
                )
                state.add_tokens(response.tokens_prompt, response.tokens_completion)
                state.provider = response.provider
                state.model = response.model

                self._perf_tracker.record(
                    response.model, response.latency_ms,
                    (time.time() - _t_llm) * 1000,
                    bool(response.text) or response.has_tool_calls,
                )

                if not response.has_tool_calls:
                    fallback_call = self._parse_text_tool_call(response.text, self.registry)
                    if fallback_call is not None:
                        response.tool_calls = [fallback_call]
                    else:
                        final = self._strip_thinking(response.text).strip()
                        if not final:
                            error = "provider returned an empty response"
                            if response.finish_reason and response.finish_reason != "stop":
                                error += f" (finish_reason={response.finish_reason})"
                            state.errors.append(error)
                            self.logger.record(trace_id, events.TASK_FAILED, {
                                "goal": goal[:200], "error": error,
                            })
                            self._emit("task.failed", {"goal": goal[:200], "error": error}, trace_id)
                            state.transition(TaskStatus.FAILED)
                            self._finish_observation(False, "", state, iteration)
                            return AgentResult(
                                success=False, response="", trace_id=trace_id, state=state,
                                error=error, observation=self._result_observation(state),
                                perf=self._end_perf(tracer, root),
                            )

                        # Quality escalation: evaluate cheap-model answers,
                        # re-route to reasoning model if uncertain
                        q_result = self._quality_eval.evaluate(final, goal)
                        if (q_result.should_escalate
                                and not getattr(state, "_quality_escalated", False)
                                and iteration < self.max_iterations):
                            state._quality_escalated = True
                            self._emit("quality.escalate", {
                                "score": q_result.score,
                                "model": response.model,
                                "signals": q_result.signals,
                            }, trace_id)
                            messages.append({
                                "role": "user",
                                "content": (
                                    "Your previous answer was uncertain or incomplete. "
                                    "Please provide a more specific, confident, and "
                                    "complete answer to the original question."
                                ),
                            })
                            continue

                        self.logger.record(trace_id, events.TASK_COMPLETED, {
                            "goal": goal[:200],
                            "iterations": iteration,
                            "tokens": state.tokens_used,
                            "provider": response.provider,
                        })
                        state.transition(TaskStatus.OBSERVING)
                        state.transition(TaskStatus.VERIFYING)

                        # Post-execution verification gate
                        if self._verification_enabled:
                            ver_report = await self._run_verification(trace_id)
                            if not ver_report.all_passed:
                                self._emit("verification.failed", {
                                    "steps_run": ver_report.steps_run,
                                    "steps_passed": ver_report.steps_passed,
                                    "failures": [
                                        {"name": r.step_name, "error": r.error or r.stderr[:200]}
                                        for r in ver_report.results if not r.passed
                                    ],
                                }, trace_id)
                                failure_ctx = self._build_verification_failure_context(ver_report)
                                state.errors.append(failure_ctx)
                                from core.agent.state import TerminalReason
                                if iteration < self.max_iterations:
                                    messages.append({
                                        "role": "user",
                                        "content": (
                                            "Verification failed. The following checks did not pass:\n"
                                            + failure_ctx
                                            + "\nPlease fix the issues and try again."
                                        ),
                                    })
                                    state.transition(TaskStatus.RECOVERING)
                                    state.transition(TaskStatus.EXECUTING)
                                    continue
                                else:
                                    state.terminal_reason = TerminalReason.VERIFICATION_FAIL
                                    self._emit("task.failed", {
                                        "goal": goal[:200],
                                        "error": "verification failed and no retries remaining",
                                    }, trace_id)
                                    state.transition(TaskStatus.FAILED)
                                    self._finish_observation(False, "", state, iteration)
                                    return AgentResult(
                                        success=False, response=final, trace_id=trace_id,
                                        state=state, error="verification failed",
                                        observation=self._result_observation(state),
                                        perf=self._end_perf(tracer, root),
                                    )
                            self._emit("verification.passed", {
                                "steps_run": ver_report.steps_run,
                            }, trace_id)

                        state.transition(TaskStatus.COMPLETED)
                        _total_latency = (time.time() - _run_start) * 1000
                        self._emit("task.completed", {
                            "goal": goal[:200], "iterations": iteration,
                            "tokens": state.tokens_used, "provider": response.provider,
                            "response": final[:500],
                            "latency_profile": dict(_latency_log),
                            "total_latency_ms": _total_latency,
                        }, trace_id)
                        self._finish_observation(True, final, state, iteration)
                        return AgentResult(
                            success=True, response=final, trace_id=trace_id, state=state,
                            observation=self._result_observation(state),
                            perf=self._end_perf(tracer, root),
                        )

                for call in response.tool_calls:
                    if not call.id:
                        call.id = self._next_tool_id()

                if len(response.tool_calls) > self.max_tool_calls_per_step:
                    self.logger.record(trace_id, events.TOOL_FAILED, {
                        "tool": "batch",
                        "error": f"{len(response.tool_calls)} tool calls truncated to {self.max_tool_calls_per_step}",
                    })
                    response.tool_calls = response.tool_calls[:self.max_tool_calls_per_step]

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
                        _t_tool = time.time()
                        await self._handle_call(messages, call, state, trace_id, session_id)
                        _latency_log.append(("tool", (time.time() - _t_tool) * 1000))

                # Safety: if the LLM keeps making tool calls without ever producing
                # a text response, inject a nudge after 5 consecutive tool-only iterations.
                if iteration >= 5 and not any(
                    m.get("role") == "assistant" and m.get("content")
                    for m in messages
                ):
                    messages.append({
                        "role": "user",
                        "content": (
                            "You have been calling tools without producing a text response. "
                            "Please stop calling tools and give your final answer now. "
                            "Summarize what you found or did in 2-3 sentences."
                        ),
                    })

                state.transition(TaskStatus.OBSERVING)
                state.transition(TaskStatus.EXECUTING)
        except Exception as e:
            error = str(e)[:500]
            state.errors.append(error)
            is_provider = isinstance(e, (ProviderError, RuntimeError)) and (
                "provider" in error.lower() or "429" in error or "rate limit" in error.lower()
                or "quota" in error.lower() or "overloaded" in error.lower()
            )
            fc = classify_failure(error, is_provider=is_provider)
            state.failure_class = pick_worst_failure(state.failure_class, fc)
            self.logger.record(trace_id, events.TASK_FAILED, {"goal": goal[:200], "error": error})
            self._emit("task.failed", {"goal": goal[:200], "error": error, "failure_class": fc.value}, trace_id)
            try:
                state.transition(TaskStatus.FAILED)
            except ValueError:
                pass  # already in terminal state
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
        try:
            state.transition(TaskStatus.FAILED)
        except ValueError:
            pass
        self._finish_observation(False, "", state, state.iteration)
        from core.agent.state import TerminalReason
        state.terminal_reason = TerminalReason.MAX_ITERATIONS
        return AgentResult(
            success=False,
            response="",
            trace_id=trace_id,
            state=state,
            error=f"Max iterations ({self.max_iterations}) reached without a final answer",
            observation=self._result_observation(state),
            perf=self._end_perf(tracer, root),
        )

    async def _complete(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list,
        on_chunk: Callable[[str], Awaitable[None]] | None,
    ) -> LLMResponse:
        """Send a completion, streaming the answer back chunk-by-chunk.

        When ``on_chunk`` is set the call goes through
        :meth:`router.complete_stream_typed`: content is forwarded live (so
        callers can render the first tokens of the final answer as they arrive)
        while streamed tool calls are still captured, so multi-step tool loops
        keep working. Without a callback it behaves exactly like the plain
        :meth:`router.complete` call.
        """
        kwargs = dict(
            system_prompt=system_prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            tools=tools,
            preferred_provider=getattr(self.router, "preferred_provider", None),
            preferred_model=self._preferred_model,
        )
        if on_chunk is None:
            return await self.router.complete(messages, **kwargs)

        start = time.perf_counter()
        text_parts: list[str] = []
        tool_calls: list = []
        async for chunk, calls in self.router.complete_stream_typed(messages, **kwargs):
            if chunk:
                text_parts.append(chunk)
                try:
                    await on_chunk(chunk)
                except Exception:
                    pass
            if calls is not None:
                tool_calls = calls
        text = "".join(text_parts)
        tokens_completion = max(1, len(text) // 4)
        return LLMResponse(
            text=text,
            model=self.router._last_model or "",
            provider=self.router._last_provider or "",
            tokens_used=tokens_completion,
            tokens_prompt=estimate_tokens(json.dumps(messages, default=str)) + estimate_tokens(system_prompt or ""),
            tokens_completion=tokens_completion,
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
            finish_reason="stop",
            tool_calls=tool_calls,
        )

    @staticmethod
    def _end_perf(tracer, root, status: str = "OK", error: str = "") -> dict[str, Any]:
        trace = tracer.end(root, status=status, error=error)
        return trace or {}

    async def _run_verification(self, trace_id: str):
        from core.agent.verification import VerificationEngine, VerificationStep
        engine = VerificationEngine(project_root=str(self.project.root_path))
        if self._harness is not None and self._harness.config.verification_steps:
            for name, cmd in self._harness.config.verification_steps:
                engine.add_step(VerificationStep(name=name, command=cmd))
        else:
            engine.configure_defaults()
        self._emit("verification.started", {}, trace_id)
        return await engine.verify()

    @staticmethod
    def _build_verification_failure_context(report) -> str:
        """Build bounded, structured failure context from VerificationReport.

        Uses VerificationResult.summary for concise failure info (enough to
        fix, not enough to overflow the context window). Falls back to raw
        stderr for results without a summary.
        """
        lines = []
        for r in report.results:
            if not r.passed:
                if r.summary:
                    lines.append(f"- {r.summary}")
                else:
                    detail = r.error or r.stderr[:200] if r.stderr else "unknown"
                    lines.append(f"- {r.step_name}: {detail}")
        return "\n".join(lines) if lines else "unknown verification failure"

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

    def _result_observation(self, state: AgentState) -> dict[str, Any]:
        observation = self.observer.summary()
        observation["context_usage"] = state.context_usage
        return observation

    @staticmethod
    def _system_tokens(system_prompt: str, tools: list | None) -> int:
        tokens = estimate_tokens(system_prompt)
        if tools:
            tokens += estimate_tokens(json.dumps(tools))
        return tokens

    async def _handle_call(self, messages: list[dict[str, Any]], call, state: AgentState,
                           trace_id: str, session_id: str) -> None:
        self.logger.record(trace_id, events.TOOL_REQUESTED, {"tool": call.name})
        await self._tool_service.execute_tool(
            call, trace_id=trace_id, session_id=session_id,
            append_to_messages=messages, state=state,
        )
        if self._tool_verifier.should_verify(call.name):
            try:
                vr = await self._tool_verifier.verify(call.name, call.arguments, "")
                if vr and not vr.verified:
                    self._emit("tool.verification_failed", {
                        "tool": call.name, "check": vr.check_name,
                        "message": vr.message,
                    }, trace_id)
            except Exception:
                pass
