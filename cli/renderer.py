"""Renderable helpers for the JARVIS MK-X terminal.

Claude Code-style UI: conversation is the screen. No borders, no panels,
no permanent sidebars. Clean, minimal, fast.

``Renderer`` is the pure display layer: backend owns state and decisions,
this class only turns ``AppState`` snapshots into Rich renderables.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from contextlib import nullcontext
from typing import Any

from rich import box
from rich.console import Console, Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from core.output_compressor import compress_output

from .layout import LayoutManager
from .models import (
    AgentEvent,
    AppState,
    AuditSection,
    CodeFile,
    ConfirmationRequest,
    EventStatus,
    EventType,
    MemoryHit,
    Message,
    Mode,
    Plan,
    StepStatus,
)
from .theme import COLORS, BoxStyles, get_symbols

logger = logging.getLogger("jarvis.cli.renderer")

CODE_THEME = "monokai"


def render_markdown(text: str, *, plain: bool = False):
    if plain or not _looks_like_markdown(text):
        return Text(text)
    return Markdown(text, code_theme=CODE_THEME)


def _looks_like_markdown(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    if "\n" not in text:
        return bool(stripped.startswith(("# ", "- ", "* ", "> ", "```")))
    return True


class Renderer:
    """Pure display layer. Claude Code-style: conversation is the UI."""

    def __init__(self, console: Console | None = None, unicode: bool = True) -> None:
        self.console = console or Console(highlight=False, emoji=False)
        self.layout_mgr = LayoutManager(self.console)
        self.symbols = get_symbols(unicode)
        self.state = AppState()
        self._live_display = None

    # ── State mutators ───────────────────────────────────────────────────

    def set_mode(self, mode: Mode | str) -> None:
        if isinstance(mode, str):
            mode = Mode(mode.upper())
        self.state.mode = mode

    def set_model(self, model: str) -> None:
        self.state.model = model

    def set_tokens(self, used: int, limit: int = 32000) -> None:
        self.state.tokens_used = used
        self.state.tokens_limit = limit

    def set_plan(self, plan: Plan | None) -> None:
        self.state.plan = plan

    def add_message(self, role: str, content: str) -> None:
        self.state.messages.append(Message(role=role, content=content))

    def push_event(self, event: AgentEvent) -> None:
        self.state.events.append(event)
        self._recount_tools()

    def update_event(self, event: AgentEvent) -> None:
        self._recount_tools()

    def set_workspace(self, name: str) -> None:
        self.state.workspace = name.lower()

    def set_confirmation(self, req: ConfirmationRequest | None) -> None:
        self.state.pending_confirmation = req

    def set_code(self, files: Sequence[CodeFile], path: str = "",
                 content: str = "", language: str = "python",
                 loc: int = 0, modified: bool = False) -> None:
        self.state.code_files = list(files)
        self.state.code_path = path
        self.state.code_content = content
        self.state.code_language = language
        self.state.code_loc = loc
        self.state.code_modified = modified

    def set_memory(self, query: str, hits: Sequence[MemoryHit]) -> None:
        self.state.memory_query = query
        self.state.memory_hits = list(hits)

    def set_audit(self, sections: Sequence[AuditSection]) -> None:
        self.state.audit_sections = list(sections)

    def set_provider_notice(self, provider: str, message: str, kind: str = "warning", retry_after: float | None = None) -> None:
        self.state.provider_notice = (provider, message, kind, retry_after)

    def clear_provider_notice(self) -> None:
        self.state.provider_notice = None

    def _recount_tools(self) -> None:
        self.state.tools_active = sum(
            1 for e in self.state.events
            if e.type == EventType.TOOL and e.status == EventStatus.RUNNING
        )

    # ── Status bar — compact single line ──────────────────────────────────

    def _token_str(self) -> str:
        used, limit = self.state.tokens_used, self.state.tokens_limit
        u = f"{used / 1000:.1f}K" if used >= 1000 else str(used)
        l = f"{limit // 1000}K" if limit >= 1000 else str(limit)
        return f"{u}/{l}"

    def render_status(self) -> Text:
        """Compact status: JARVIS · mode · model · tokens · tools · ONLINE"""
        width = self.console.size.width
        sep = self.symbols["separator"]
        parts: list[Text] = []

        if width >= 120:
            parts.append(Text("JARVIS", style="jarvis.accent bold"))
            parts.append(Text(f" {sep} ", style="jarvis.muted"))

        parts.append(Text(self.state.mode.value.lower(), style="jarvis.accent"))

        if width >= 70 and self.state.model:
            model_display = self.state.model
            if len(model_display) > 25:
                model_display = model_display[:22] + "..."
            parts += [Text(f" {sep} ", style="jarvis.muted"),
                       Text(model_display, style="jarvis.secondary")]

        parts += [Text(f" {sep} ", style="jarvis.muted"),
                   Text(self._token_str(), style="jarvis.dim")]

        if width >= 90:
            tool_count = self.state.tools_active
            if tool_count:
                parts += [Text(f" {sep} ", style="jarvis.muted"),
                           Text(f"{tool_count} tools", style="jarvis.running")]

        if width >= 120:
            conn_style = "jarvis.success" if self.state.connection == "ONLINE" else "jarvis.warning"
            parts += [Text(f" {sep} ", style="jarvis.muted"),
                       Text(self.state.connection, style=conn_style)]

        return Text.assemble(*parts)

    # ── Plan ──────────────────────────────────────────────────────────────

    def render_plan(self, compact: bool = False) -> RenderableType:
        plan = self.state.plan
        if not plan or not plan.steps:
            return Text("", style="jarvis.muted")

        if compact:
            done = sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED)
            total = len(plan.steps)
            active = next((s for s in plan.steps if s.status == StepStatus.ACTIVE), None)
            parts = [Text(f"Plan {done}/{total}", style="jarvis.muted")]
            if active:
                parts.append(Text(f" -> {active.description}", style="jarvis.active"))
            return Text.assemble(*parts)

        lines: list[Text] = []
        for step in plan.steps:
            if step.status == StepStatus.COMPLETED:
                sym, style = self.symbols["done"], "jarvis.done"
            elif step.status == StepStatus.ACTIVE:
                sym, style = self.symbols["current"], "jarvis.active"
            elif step.status == StepStatus.FAILED:
                sym, style = self.symbols["failed"], "jarvis.failed"
            else:
                sym, style = self.symbols["planned"], "jarvis.muted"
            lines.append(Text.assemble(
                Text(f"  {sym} ", style=style),
                Text(step.description, style=style if step.status != StepStatus.PENDING else "jarvis.dim"),
            ))
        return Group(*lines)

    # ── Activity ──────────────────────────────────────────────────────────

    def render_activity(self) -> RenderableType:
        if not self.state.events:
            return Text("No events", style="jarvis.muted")
        items = [self._render_event(e) for e in self.state.events[-14:]]
        return Group(*items)

    def _render_event(self, e: AgentEvent) -> RenderableType:
        sym = self.symbols
        if e.status == EventStatus.RUNNING:
            status_sym, style = sym["running"], "jarvis.running"
        elif e.status == EventStatus.COMPLETED:
            status_sym, style = sym["done"], "jarvis.done"
        elif e.status == EventStatus.FAILED:
            status_sym, style = sym["failed"], "jarvis.failed"
        else:
            status_sym, style = sym["planned"], "jarvis.muted"

        label = e.tool or e.type.value
        header = Text.assemble(
            Text(f"  {status_sym} ", style=style),
            Text(label, style="jarvis.tool"),
        )
        parts: list[RenderableType] = [header]

        if e.arguments:
            parts.append(Text(f"    {e.arguments[:120]}", style="jarvis.dim"))
        if e.result:
            parts.append(Text(f"    {e.result[:200]}", style=style))
        if e.exit_code is not None and e.exit_code != 0:
            parts.append(Text(f"    exit {e.exit_code}", style="jarvis.error"))
        if e.duration_s is not None:
            parts.append(Text(f"    {e.duration_s:.1f}s", style="jarvis.muted"))
        if e.full_output and e.expanded:
            compressed = compress_output(e.full_output, format_type="auto", method="gzip", max_size_reduction=0.3)
            out = compressed if len(compressed) < len(e.full_output) else e.full_output
            if len(out) > 4000:
                out = out[:4000] + "\n... (truncated)"
            parts.append(Text("    --- full output ---", style="jarvis.muted"))
            parts.append(Text(out, style="jarvis.dim"))
        return Group(*parts)

    # ── Conversation ──────────────────────────────────────────────────────

    def render_conversation(self) -> RenderableType:
        """Conversation = semantic interaction only. No tool output, no
        verification, no recovery leaking in."""
        if not self.state.messages:
            return Group(
                Text(""),
                Text("What are we building?", style="jarvis.accent"),
                Text(""),
            )
        blocks: list[RenderableType] = []
        for msg in self.state.messages[-30:]:
            if msg.role == "user":
                blocks.append(self._render_user_message(msg.content))
            elif msg.role == "agent":
                blocks.append(self._render_agent_message(msg.content))
            elif msg.role == "tool":
                blocks.append(self._render_tool_result(msg.content))
            else:
                blocks.append(self._render_system_event(msg.content))
        return Group(*blocks)

    def _render_user_message(self, content: str) -> RenderableType:
        return Group(
            Text(content, style="jarvis.user"),
            Text(""),
        )

    def _render_agent_message(self, content: str) -> RenderableType:
        try:
            md = Markdown(content, code_theme="monokai")
        except Exception:
            md = Text(content, style="jarvis.agent")
        return Group(md, Text(""))

    def _render_tool_result(self, content: str) -> RenderableType:
        if len(content) > 300:
            content = content[:300] + "\n  ... (truncated)"
        return Group(Text(f"  {content}", style="jarvis.dim"),)

    def _render_system_event(self, content: str) -> RenderableType:
        return Group(Text(f"  {content}", style="jarvis.system"),)

    # ── Tool cards ────────────────────────────────────────────────────────

    def render_tool_card(self, tool_name: str, arguments: dict,
                         status: str = "running", result: str = "",
                         duration_ms: float = 0.0, expanded: bool = False) -> RenderableType:
        sym = self.symbols
        arg_summary = self._summarize_args(arguments)

        if status == "running":
            status_sym, style = sym["running"], "jarvis.running"
        elif status == "ok":
            status_sym, style = sym["done"], "jarvis.done"
        elif status == "denied":
            status_sym, style = sym["failed"], "jarvis.warning"
        else:
            status_sym, style = sym["failed"], "jarvis.failed"

        duration_str = f" ({duration_ms:.0f}ms)" if duration_ms > 0 else ""

        if not expanded:
            return Text.assemble(
                Text(f"  {status_sym} ", style=style),
                Text(tool_name, style="jarvis.tool"),
                Text(f" {arg_summary}", style="jarvis.dim"),
                Text(duration_str, style="jarvis.muted"),
            )

        lines: list[RenderableType] = [
            Text.assemble(
                Text(f"  {status_sym} ", style=style),
                Text(tool_name, style="jarvis.tool"),
                Text(duration_str, style="jarvis.muted"),
            ),
        ]
        if arguments:
            for k, v in arguments.items():
                val = str(v)
                if len(val) > 80:
                    val = val[:77] + "..."
                lines.append(Text(f"    {k}: {val}", style="jarvis.dim"))
        if result and status != "running":
            res_preview = result[:200] + ("..." if len(result) > 200 else "")
            lines.append(Text(f"    {res_preview}", style=style))
        return Group(*lines)

    def _summarize_args(self, arguments: dict) -> str:
        if not arguments:
            return ""
        if "path" in arguments:
            return str(arguments["path"])
        if "pattern" in arguments:
            return str(arguments["pattern"])
        if "command" in arguments:
            cmd = str(arguments["command"])
            return cmd[:50] + ("..." if len(cmd) > 50 else "")
        if "query" in arguments:
            return str(arguments["query"])
        first_val = next(iter(arguments.values()), None)
        if first_val is not None:
            s = str(first_val)
            return s[:40] + ("..." if len(s) > 40 else "")
        return ""

    # ── Verification & Recovery (standalone, not in conversation) ─────────

    def render_verification_block(self, steps: list[dict]) -> RenderableType:
        sym = self.symbols
        lines: list[RenderableType] = [Text("  Verification", style="jarvis.info")]
        for step in steps:
            name = step.get("name", "")
            passed = step.get("passed", False)
            running = step.get("running", False)
            duration = step.get("duration_ms", 0)
            if running:
                s, style = sym["running"], "jarvis.running"
            elif passed:
                s, style = sym["done"], "jarvis.done"
            else:
                s, style = sym["failed"], "jarvis.failed"
            dur = f" ({duration:.0f}ms)" if duration > 0 else ""
            lines.append(Text(f"    {s} {name}{dur}", style=style))
        return Group(*lines)

    def render_recovery_block(self, error: str, attempt: int = 1) -> RenderableType:
        lines: list[RenderableType] = [
            Text(f"  RECOVERING (attempt {attempt})", style="jarvis.warning"),
        ]
        if error:
            preview = error[:200] + ("..." if len(error) > 200 else "")
            lines.append(Text(f"    {preview}", style="jarvis.dim"))
        return Group(*lines)

    def render_verification(self) -> RenderableType | None:
        if not self.state.verification_steps:
            return None
        return self.render_verification_block(self.state.verification_steps)

    def render_recovery(self) -> RenderableType | None:
        if not self.state.recovery_active:
            return None
        return self.render_recovery_block(
            self.state.recovery_error,
            attempt=self.state.recovery_attempt,
        )

    # ── Code workspace ────────────────────────────────────────────────────

    def render_code_files(self) -> RenderableType:
        if not self.state.code_files:
            return Text("No files", style="jarvis.muted")
        lines = []
        for f in self.state.code_files:
            mark = " *" if f.modified else ""
            style = "jarvis.active" if f.selected else "jarvis.dim"
            lines.append(Text(f"  {f.path}{mark}", style=style))
        return Group(*lines)

    def render_code_buffer(self) -> RenderableType:
        if not self.state.code_content:
            return Text("No file selected", style="jarvis.muted")
        return Syntax(
            self.state.code_content, self.state.code_language,
            theme="monokai", line_numbers=True, word_wrap=False,
        )

    def render_code_header(self) -> Text:
        path = self.state.code_path or "---"
        loc = f"{self.state.code_loc:,} LOC" if self.state.code_loc else ""
        mod = " MODIFIED" if self.state.code_modified else ""
        return Text(f"  {path} {loc}{mod}", style="jarvis.dim")

    # ── Memory workspace ──────────────────────────────────────────────────

    def render_memory(self) -> RenderableType:
        parts: list[RenderableType] = []
        if self.state.memory_query:
            parts.append(Text(f"  query: {self.state.memory_query}", style="jarvis.accent"))
        if not self.state.memory_hits:
            parts.append(Text("  No memories", style="jarvis.muted"))
            return Group(*parts)
        for h in self.state.memory_hits:
            parts.append(Text.assemble(
                Text(f"  {h.score:.2f} ", style="jarvis.success"),
                Text(h.title, style="jarvis.user"),
            ))
            if h.snippet:
                parts.append(Text(f"    {h.snippet[:120]}", style="jarvis.dim"))
        return Group(*parts)

    # ── Audit workspace ───────────────────────────────────────────────────

    def render_audit(self) -> RenderableType:
        if not self.state.audit_sections:
            return Text("  No audit data", style="jarvis.muted")
        blocks: list[RenderableType] = []
        for section in self.state.audit_sections:
            blocks.append(Text(f"  {section.title}", style="jarvis.accent"))
            for status_key, label, detail in section.items:
                sym = self.symbols.get(status_key, "-")
                style_map = {"done": "jarvis.done", "failed": "jarvis.failed",
                             "running": "jarvis.running", "warning": "jarvis.warning"}
                style = style_map.get(status_key, "jarvis.dim")
                line = Text.assemble(Text(f"    {sym} ", style=style), Text(label, style=style))
                if detail:
                    line = Text.assemble(line, Text(f"  {detail}", style="jarvis.dim"))
                blocks.append(line)
        return Group(*blocks)

    # ── Security confirmation ─────────────────────────────────────────────

    def render_confirmation(self) -> RenderableType:
        req = self.state.pending_confirmation
        if not req:
            return Text("")
        lines: list[RenderableType] = [
            Text("  Permission required", style="jarvis.error"),
            Text(""),
            Text(f"  {req.operation}", style="jarvis.accent"),
            Text(""),
            Text("  [Enter] Allow  [Esc] Deny  [A] Always", style="jarvis.dim"),
        ]
        return Group(*lines)

    def confirm_interactive(self, req: ConfirmationRequest) -> str:
        self.set_confirmation(req)
        pause = getattr(self._live_display, "pause", None)
        cm = pause() if pause is not None else nullcontext()
        with cm:
            self.console.print(self.render_confirmation())
            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "deny"
            finally:
                self.set_confirmation(None)
        if answer in ("y", "yes"):
            return "once"
        if answer in ("r", "run"):
            return "run"
        return "deny"

    def attach_live(self, display) -> None:
        self._live_display = display

    def detach_live(self) -> None:
        self._live_display = None

    # ── Full-screen task view ─────────────────────────────────────────────

    def render_task_screen(self) -> RenderableType:
        """Claude Code-style screen: conversation is the UI.

        Layout (from attached jarvis_claude_ui.py):
          Header: one compact status line (JARVIS MK-X · AGENT · model · tokens · ONLINE)
          Body: conversation + plan + activity + provider notices
          Footer: separator + anchored input bar
        """
        width = self.console.size.width

        # ── Header: single compact status line ──────────────────────────
        header = self._render_header()

        # ── Body: conversation + plan + activity ────────────────────────
        body = self._render_body()

        # ── Footer: separator + anchored prompt ─────────────────────────
        sep = Text("─" * max(1, width - 1), style="jarvis.muted")
        prompt = Text()
        prompt.append("JARVIS", style="jarvis.accent")
        prompt.append(f" [{self.state.mode.value.lower()}] > ", style="jarvis.tool")
        if self.state.tools_active > 0:
            prompt.append("working...", style="jarvis.running")
        else:
            prompt.append("_", style="jarvis.dim")

        elements: list[RenderableType] = [
            header,
            Text("") if width < 70 else Text(""),
            body,
            Text("") if width < 70 else Text(""),
            sep,
            prompt,
        ]

        if self.state.pending_confirmation is not None:
            elements += [Text(""), self.render_confirmation()]

        return Group(*elements)

    def _render_header(self) -> Text:
        """ClaudeCode-style header: one compact line with all status info."""
        width = self.console.size.width
        t = Text()
        t.append("JARVIS", style="jarvis.accent")
        t.append(" MK-X", style="jarvis.tool")
        t.append("  ·  ", style="jarvis.muted")
        t.append(self.state.mode.value.lower(), style="jarvis.accent")

        # Model (only if wide enough)
        if width >= 80 and self.state.model:
            model = self.state.model
            if len(model) > 28:
                model = model[:25] + "..."
            t.append("  ·  ", style="jarvis.muted")
            t.append(model, style="jarvis.secondary")

        # Tokens (only if wide)
        if width >= 100:
            used = self.state.tokens_used / 1000
            limit = self.state.tokens_limit / 1000
            t.append("  ·  ", style="jarvis.muted")
            t.append(f"{used:.1f}K/{limit:.0f}K", style="jarvis.dim")

        # Connection
        t.append("  ·  ", style="jarvis.muted")
        conn_style = "jarvis.success" if self.state.connection == "ONLINE" else "jarvis.warning"
        t.append(self.state.connection, style=conn_style)

        # Workspace (only if wide)
        if width >= 90 and self.state.workspace and self.state.workspace != "chat":
            t.append("  ·  ", style="jarvis.muted")
            t.append(self.state.workspace, style="jarvis.dim")

        return t

    def _render_body(self) -> RenderableType:
        """ClaudeCode-style body: conversation is primary, plan + activity inline."""
        blocks: list[RenderableType] = []

        # Empty state
        if not self.state.messages and not self.state.events:
            blocks.extend([
                Text("Ready.", style="jarvis.tool"),
                Text(""),
                Text("Tell JARVIS what you want to build, inspect, fix, or test.", style="jarvis.dim"),
            ])
            return Group(*blocks)

        # Conversation (last 20 messages, semantic only)
        for msg in self.state.messages[-20:]:
            if msg.role == "user":
                blocks.extend([
                    Text("You", style="jarvis.accent"),
                    Text(f"> {msg.content}", style="jarvis.user"),
                    Text(""),
                ])
            elif msg.role == "agent":
                blocks.extend([
                    Text("JARVIS", style="jarvis.tool"),
                    self._render_agent_message(msg.content),
                    Text(""),
                ])
            else:
                blocks.extend([self._render_system_event(msg.content), Text("")])

        # Plan (only when active)
        plan_block = self.render_plan()
        if plan_block and self.state.plan and self.state.plan.steps:
            blocks.extend([Text("Plan", style="jarvis.accent"), plan_block, Text("")])

        # Activity (only when events exist)
        if self.state.events:
            blocks.extend([Text("Activity", style="jarvis.accent"), self.render_activity(), Text("")])

        # Verification (standalone, not in conversation)
        verification = self.render_verification()
        if verification is not None:
            blocks.extend([verification, Text("")])

        # Recovery (standalone, not in conversation)
        recovery = self.render_recovery()
        if recovery is not None:
            blocks.extend([recovery, Text("")])

        # Provider notices (semantic, not logging)
        notice = self._render_provider_notice()
        if notice is not None:
            blocks.append(notice)

        return Group(*blocks)

    def _render_provider_notice(self) -> Text | None:
        """Render a provider notice (rate limit, provider switch) as a semantic UI event."""
        notice = self.state.provider_notice
        if notice is None:
            return None
        provider, message, kind, retry_after = notice
        style_map = {"error": "jarvis.error", "warning": "jarvis.warning", "info": "jarvis.accent"}
        sym_map = {"error": "✗", "warning": "⚠", "info": "●"}
        style = style_map.get(kind, "jarvis.warning")
        sym = sym_map.get(kind, "⚠")
        text = f"{provider}: {message}"
        if retry_after is not None:
            text += f" · retrying in {retry_after:.0f}s"
        return Text(f"{sym} {text}", style=style)

    def render_activity_panel(self) -> RenderableType:
        return Panel(
            self.render_activity(),
            title="ACTIVITY",
            title_align="left",
            border_style=COLORS.border,
            box=BoxStyles.ACTIVITY,
            padding=(0, 1),
        )

    def render_palette(self, entries: Sequence[tuple[str, str]] | None = None) -> RenderableType:
        if not entries:
            entries = [
                ("chat", "Conversation"), ("plan", "Plan focus"),
                ("code", "Code workspace"), ("activity", "Event stream"),
                ("memory", "Memory"), ("audit", "Audit / health"),
            ]
        table = Table(show_header=False, box=None)
        table.add_column(style="bold cyan", width=18)
        table.add_column(style="dim")
        for key, desc in entries:
            table.add_row(key, desc)
        return Panel(table, title="COMMANDS", border_style=COLORS.border, box=box.ROUNDED)

    def build_full_layout(self):
        return self.layout_mgr.build(
            conversation=self.render_conversation(),
            plan=self.render_plan(),
            activity=self.render_activity(),
            code=self.render_code_buffer(),
            memory=self.render_memory(),
            audit=self.render_audit(),
        )

    def print_status_bar(self) -> None:
        self.console.print(self.render_status())

    def print_prompt(self) -> str:
        return "> "

    def clear(self) -> None:
        self.console.clear()

    def print(self, *args: Any, **kwargs: Any) -> None:
        self.console.print(*args, **kwargs)

    def print_error(self, title: str, detail: str = "", fallback: str = "") -> None:
        self.console.print(Text(f"  {title}", style="jarvis.error"))
        if detail:
            self.console.print(Text(f"    {detail}", style="jarvis.dim"))
        if fallback:
            self.console.print(Text(f"    {fallback}", style="jarvis.warning"))

    def print_success(self, msg: str) -> None:
        self.console.print(Text(f"  {msg}", style="jarvis.success"))
