"""Renderable helpers for the JARVIS MK-X terminal.

Assistant responses are usually Markdown; the Rich ``Markdown`` renderable adds
syntax highlighting for code blocks and neat lists. Plain text stays plain, and
the ``--json`` output path is never routed through here.

``Renderer`` is the pure display layer: backend owns state and decisions, this
class only turns ``AppState`` snapshots into Rich renderables.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from contextlib import nullcontext
from datetime import datetime
from typing import Any

from rich import box
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
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
    RiskLevel,
    StepStatus,
)
from .theme import COLORS, BoxStyles, get_symbols

logger = logging.getLogger("jarvis.cli.renderer")

CODE_THEME = "monokai"


def render_markdown(text: str, *, plain: bool = False):
    """Turn an assistant response into a Rich renderable.

    Args:
        text: raw assistant output.
        plain: force plain-text rendering (no Markdown interpretation).
    """
    if plain or not _looks_like_markdown(text):
        return Text(text)
    return Markdown(text, code_theme=CODE_THEME)


def _looks_like_markdown(text: str) -> bool:
    """Cheap heuristic: only interpret as Markdown when it looks like it.

    Avoids mangling one-line answers or plain prose with stray '#'/'*' that a
    naive renderer would choke on, and keeps rendering cheap for JSON/plain
    output.
    """
    stripped = text.lstrip()
    if not stripped:
        return False
    if "\n" not in text:
        # Single-line answers: only treat explicit emphasis/links/code as MD.
        return bool(stripped.startswith(("#", "- ", "* ", "> ", "```")))
    return True


class Renderer:
    """Pure display layer. Mutators only accept state that the backend already decided."""

    def __init__(self, console: Console | None = None, unicode: bool = True) -> None:
        self.console = console or Console(highlight=False, emoji=False)
        self.layout_mgr = LayoutManager(self.console)
        self.symbols = get_symbols(unicode)
        self.state = AppState()
        self._live_display = None

    # ------------------------------------------------------------------
    # State mutators (called by AgentLoop / event bus only)
    # ------------------------------------------------------------------

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

    def set_code(
        self,
        files: Sequence[CodeFile],
        path: str = "",
        content: str = "",
        language: str = "python",
        loc: int = 0,
        modified: bool = False,
    ) -> None:
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

    def _recount_tools(self) -> None:
        self.state.tools_active = sum(
            1 for e in self.state.events
            if e.type == EventType.TOOL and e.status == EventStatus.RUNNING
        )

    # ------------------------------------------------------------------
    # Status bar — collapses fields by terminal width
    # ------------------------------------------------------------------

    def _token_str(self) -> str:
        used, limit = self.state.tokens_used, self.state.tokens_limit
        u = f"{used / 1000:.1f}K" if used >= 1000 else str(used)
        l = f"{limit // 1000}K" if limit >= 1000 else str(limit)
        return f"{u}/{l}"

    def render_status(self) -> Text:
        """
        Priority collapse:
          ≥120  full
          90–119 drop TOOL + MEMORY
          <70   drop model + time
        """
        width = self.console.size.width
        sym = self.symbols
        sep = Text(f" {sym['separator']} ", style="jarvis.muted")
        parts: list[Text] = [
            Text(f"{sym['diamond']} ", style="jarvis.primary"),
            Text("JARVIS", style="bold jarvis.primary"),
            Text(f" {sym['separator']} ", style="jarvis.muted"),
            Text(self.state.mode.value.upper(), style="jarvis.accent"),
        ]

        if width >= 70:
            model_display = self.state.model
            if len(model_display) > 25:
                model_display = model_display[:22] + "..."
            parts += [sep, Text(model_display, style="jarvis.secondary")]

        parts += [sep, Text(self._token_str(), style="jarvis.dim")]

        if width >= 120:
            tool_sym = sym['running'] if self.state.tools_active else sym['done']
            tool_style = "jarvis.running" if self.state.tools_active else "jarvis.done"
            tool_label = f"{tool_sym} 1 TOOL" if self.state.tools_active == 1 else f"{tool_sym} {self.state.tools_active} TOOLS" if self.state.tools_active else f"{sym['done']} IDLE"
            parts += [sep, Text(tool_label, style=tool_style)]
            if self.state.memory_enabled:
                parts += [sep, Text(f"{sym['star']} MEMORY", style="jarvis.success")]

        conn_sym = sym['done'] if self.state.connection == "ONLINE" else sym['failed']
        conn_style = "jarvis.success" if self.state.connection == "ONLINE" else "jarvis.warning"
        parts += [sep, Text(f"{conn_sym} {self.state.connection}", style=conn_style)]

        if width >= 90:
            parts += [sep, Text(datetime.now().strftime("%H:%M:%S"), style="jarvis.dim")]

        return Text.assemble(*parts)

    # ------------------------------------------------------------------
    # Plan panel (stateful snapshot only)
    # ------------------------------------------------------------------

    def render_plan(self) -> RenderableType:
        plan = self.state.plan
        if not plan or not plan.steps:
            return Text("No active plan", style="jarvis.muted")

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
                Text(f"{sym} ", style=style),
                Text(step.description, style=style if step.status != StepStatus.PENDING else "jarvis.dim"),
            ))
        return Group(*lines)

    # ------------------------------------------------------------------
    # Activity = live structured event stream
    # ------------------------------------------------------------------

    def render_activity(self) -> RenderableType:
        if not self.state.events:
            return Text("No recent events", style="jarvis.muted")
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
            Text(f"{status_sym} ", style=style),
            Text(label, style="bold jarvis.tool"),
        )
        parts: list[RenderableType] = [header]

        if e.arguments:
            parts.append(Text(f"  {e.arguments}", style="jarvis.dim"))
        if e.result:
            parts.append(Text(f"  {e.result}", style=style))
        if e.exit_code is not None and e.exit_code != 0:
            parts.append(Text(f"  Exit code: {e.exit_code}", style="jarvis.error"))
        if e.duration_s is not None:
            parts.append(Text(f"  {e.duration_s:.1f}s", style="jarvis.muted"))
        if e.full_output and e.expanded:
            # Compress output before truncation for token efficiency
            compressed = compress_output(
                e.full_output,
                format_type="auto",
                method="gzip",
                max_size_reduction=0.3,
            )
            out = compressed if len(compressed) < len(e.full_output) else e.full_output
            if len(out) > 4000:
                out = out[:4000] + f"\n{sym['ellipsis']} (truncated)"
            parts.append(Text(f"  {sym['separator']}{sym['separator']}{sym['separator']} full output {sym['separator']}{sym['separator']}{sym['separator']}", style="jarvis.muted"))
            parts.append(Text(out, style="jarvis.dim"))
        return Group(*parts)

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    def render_conversation(self) -> RenderableType:
        if not self.state.messages:
            return Text("Ready. Type a request or /help.", style="jarvis.muted")
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

        # Inject verification block if steps exist
        if self.state.verification_steps:
            blocks.append(Text(""))
            blocks.append(self.render_verification_block(self.state.verification_steps))

        # Inject recovery block if active
        if self.state.recovery_active:
            blocks.append(Text(""))
            blocks.append(self.render_recovery_block(
                self.state.recovery_error,
                attempt=self.state.recovery_attempt,
            ))

        return Group(*blocks)

    def _render_user_message(self, content: str) -> RenderableType:
        """Claude Code-style user message: label + indented content."""
        sym = self.symbols
        return Group(
            Text(f"{sym['arrow_right']} You", style="bold bright_white"),
            Text(f"  {content}", style="jarvis.user"),
            Text(""),
        )

    def _render_agent_message(self, content: str) -> RenderableType:
        """Claude Code-style assistant message: label + markdown content."""
        sym = self.symbols
        try:
            md = Markdown(content, code_theme="monokai")
        except Exception:
            md = Text(content, style="jarvis.agent")
        return Group(
            Text(f"{sym['diamond']} JARVIS", style="bold bright_cyan"),
            md,
            Text(""),
        )

    def _render_tool_result(self, content: str) -> RenderableType:
        """Tool result: compact, dim, no label."""
        if len(content) > 300:
            content = content[:300] + f"\n  {self.symbols['ellipsis']} (truncated)"
        return Group(
            Text(f"  {content}", style="jarvis.dim"),
        )

    def _render_system_event(self, content: str) -> RenderableType:
        """System/verification event: muted style."""
        return Group(
            Text(f"  {content}", style="jarvis.system"),
        )

    # ------------------------------------------------------------------
    # Tool cards — collapsed by default, expandable
    # ------------------------------------------------------------------

    def render_tool_card(self, tool_name: str, arguments: dict,
                         status: str = "running", result: str = "",
                         duration_ms: float = 0.0, expanded: bool = False) -> RenderableType:
        """A single tool execution card.

        Collapsed:  ✓ filesystem.read src/auth.py  (18ms)
        Expanded:   full details panel
        """
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
                Text(tool_name, style="bold jarvis.tool"),
                Text(f" {arg_summary}", style="jarvis.dim"),
                Text(duration_str, style="jarvis.muted"),
            )

        # Expanded view
        lines: list[RenderableType] = [
            Text.assemble(
                Text(f"  {status_sym} ", style=style),
                Text(tool_name, style="bold jarvis.tool"),
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
            lines.append(Text(f"    result: {res_preview}", style=style))
        return Group(*lines)

    def _summarize_args(self, arguments: dict) -> str:
        """Create a one-line summary of tool arguments."""
        if not arguments:
            return ""
        # For filesystem tools, show the path
        if "path" in arguments:
            return str(arguments["path"])
        if "pattern" in arguments:
            return str(arguments["pattern"])
        if "command" in arguments:
            cmd = str(arguments["command"])
            return cmd[:50] + ("..." if len(cmd) > 50 else "")
        if "query" in arguments:
            return str(arguments["query"])
        # Generic: first value
        first_val = next(iter(arguments.values()), None)
        if first_val is not None:
            s = str(first_val)
            return s[:40] + ("..." if len(s) > 40 else "")
        return ""

    # ------------------------------------------------------------------
    # Code workspace
    # ------------------------------------------------------------------
    # Verification & Recovery blocks
    # ------------------------------------------------------------------

    def render_verification_block(self, steps: list[dict]) -> RenderableType:
        """Compact verification display:

        Verification
          ✓ tests (1.2s)
          ✓ lint (0.3s)
          ● typecheck...
        """
        sym = self.symbols
        lines: list[RenderableType] = [Text("Verification", style="bold jarvis.info")]
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
            lines.append(Text(f"  {s} {name}{dur}", style=style))
        return Group(*lines)

    def render_recovery_block(self, error: str, attempt: int = 1) -> RenderableType:
        """Recovery display:

        ↻ RECOVERING (attempt 2)
          pytest failed: 2 tests failed in test_auth.py
          Attempting repair...
        """
        sym = self.symbols
        lines: list[RenderableType] = [
            Text(f"{sym['arrow_right']} RECOVERING (attempt {attempt})",
                 style="bold jarvis.warning"),
        ]
        if error:
            preview = error[:200] + ("..." if len(error) > 200 else "")
            lines.append(Text(f"  {preview}", style="jarvis.dim"))
        lines.append(Text("  Attempting repair...", style="jarvis.muted"))
        return Group(*lines)

    # ------------------------------------------------------------------
    # Code workspace
    # ------------------------------------------------------------------

    def render_code_files(self) -> RenderableType:
        if not self.state.code_files:
            return Text("No files", style="jarvis.muted")
        lines = []
        for f in self.state.code_files:
            mark = " ●" if f.modified else ""
            style = "jarvis.active" if f.selected else "jarvis.dim"
            lines.append(Text(f"{f.path}{mark}", style=style))
        return Group(*lines)

    def render_code_buffer(self) -> RenderableType:
        if not self.state.code_content:
            return Text("No file selected", style="jarvis.muted")
        return Syntax(
            self.state.code_content,
            self.state.code_language,
            theme="monokai",
            line_numbers=True,
            word_wrap=False,
        )

    def render_code_header(self) -> Text:
        path = self.state.code_path or "—"
        loc = f"{self.state.code_loc:,} LOC" if self.state.code_loc else ""
        mod = " · MODIFIED" if self.state.code_modified else ""
        return Text.assemble(
            Text("JARVIS", style="bold jarvis.primary"),
            Text(" · CODE · ", style="jarvis.muted"),
            Text(path, style="jarvis.accent"),
            Text(f" · {loc}{mod}" if loc or mod else "", style="jarvis.dim"),
        )

    # ------------------------------------------------------------------
    # Memory workspace
    # ------------------------------------------------------------------

    def render_memory(self) -> RenderableType:
        parts: list[RenderableType] = []
        if self.state.memory_query:
            parts.append(Text("QUERY", style="jarvis.muted"))
            parts.append(Text(self.state.memory_query, style="jarvis.accent"))
            parts.append(Text(""))
        if not self.state.memory_hits:
            parts.append(Text("No memories loaded", style="jarvis.muted"))
            return Group(*parts)
        parts.append(Text("RELEVANT MEMORIES", style="jarvis.muted"))
        for h in self.state.memory_hits:
            parts.append(Text.assemble(
                Text(f"{h.score:.2f}  ", style="jarvis.success"),
                Text(h.title, style="jarvis.user"),
            ))
            parts.append(Text(f"      {h.date}", style="jarvis.dim"))
            if h.snippet:
                parts.append(Text(f"      {h.snippet}", style="jarvis.dim"))
        return Group(*parts)

    # ------------------------------------------------------------------
    # Audit workspace
    # ------------------------------------------------------------------

    def render_audit(self) -> RenderableType:
        if not self.state.audit_sections:
            return Text("No audit data (backend not connected)", style="jarvis.muted")
        blocks: list[RenderableType] = []
        for section in self.state.audit_sections:
            blocks.append(Text(section.title, style="bold jarvis.accent"))
            for status_key, label, detail in section.items:
                sym = self.symbols.get(status_key, "•")
                style = {
                    "done": "jarvis.done",
                    "failed": "jarvis.failed",
                    "running": "jarvis.running",
                    "warning": "jarvis.warning",
                }.get(status_key, "jarvis.dim")
                line = Text.assemble(
                    Text(f"{sym} ", style=style),
                    Text(label, style=style),
                )
                if detail:
                    line = Text.assemble(line, Text(f"  {detail}", style="jarvis.dim"))
                blocks.append(line)
            blocks.append(Text(""))
        return Group(*blocks)

    # ------------------------------------------------------------------
    # Security confirmation (structured, policy-backed)
    # ------------------------------------------------------------------

    def render_confirmation(self) -> RenderableType:
        req = self.state.pending_confirmation
        if not req:
            return Text("")
        risk_style = {
            RiskLevel.LOW: "jarvis.success",
            RiskLevel.MEDIUM: "jarvis.warning",
            RiskLevel.HIGH: "jarvis.error",
            RiskLevel.CRITICAL: "bold jarvis.error",
        }.get(req.risk, "jarvis.warning")
        rev = "YES" if req.reversible else "NO"
        body = Group(
            Text(f"  {self.symbols['failed']} JARVIS wants to execute:", style="jarvis.error"),
            Text(""),
            Text(f"  {req.operation}", style="bold jarvis.accent"),
            Text(""),
            Text.assemble(Text("  Risk:       ", style="jarvis.muted"), Text(req.risk.value.upper(), style=risk_style)),
            Text.assemble(Text("  Scope:      ", style="jarvis.muted"), Text(req.scope)),
            Text.assemble(Text("  Reversible: ", style="jarvis.muted"), Text(rev, style="jarvis.done" if req.reversible else "jarvis.error")),
            Text(""),
            Text("  Allow once?      [y]", style="jarvis.dim"),
            Text("  Allow this run?  [r]", style="jarvis.dim"),
            Text("  Deny             [n]", style="jarvis.dim"),
        )
        return Panel(
            body,
            title=f"[bold jarvis.error] {self.symbols['failed']} SECURITY CONFIRMATION [/]",
            border_style="bright_red",
            box=BoxStyles.CONFIRMATION,
            padding=(1, 2),
        )

    def confirm_interactive(self, req: ConfirmationRequest) -> str:
        """
        Returns: 'once' | 'run' | 'deny'
        Decision is handed back to the security/policy layer.
        """
        self.set_confirmation(req)
        # During a full-screen task run the alternate screen must be suspended
        # while we block on input, then resumed (hybrid UI).
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
        """Give the task display a hook to suspend/resume around blocking I/O."""
        self._live_display = display

    def detach_live(self) -> None:
        self._live_display = None

    # ------------------------------------------------------------------
    # Full-screen task view (hybrid UI) + command palette
    # ------------------------------------------------------------------

    def render_task_screen(self) -> RenderableType:
        """The full-screen view shown while an agent run is live: header status
        bar, conversation (streamed live), and — on wide terminals — the
        activity stream beside it. Reads only ``AppState``; no decisions."""
        header = Panel(
            self.render_status(),
            border_style=COLORS.border_focus,
            box=BoxStyles.HEADER,
            padding=(0, 1),
            height=3,
        )
        conversation = Panel(
            self.render_conversation(),
            title=f"[jarvis.primary]{self.symbols['arrow_right']} JARVIS[/]",
            title_align="left",
            border_style=COLORS.border,
            box=BoxStyles.PANEL,
            padding=(0, 1),
        )
        if self.console.size.width >= 120:
            layout = Layout()
            layout.split_row(
                Layout(conversation, ratio=7),
                Layout(self.render_activity_panel(), ratio=3),
            )
            body = layout
        else:
            body = conversation
        elements: list[RenderableType] = [header, Text(""), body]
        if self.state.pending_confirmation is not None:
            elements += [Text(""), self.render_confirmation()]
        return Group(*elements)

    def render_activity_panel(self) -> RenderableType:
        return Panel(
            self.render_activity(),
            title=f"[jarvis.muted]{self.symbols['arrow_right']} ACTIVITY[/]",
            title_align="left",
            border_style=COLORS.border,
            box=BoxStyles.ACTIVITY,
            padding=(0, 1),
        )

    def render_palette(self, entries: Sequence[tuple[str, str]] | None = None) -> RenderableType:
        """Command palette (Ctrl+K / /palette). ``entries`` are ``(key, help)``
        pairs supplied by the command registry — never invented here."""
        if not entries:
            entries = [
                ("chat", "Conversation (default)"),
                ("plan", "Plan focus"),
                ("code", "Code workspace"),
                ("activity", "Live event stream"),
                ("memory", "Memory workspace"),
                ("audit", "Audit / health"),
            ]
        table = Table(show_header=False, box=None)
        table.add_column(style="bold cyan", width=18)
        table.add_column(style="dim")
        for key, desc in entries:
            table.add_row(key, desc)
        return Panel(
            table,
            title="JARVIS COMMAND PALETTE",
            border_style=COLORS.border,
            box=box.ROUNDED,
        )

    # ------------------------------------------------------------------
    # Layout assembly
    # ------------------------------------------------------------------

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
        self.console.print(Panel(
            self.render_status(),
            border_style=COLORS.border_focus,
            box=BoxStyles.HEADER,
            padding=(0, 1),
            height=3,
        ))

    def print_prompt(self) -> str:
        return f" {self.symbols['prompt']} JARVIS [{self.state.mode.value}]> "

    def clear(self) -> None:
        self.console.clear()

    def print(self, *args: Any, **kwargs: Any) -> None:
        self.console.print(*args, **kwargs)

    def print_error(self, title: str, detail: str = "", fallback: str = "") -> None:
        self.console.print(Text(f"{self.symbols['failed']} {title}", style="jarvis.error"))
        if detail:
            self.console.print(Text(f"  {detail}", style="jarvis.dim"))
        if fallback:
            self.console.print(Text(f"  {fallback}", style="jarvis.warning"))

    def print_success(self, msg: str) -> None:
        self.console.print(Text(f"{self.symbols['done']} {msg}", style="jarvis.success"))
