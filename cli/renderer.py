"""Renderable helpers for the JARVIS MK-X terminal.

Claude Code-style UI: conversation is the screen. No borders, no panels,
no permanent sidebars. Clean, minimal, fast.

ARCHITECTURE INVARIANT:
    ``render_task_screen()`` is the SINGLE canonical render path.
    All other render methods are building blocks used by it.
    ``build_full_layout()`` delegates to ``render_task_screen()``
    when the LayoutManager is not needed for wide terminals.

``Renderer`` is the pure display layer: backend owns state and decisions,
this class only turns ``AppState`` snapshots into Rich renderables.
"""

from __future__ import annotations

import logging
import re
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
from .theme import COLORS, BoxStyles, build_rich_theme, get_symbols

logger = logging.getLogger("jarvis.cli.renderer")

CODE_THEME = "monokai"

# Markdown detection: explicit constructs, not just "has newlines"
_MD_CONSTRUCTS = re.compile(
    r"(^#{1,6}\s|^\s*[-*+]\s|^\s*\d+\.\s|^\s*>\s|```|^\s*\|.*\|.*\||"
    r"^\s*\[.+\]\(.+\)|^\s*!\[.*\]\(.+\))",
    re.MULTILINE,
)


def render_markdown(text: str, *, plain: bool = False):
    if plain or not _looks_like_markdown(text):
        return Text(text)
    return Markdown(text, code_theme=CODE_THEME)


def _looks_like_markdown(text: str) -> bool:
    """Detect actual Markdown constructs, not just multiline text."""
    stripped = text.lstrip()
    if not stripped:
        return False
    if "\n" not in text:
        return bool(stripped.startswith(("# ", "- ", "* ", "> ", "```")))
    return bool(_MD_CONSTRUCTS.search(text))


class Renderer:
    """Pure display layer. Claude Code-style: conversation is the UI.

    Single canonical render path: ``render_task_screen()``.
    All other methods are building blocks.
    """

    def __init__(self, console: Console | None = None, unicode: bool = True) -> None:
        self.console = console or Console(theme=build_rich_theme(), highlight=False, emoji=False)
        self.layout_mgr = LayoutManager(self.console)
        self.symbols = get_symbols(unicode)
        self.state = AppState()
        self._live_display = None
        self._streaming_text: str = ""

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

    def set_streaming(self, text: str) -> None:
        """Update the streaming text token-by-token."""
        self._streaming_text = text

    def clear_streaming(self) -> None:
        self._streaming_text = ""

    def _recount_tools(self) -> None:
        self.state.tools_active = sum(
            1 for e in self.state.events
            if e.type == EventType.TOOL and e.status == EventStatus.RUNNING
        )

    # ── Status bar — compact single line ──────────────────────────────────

    def _token_str(self) -> str:
        used, limit = self.state.tokens_used, self.state.tokens_limit
        used_str = f"{used / 1000:.1f}K" if used >= 1000 else str(used)
        limit_str = f"{limit // 1000}K" if limit >= 1000 else str(limit)
        return f"{used_str}/{limit_str}"

    def render_status(self) -> Text:
        """Compact status: JARVIS MK-X · model · provider · MEM ✓ · ONLINE"""
        width = self.console.size.width
        sep = self.symbols["separator"]
        parts: list[Text] = []

        parts.append(Text("JARVIS MK-X", style="jarvis.accent bold"))
        parts.append(Text(f" {sep} ", style="jarvis.muted"))

        model_name = self.state.model or "qwen2.5:3b"
        if len(model_name) > 20:
            model_name = model_name[:18] + "..."
        parts.append(Text(model_name, style="jarvis.secondary"))
        parts.append(Text(f" {sep} ", style="jarvis.muted"))

        parts.append(Text(self.state.provider or "Ollama", style="jarvis.accent"))
        parts.append(Text(f" {sep} ", style="jarvis.muted"))

        parts.append(Text(self._token_str(), style="jarvis.dim"))
        parts.append(Text(f" {sep} ", style="jarvis.muted"))

        mem_status = "MEM \u2713" if self.state.memory_enabled else "MEM -"
        mem_style = "jarvis.success" if self.state.memory_enabled else "jarvis.dim"
        parts.append(Text(mem_status, style=mem_style))
        parts.append(Text(f" {sep} ", style="jarvis.muted"))

        conn_style = "jarvis.success" if self.state.connection == "ONLINE" else "jarvis.warning"
        parts.append(Text(self.state.connection, style=conn_style))

        if width >= 90 and self.state.vram_gb is not None:
            parts.append(Text(f" {sep} ", style="jarvis.muted"))
            parts.append(Text(f"{self.state.vram_gb:.1f}GB VRAM", style="jarvis.dim"))

        return Text.assemble(*parts)

    # ── Shared conversation helpers ───────────────────────────────────────
    # Used by both render_task_screen() and render_conversation().
    # Single source of truth for how messages look.

    def _render_user_block(self, content: str) -> RenderableType:
        """Shared user message block — Claude Code style."""
        return Group(
            Text("You", style="jarvis.user_label bold"),
            Text(f"> {content}", style="jarvis.user"),
            Text(""),
        )

    def _render_agent_block(self, content: str) -> RenderableType:
        """Shared agent message block — Claude Code style."""
        return Group(
            self._render_md_or_text(content),
            Text(""),
        )

    def _render_md_or_text(self, content: str) -> RenderableType:
        """Render content as Markdown if it looks like it, else plain text."""
        if not _looks_like_markdown(content):
            return Text(content, style="jarvis.agent")
        try:
            return Markdown(content, code_theme=CODE_THEME)
        except Exception:
            return Text(content, style="jarvis.agent")

    def _render_system_block(self, content: str) -> RenderableType:
        """Shared system event block."""
        return Group(Text(f"  {content}", style="jarvis.system"),)

    def _render_conversation_messages(self, limit: int = 20) -> list[RenderableType]:
        """Shared conversation rendering — used by both render_task_screen and render_conversation."""
        if not self.state.messages:
            return []
        blocks: list[RenderableType] = []
        for msg in self.state.messages[-limit:]:
            if msg.role == "user":
                blocks.append(self._render_user_block(msg.content))
            elif msg.role == "agent":
                blocks.append(self._render_agent_block(msg.content))
            else:
                blocks.append(self._render_system_block(msg.content))
        return blocks

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
        """Render a single tool event. No compression here — that's the service layer's job."""
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
        # Output truncation only — no compression in the renderer
        if e.full_output and e.expanded:
            out = e.full_output
            if len(out) > 4000:
                out = out[:4000] + "\n... (truncated)"
            parts.append(Text("    --- full output ---", style="jarvis.muted"))
            parts.append(Text(out, style="jarvis.dim"))
        return Group(*parts)

    # ── Conversation (standalone, for build_full_layout) ──────────────────

    def render_conversation(self) -> RenderableType:
        """Standalone conversation view. Uses shared helpers for consistency."""
        if not self.state.messages:
            return Group(
                Text(""),
                Text("What are we building?", style="jarvis.accent"),
                Text(""),
            )
        blocks = self._render_conversation_messages(limit=30)
        return Group(*blocks) if blocks else Text("")

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

    # ── Verification & Recovery ───────────────────────────────────────────

    def render_verification_block(self, steps: list[dict]) -> RenderableType:
        sym = self.symbols
        lines: list[RenderableType] = [
            Text.assemble(Text(f"  {sym['running']} ", style="jarvis.running"), Text("Verification", style="jarvis.info bold"))
        ]
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

    def render_turn_footer(self, latency_s: float | None = None, tokens: int | None = None,
                           tools_count: int | None = None, cost_str: str = "Local $0.00") -> RenderableType:
        """Render Claude Code subtle turn stats footer."""
        parts: list[Text] = []
        sep = Text(" . ", style="jarvis.muted")

        lat = latency_s if latency_s is not None else self.state.last_turn_latency_s
        if lat is not None and lat > 0:
            parts.append(Text(f"{lat:.1f}s", style="jarvis.dim"))

        tok = tokens if tokens is not None else self.state.last_turn_tokens
        if tok is not None and tok > 0:
            if parts:
                parts.append(sep)
            parts.append(Text(f"{tok:,} tokens", style="jarvis.dim"))

        tc = tools_count if tools_count is not None else len(self.state.events)
        if tc > 0:
            if parts:
                parts.append(sep)
            parts.append(Text(f"{tc} tools", style="jarvis.dim"))

        if parts:
            parts.append(sep)
        parts.append(Text(cost_str, style="jarvis.muted"))

        return Text.assemble(Text("  "), *parts)

    def render_interrupt_block(self, model: str = "1.5B", text: str = "") -> RenderableType:
        sym = self.symbols
        lines: list[RenderableType] = [
            Text.assemble(
                Text(f"  {sym['diamond']} ", style="jarvis.secondary"),
                Text(f"interrupt . {model}", style="jarvis.secondary bold"),
            )
        ]
        if text:
            lines.append(Text(f"    {text}", style="jarvis.dim"))
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

    # ── Streaming indicator ───────────────────────────────────────────────

    def render_streaming(self) -> RenderableType:
        """Show live streaming text with a cursor."""
        if not self._streaming_text:
            return Text("")
        if not _looks_like_markdown(self._streaming_text):
            return Group(
                Text(self._streaming_text, style="jarvis.agent"),
                Text("\u258c", style="jarvis.accent"),
            )
        try:
            md = Markdown(self._streaming_text, code_theme="monokai")
            return Group(md, Text("  \u258c", style="jarvis.accent"))
        except Exception:
            return Group(
                Text(self._streaming_text, style="jarvis.agent"),
                Text("\u258c", style="jarvis.accent"),
            )

    # ── Workspaces ────────────────────────────────────────────────────────

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

    # ── Confirmation ──────────────────────────────────────────────────────
    # Labels now match actual parsing (Enter/y=yes, Esc=n=deny, A=r=always-run)

    def render_confirmation(self) -> RenderableType:
        req = self.state.pending_confirmation
        if not req:
            return Text("")
        lines: list[RenderableType] = [
            Text("  Permission required", style="jarvis.error"),
            Text(""),
            Text(f"  {req.operation}", style="jarvis.accent"),
            Text(""),
            Text("  [y] Allow once  [r] Allow for this run  [n] Deny", style="jarvis.dim"),
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

    # ── Canonical render path: render_task_screen() ───────────────────────
    # This is the SINGLE entry point for the live UI.
    # All body parts are assembled here, not in layout.py.

    def render_task_screen(self) -> RenderableType:
        """THE canonical render path. Single source of truth for the UI.

        Layout:
          Header: compact status line (JARVIS · model · provider · MEM ✓ · ONLINE)
          Body:   conversation + streaming + plan + activity + verification + footer
          Footer: separator + anchored input bar
        """
        width = self.console.size.width

        header = self._render_header()
        body = self._render_body()
        footer = self._render_footer(width)

        elements: list[RenderableType] = [header, Text(""), body, Text(""), footer]

        if self.state.pending_confirmation is not None:
            elements += [Text(""), self.render_confirmation()]

        return Group(*elements)

    def _render_header(self) -> RenderableType:
        """Compact top status bar in a subtle panel."""
        width = self.console.size.width
        sep = self.symbols["separator"]

        t = Text()
        t.append("JARVIS", style="jarvis.accent bold")
        t.append(f" {sep} ", style="jarvis.muted")

        model_name = self.state.model or "qwen2.5:3b"
        if len(model_name) > 22:
            model_name = model_name[:20] + "..."
        t.append(model_name, style="jarvis.secondary")
        t.append(f" {sep} ", style="jarvis.muted")

        t.append(self.state.provider or "Ollama", style="jarvis.accent")
        t.append(f" {sep} ", style="jarvis.muted")

        mem_status = "MEM \u2713" if self.state.memory_enabled else "MEM -"
        mem_style = "jarvis.success" if self.state.memory_enabled else "jarvis.dim"
        t.append(mem_status, style=mem_style)
        t.append(f" {sep} ", style="jarvis.muted")

        conn_style = "jarvis.success" if self.state.connection == "ONLINE" else "jarvis.warning"
        t.append(self.state.connection, style=conn_style)

        if width >= 95 and self.state.vram_gb is not None:
            t.append(f" {sep} ", style="jarvis.muted")
            t.append(f"{self.state.vram_gb:.1f}GB VRAM", style="jarvis.dim")

        return Panel(t, box=box.ROUNDED, border_style=COLORS.border, padding=(0, 1))

    def _render_body(self) -> RenderableType:
        """Body assembly: conversation + streaming + plan + activity + verification + diagnostics."""
        blocks: list[RenderableType] = []

        # Empty state
        if not self.state.messages and not self.state.events:
            return Group(
                Text("Ready.", style="jarvis.tool"),
                Text(""),
                Text("Tell JARVIS what you want to build, inspect, fix, or test.", style="jarvis.dim"),
            )

        # Conversation — uses SHARED helper for consistency with render_conversation()
        blocks.extend(self._render_conversation_messages(limit=20))

        # Streaming text (live tokens during agent work)
        if self._streaming_text:
            blocks.extend([Text(""), self.render_streaming()])

        # Interrupt state
        if self.state.interrupt_active:
            blocks.extend([
                self.render_interrupt_block(self.state.interrupt_model, self.state.interrupt_text),
                Text(""),
            ])

        # Plan (only when active)
        plan_block = self.render_plan()
        if plan_block and self.state.plan and self.state.plan.steps:
            blocks.extend([Text("  Plan", style="jarvis.accent"), plan_block, Text("")])

        # Activity
        if self.state.events:
            blocks.extend([self.render_activity(), Text("")])

        # Verification
        verification = self.render_verification()
        if verification is not None:
            blocks.extend([verification, Text("")])

        # Recovery
        recovery = self.render_recovery()
        if recovery is not None:
            blocks.extend([recovery, Text("")])

        # Turn footer
        if self.state.last_turn_latency_s is not None or self.state.last_turn_tokens is not None:
            blocks.extend([self.render_turn_footer(), Text("")])

        # Provider notices
        notice = self._render_provider_notice()
        if notice is not None:
            blocks.append(notice)

        return Group(*blocks)

    def _render_footer(self, width: int) -> Text:
        """Anchored input bar with mode indicator."""
        sep = "\u2500" * max(1, width - 1)
        line = Text(sep, style="jarvis.muted")
        line.append("\n")
        line.append("JARVIS", style="jarvis.accent")
        line.append(f" [{self.state.mode.value.lower()}] > ", style="jarvis.tool")
        if self.state.tools_active > 0:
            line.append("\u25d8 working...", style="jarvis.running")
        else:
            line.append("_", style="jarvis.dim")
        return line

    def _render_provider_notice(self) -> Text | None:
        notice = self.state.provider_notice
        if notice is None:
            return None
        provider, message, kind, retry_after = notice
        style_map = {"error": "jarvis.error", "warning": "jarvis.warning", "info": "jarvis.accent"}
        sym_map = {"error": "\u2717", "warning": "\u26a0", "info": "\u25cf"}
        style = style_map.get(kind, "jarvis.warning")
        sym = sym_map.get(kind, "\u26a0")
        text = f"{provider}: {message}"
        if retry_after is not None:
            text += f" . retrying in {retry_after:.0f}s"
        return Text(f"{sym} {text}", style=style)

    # ── Layout integration (wide terminals only) ──────────────────────────

    def build_full_layout(self):
        """Layout path for wide terminals. Delegates body to render_task_screen()."""
        return self.layout_mgr.build(
            conversation=self.render_conversation(),
            plan=self.render_plan(),
            activity=self.render_activity(),
            code=self.render_code_buffer(),
            memory=self.render_memory(),
            audit=self.render_audit(),
        )

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

    # ── Output helpers ────────────────────────────────────────────────────

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
