"""JARVIS MK-X Event / State Bus.

The *sole* anti-corruption layer between the agent engine and the terminal.

Backend owns state and decisions; the renderer only displays snapshots. This
module translates engine reality into the CLI view-models (``cli.models``):

* observer events  → ``AgentEvent`` (activity stream) + ``Plan`` steps
* ``AgentResult``  → conversation messages, tokens, provider/model
* failures         → failed events + a status message (prompt stays usable)

Nothing in ``cli/main.py`` or the renderer is allowed to reach into the engine
past this boundary.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from core import events

from .models import (
    AgentEvent,
    AppState,
    AuditSection,
    ConfirmationRequest,
    EventStatus,
    EventType,
    MemoryHit,
    Message,
    Mode,
    Plan,
    PlanStep,
    RiskLevel,
    StepStatus,
)

logger = logging.getLogger("jarvis.cli.bridge")

# Map engine step statuses onto view-model statuses.
_STEP_TO_EVENT_STATUS = {
    "ok": EventStatus.COMPLETED,
    "error": EventStatus.FAILED,
    "denied": EventStatus.FAILED,
    "running": EventStatus.RUNNING,
}


class AgentBridge:
    """Translates engine output into ``AppState`` snapshots for the renderer.

    Attach to an ``AgentLoop`` via :meth:`attach_loop` — the observer callback
    is owned here, so the renderer and the REPL never see raw engine events.
    """

    def __init__(self, renderer=None) -> None:
        self.renderer = renderer
        self.state: AppState = getattr(renderer, "state", None) or AppState()
        self.loop: Any | None = None
        self._run_started: float = 0.0
        self._active_event: AgentEvent | None = None
        self._event_by_step: dict[int, AgentEvent] = {}
        self.confirmation_handler = None

    # ── attachment ──────────────────────────────────────────────────────────

    def attach_loop(self, loop) -> None:
        """Own the loop's observer callback. Only one consumer per run."""
        self.loop = loop
        loop.observer.on_event = self.on_event

    # ── public state pulls (status bar / workspace data) ────────────────────

    def pull_status(self) -> None:
        """Refresh provider/model/mode/memory flags from the loop."""
        loop = self.loop
        if loop is None:
            return
        self.state.mode = Mode(str(loop.permissions.mode).upper())
        model = getattr(loop.router, "_last_model", None)
        provider = getattr(loop.router, "_last_provider", None)
        if model:
            self.state.model = model if provider is None else f"{provider}/{model}"
        self.state.memory_enabled = loop.mem is not None
        self.state.connection = "ONLINE"

    def pull_tokens(self, result) -> None:
        """Copy token accounting from a finished AgentResult."""
        usage = (result.observation or {}).get("context_usage") or {}
        if usage:
            self.state.tokens_used = usage.get("total_tokens", self.state.tokens_used)
            self.state.tokens_limit = usage.get("total_budget", self.state.tokens_limit)

    # ── run lifecycle ───────────────────────────────────────────────────────

    def start_run(self, goal: str) -> None:
        """Begin one goal: log the user turn and reset the plan."""
        self._run_started = time.time()
        self._event_by_step = {}
        self._active_event = None
        self.state.messages.append(Message(role="user", content=goal))
        self.state.plan = Plan.new(goal, [])

    def finish_run(self, result) -> None:
        """Close out a successful run: agent message + final accounting."""
        if result.response:
            self.state.messages.append(Message(role="agent", content=result.response))
        self.pull_tokens(result)
        self._complete_active_events()
        self.state.status_message = ""

    def fail_run(self, message: str) -> None:
        """Recover from an engine failure: mark the active event failed and
        surface a status message. The prompt stays usable."""
        logger.warning("engine run failed: %s", message)
        if self._active_event is not None:
            self._active_event.fail(result=message, duration_s=time.time() - self._run_started)
            self._update_renderer_event()
            self._active_event = None
        self.state.status_message = message
        self._push_status()

    # ── observer event translation ──────────────────────────────────────────

    def on_event(self, name: str, payload: dict[str, Any]) -> None:
        """Engine observer callback — the only event entry point."""
        try:
            self._translate(name, payload)
        except Exception as exc:  # a broken subscriber must never take down a run
            logger.error("bridge translation failed for %s: %s", name, exc)

    def _translate(self, name: str, payload: dict[str, Any]) -> None:
        if name == events.TASK_STARTED:
            self._on_task_started(payload)
        elif name == events.STEP_STARTED:
            self._on_step_started(payload)
        elif name == events.STEP_COMPLETED:
            self._on_step_completed(payload)
        elif name == events.PERMISSION_OBSERVED:
            self._on_permission_observed(payload)
        elif name == events.STEP_FAILED:
            self._on_step_failed(payload)
        elif name == events.TASK_FINISHED:
            self._on_task_finished(payload)
        elif name == events.TASK_CANCELLED:
            self._on_task_cancelled(payload)

    def _on_task_started(self, payload: dict[str, Any]) -> None:
        self._active_event = None
        self.state.status_message = ""

    def _on_step_started(self, payload: dict[str, Any]) -> None:
        step_idx = int(payload.get("step", -1))
        tool = payload.get("tool", "tool")
        self._complete_active_events()

        ev = AgentEvent.tool_start(tool, parent_run_id=payload.get("task_id", ""))
        self.state.events.append(ev)
        self._active_event = ev
        if step_idx >= 0:
            self._event_by_step[step_idx] = ev

        # Track the plan: each tool step becomes a plan step the agent is on.
        plan = self.state.plan
        if plan is not None and not plan.steps:
            step = PlanStep.new(tool, StepStatus.ACTIVE)
            step.started_at = time.time()
            plan.steps.append(step)
            plan.related = getattr(plan, "related", None)
        elif plan is not None:
            for s in plan.steps:
                if s.status == StepStatus.ACTIVE:
                    s.status = StepStatus.COMPLETED
                    s.completed_at = time.time()
            plan.steps.append(PlanStep.new(tool, StepStatus.ACTIVE))

        self._push_status()

    def _on_step_completed(self, payload: dict[str, Any]) -> None:
        step_idx = int(payload.get("step", -1))
        status = _STEP_TO_EVENT_STATUS.get(payload.get("status", ""), EventStatus.COMPLETED)
        duration_ms = payload.get("duration_ms") or 0.0
        ev = self._event_by_step.get(step_idx) or self._active_event
        if ev is None:
            return
        if status == EventStatus.FAILED:
            ev.fail(result=payload.get("error", ""), duration_s=duration_ms / 1000.0)
        else:
            ev.complete(result=self._tool_result(payload.get("tool", ev.tool or "")),
                        duration_s=duration_ms / 1000.0)
        if self._active_event is ev:
            self._active_event = None
        self._update_renderer_event()
        self._complete_plan_step(StepStatus.COMPLETED)

    def _on_permission_observed(self, payload: dict[str, Any]) -> None:
        tool = payload.get("tool", "")
        allowed = bool(payload.get("allowed", True))
        reason = payload.get("reason", "")
        ev = AgentEvent(
            event_id=f"sec-{int(time.time() * 1000) % 1000000}",
            timestamp=time.time(),
            type=EventType.SECURITY,
            status=EventStatus.COMPLETED if allowed else EventStatus.FAILED,
            tool=tool,
            result=f"{'allowed' if allowed else 'denied'} — {reason}",
        )
        self.state.events.append(ev)
        if not allowed:
            self.state.status_message = f"blocked: {tool} denied"
        self._push_status()

    def _on_step_failed(self, payload: dict[str, Any]) -> None:
        self.fail_run(payload.get("error", "step failed"))

    def _on_task_finished(self, payload: dict[str, Any]) -> None:
        self._complete_active_events()
        for s in self.state.plan.steps if self.state.plan else []:
            if s.status == StepStatus.ACTIVE:
                s.status = StepStatus.COMPLETED
                s.completed_at = time.time()

    def _on_task_cancelled(self, payload: dict[str, Any]) -> None:
        self._complete_active_events()
        self.state.status_message = "task cancelled"

    # ── internal helpers ────────────────────────────────────────────────────

    def _tool_result(self, tool: str) -> str:
        """Best-effort: pull a tool output string from the last result."""
        loop = self.loop
        result = getattr(loop, "_last_result", None)
        if result is None:
            return ""
        for call in (result.state.tool_calls if getattr(result.state, "tool_calls", None) else []):
            if call.get("name") == tool:
                out = call.get("output", "")
                return out[:400]
        return ""

    def _complete_active_events(self) -> None:
        if self._active_event is not None:
            self._active_event.complete(result="", duration_s=0.0)
            self._update_renderer_event()
            self._active_event = None

    def _complete_plan_step(self, status: StepStatus) -> None:
        plan = self.state.plan
        if plan is None or not plan.steps:
            return
        s = plan.steps[-1]
        if s.status == StepStatus.ACTIVE:
            s.status = status
            s.completed_at = time.time()

    def _update_renderer_event(self) -> None:
        if self.renderer is not None:
            self.renderer.update_event(self._active_event) if self._active_event is not None else None

    def _push_status(self) -> None:
        if self.renderer is not None:
            self.renderer.state.status_message = self.state.status_message

    # ── confirmation (Phase 5; security-owned) ──────────────────────────────

    _RISK_BY_TOOL = {
        "shell.execute": RiskLevel.CRITICAL,
        "shell.run": RiskLevel.CRITICAL,
        "package.remove": RiskLevel.HIGH,
        "package.install": RiskLevel.HIGH,
        "filesystem.delete": RiskLevel.HIGH,
        "filesystem.write": RiskLevel.HIGH,
        "process.kill": RiskLevel.HIGH,
        "system.shutdown": RiskLevel.CRITICAL,
        "system.restart": RiskLevel.CRITICAL,
    }

    def confirmation_call(self, tool_name: str, params: dict | None) -> str:
        """Engine-compatible confirmation handler.

        ``(tool_name, params) -> "once" | "run" | "deny"``. Never decides —
        routes to the operator through the renderer. Denies when no UI path
        is wired (fail-closed).
        """
        params = params or {}
        details = ""
        if params:
            details = ", ".join(f"{k}={str(v)[:40]}" for k, v in params.items())[:200]
        return self.request_confirmation(
            operation=tool_name,
            scope="tool invocation",
            risk=self._RISK_BY_TOOL.get(tool_name, RiskLevel.MEDIUM),
            reversible=True,
            details=details,
        )

    def request_confirmation(self, operation: str, scope: str = "",
                             risk: RiskLevel = RiskLevel.MEDIUM,
                             reversible: bool = True,
                             details: str = "") -> str:
        """Ask the operator for a decision. Returns 'once' | 'run' | 'deny'.

        The decision is returned to the security/policy layer; the bridge never
        decides. Falls back to 'deny' when no handler is wired.
        """
        req = ConfirmationRequest(
            operation=operation,
            risk=risk,
            scope=scope,
            reversible=reversible,
            details=details,
        )
        if self.confirmation_handler is not None:
            return self.confirmation_handler(req)
        if self.renderer is not None:
            return self.renderer.confirm_interactive(req)
        return "deny"
