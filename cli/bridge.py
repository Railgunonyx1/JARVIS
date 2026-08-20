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
from typing import Any

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

_EXT_TO_LANG = {
    ".py": "python", ".pyw": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "javascript", ".tsx": "typescript", ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".json": "json", ".md": "markdown",
    ".yml": "yaml", ".yaml": "yaml", ".sh": "bash", ".bat": "bat",
    ".ps1": "powershell", ".sql": "sql", ".c": "c", ".h": "c", ".cpp": "cpp",
    ".hpp": "cpp", ".java": "java", ".go": "go", ".rs": "rust", ".rb": "ruby",
    ".php": "php", ".lua": "lua", ".ini": "ini",
    ".cfg": "ini", ".xml": "xml", ".toml": "toml", ".txt": "text",
    ".csv": "csv", ".ipynb": "json", ".dockerfile": "dockerfile",
}


def _guess_language(path: str) -> str:
    _, ext = str(path).rsplit(".", 1) if "." in str(path) else ("", "")
    if str(path).lower().endswith("dockerfile"):
        return "dockerfile"
    return _EXT_TO_LANG.get("." + ext.lower(), "text")


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
        self.state.mode = Mode(str(loop.mode).upper())
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

    # ── workspace data (Phase 6: real backends) ─────────────────────────────

    def refresh_audit(self, limit: int = 12) -> list[dict]:
        """Load real audit data into the renderer's audit workspace."""
        from security.audit import get_audit_log

        log = get_audit_log()
        stats = log.get_stats()
        entries = log.query(limit=limit)
        sections = [
            AuditSection(title="SYSTEM", items=[
                ("done", f"Total actions: {stats['total_actions']}", ""),
                ("warning", f"Denied: {stats['denied']}", ""),
                ("failed", f"Failed: {stats['failed']}", ""),
            ]),
        ]
        if stats.get("top_tools"):
            top = ", ".join(f"{k}={v}" for k, v in list(stats["top_tools"].items())[:5])
            sections.append(AuditSection(title="TOP TOOLS", items=[("done", top, "")]))
        if entries:
            items = []
            for e in entries:
                sym = "done" if e["allowed"] else "failed"
                ts = time.strftime("%H:%M:%S", time.localtime(e["timestamp"]))
                flag = "" if e["allowed"] else " DENIED"
                detail = f"{e.get('duration_ms', 0):.0f}ms {e.get('session_id', '')[:8]}"
                items.append((sym, f"{ts} {e['tool'] or e['action']}{flag}", detail))
            sections.append(AuditSection(title="RECENT", items=items))
        self.state.audit_sections = sections
        return entries

    def refresh_memory(self, query: str = "", top_k: int = 5) -> list[dict]:
        """Run a real memory query (or stats when query is empty) into the
        renderer's memory workspace."""
        hits: list[MemoryHit] = []
        loop = self.loop
        if loop is not None and loop.mem is not None:
            if query:
                for hit in loop.mem.retrieve(query, project=str(loop.project.root_path), top_k=top_k):
                    hits.append(MemoryHit(
                        score=hit.get("score", 0.0),
                        title=hit.get("content", "?")[:80] or hit.get("source", "?"),
                        date="",
                        snippet=hit.get("content", "")[:160],
                    ))
        self.state.memory_query = query
        self.state.memory_hits = hits
        return hits

    def list_models(self) -> list[dict]:
        """Router status for the models command (no renderer state change)."""
        loop = self.loop
        if loop is None:
            return []
        return [
            {"name": name, **info}
            for name, info in getattr(loop.router, "status", {}).items()
        ]

    def refresh_code(self, path: str = "", limit: int = 200) -> None:
        """Load the project file tree into the code workspace, and read a
        file into the focused buffer when ``path`` is given."""
        loop = self.loop
        root = loop.project.root_path if loop is not None else None
        if root is None:
            return
        from .models import CodeFile

        skip = {".git", "venv", "node_modules", "__pycache__", "_quarantine",
                ".pytest_cache", "dist", "build", ".venv"}
        files: list[CodeFile] = []
        if path:
            target = (root / path).resolve()
            try:
                rel = str(target.relative_to(root))
            except ValueError:
                target = root
                rel = ""
            if target.is_dir():
                self._fill_tree(target, skip, files, limit, rel_prefix="")
            else:
                self._read_code_file(target, root, rel or path)
                return
        else:
            self._fill_tree(root, skip, files, limit)
        self.state.code_files = files[:limit]

    def _fill_tree(self, directory, skip: set, files, limit: int,
                   rel_prefix: str = "") -> None:
        from .models import CodeFile

        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            if len(files) >= limit:
                return
            if child.name.startswith(".") or child.name in skip:
                continue
            if child.is_dir():
                files.append(CodeFile(path=f"{rel_prefix}{child.name}/", modified=False))
                self._fill_tree(child, skip, files, limit, f"{rel_prefix}{child.name}/")
            else:
                files.append(CodeFile(path=f"{rel_prefix}{child.name}", modified=False))

    def _read_code_file(self, target, root, rel: str) -> None:
        from .models import CodeFile

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            self.state.status_message = f"cannot read {rel}"
            return
        self.state.code_path = rel
        self.state.code_content = content
        self.state.code_language = _guess_language(rel)
        self.state.code_loc = content.count("\n") + 1
        self.state.code_modified = False
        self.state.code_files = [
            CodeFile(path=str(p.relative_to(root)), modified=False)
            for p in root.rglob("*")
            if p.is_file() and not any(part.startswith(".") or part in {
                ".git", "venv", "node_modules", "__pycache__", "_quarantine",
                ".pytest_cache", "dist", "build", ".venv"}
                for part in p.parts)
        ][:200]

    # ── run lifecycle ───────────────────────────────────────────────────────

    def start_run(self, goal: str) -> None:
        """Begin one goal: log the user turn and reset the plan."""
        self._run_started = time.time()
        self._event_by_step = {}
        self._active_event = None
        self.state.messages.append(Message(role="user", content=goal))
        self.state.plan = Plan.new(goal, [])

    def finish_run(self, result) -> None:
        """Close out a successful run: agent message + final accounting.

        If the answer was already streamed into the last agent message
        (``stream_delta``), it is left untouched to avoid duplicating it.
        """
        if result.response:
            last = self.state.messages[-1] if self.state.messages else None
            if last is None or last.role != "agent" or not last.content:
                self.state.messages.append(Message(role="agent", content=result.response))
        self.pull_tokens(result)
        self._complete_active_events()
        self.state.status_message = ""

    def stream_delta(self, delta: str) -> None:
        """Append a streamed token to the in-progress agent message."""
        if self.state.messages and self.state.messages[-1].role == "agent":
            self.state.messages[-1].content += delta
        else:
            self.state.messages.append(Message(role="agent", content=delta))

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
        elif name == "verification.started":
            self._on_verification_started(payload)
        elif name == "verification.step":
            self._on_verification_step(payload)
        elif name == "verification.passed":
            self._on_verification_passed(payload)
        elif name == "verification.failed":
            self._on_verification_failed(payload)
        elif name == "task.recovering":
            self._on_recovery_started(payload)

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
        self.state.recovery_active = False

    def _on_task_cancelled(self, payload: dict[str, Any]) -> None:
        self._complete_active_events()
        self.state.status_message = "task cancelled"

    # ── verification & recovery events ──────────────────────────────────

    def _on_verification_started(self, payload: dict[str, Any]) -> None:
        self.state.verification_steps = []
        self.state.verification_status = "running"

    def _on_verification_step(self, payload: dict[str, Any]) -> None:
        step = {
            "name": payload.get("name", ""),
            "passed": payload.get("passed", False),
            "running": payload.get("running", False),
            "duration_ms": payload.get("duration_ms", 0),
        }
        self.state.verification_steps.append(step)

    def _on_verification_passed(self, payload: dict[str, Any]) -> None:
        self.state.verification_status = "passed"
        self.state.status_message = ""

    def _on_verification_failed(self, payload: dict[str, Any]) -> None:
        self.state.verification_status = "failed"
        failures = payload.get("failures", [])
        detail = "\n".join(
            f"  - {f.get('name', '?')}: {f.get('error', '')[:100]}" for f in failures
        ) or "unknown failure"
        self.state.status_message = f"verification failed: {detail}"

    def _on_recovery_started(self, payload: dict[str, Any]) -> None:
        self.state.recovery_active = True
        self.state.recovery_attempt = payload.get("attempt", 1)
        self.state.recovery_error = payload.get("error", "")[:200]
        self.state.status_message = f"recovering (attempt {self.state.recovery_attempt})"

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
