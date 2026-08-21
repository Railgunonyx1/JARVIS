"""JARVIS MK-X Layout Manager.

Breakpoints (deterministic, implementation matches docs):
  < 70 cols  → MINIMAL  (conversation only)
  70–119 cols → NORMAL   (plan + conversation)
  ≥ 120 cols → WIDE     (plan + conversation + activity)

Always: status bar + content + input.
Workspaces (Code / Memory / Audit) replace the content area
while preserving the status/input structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from .theme import COLORS, PANEL_TITLES, get_symbols


class LayoutMode(StrEnum):
    NORMAL = "normal"         # plan + conversation (default at 70-119 cols)
    MINIMAL = "minimal"       # conversation only (< 70 cols)
    WIDE = "wide"             # plan + conversation + activity (≥ 120 cols)
    FOCUS = "focus"           # conversation maximized, no plan/activity
    PLAN = "plan"             # force plan + conversation (override breakpoint)
    ACTIVITY = "activity"     # force activity + conversation (override breakpoint)
    CODE = "code"             # code workspace (replaces content)
    MEMORY = "memory"         # memory workspace (replaces content)
    AUDIT = "audit"           # audit workspace (replaces content)


@dataclass
class PanelState:
    name: str
    visible: bool = True
    collapsed: bool = False
    width_ratio: float = 0.22


@dataclass
class LayoutConfig:
    mode: LayoutMode = LayoutMode.NORMAL
    panels: dict[str, PanelState] = field(default_factory=dict)
    show_status_bar: bool = True
    show_input: bool = True

    def __post_init__(self) -> None:
        if not self.panels:
            self.panels = {
                "plan": PanelState("plan", visible=True, width_ratio=0.22),
                "activity": PanelState("activity", visible=True, width_ratio=0.22),
                "code": PanelState("code", visible=False, width_ratio=0.45),
                "memory": PanelState("memory", visible=False, width_ratio=0.30),
                "audit": PanelState("audit", visible=False, width_ratio=0.30),
            }


class LayoutManager:
    """Sole layout authority.  Breakpoints are explicit and deterministic:

    width < 70  → MINIMAL  (conversation only)
    70–119      → NORMAL   (plan + conversation)
    ≥ 120       → WIDE     (plan + conversation + activity)
    """
    WIDE = 120
    NORMAL = 70
    MINIMAL_COLS = 70

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self.config = LayoutConfig()
        self._symbols = get_symbols(True)
        self._force_mode: LayoutMode | None = None

    def set_mode(self, mode: str | LayoutMode) -> None:
        try:
            self._force_mode = LayoutMode(str(mode).lower())
            self.config.mode = self._force_mode
        except ValueError:
            pass

    def clear_force(self) -> None:
        self._force_mode = None

    def toggle_panel(self, name: str) -> bool:
        panel = self.config.panels.get(name)
        if panel is None:
            return False
        panel.visible = not panel.visible
        return panel.visible

    def detect_mode(self) -> LayoutMode:
        """Deterministic breakpoint detection. No ambiguity."""
        if self._force_mode is not None:
            return self._force_mode
        width = self.console.size.width
        height = self.console.size.height
        if width < self.MINIMAL_COLS or height < 16:
            return LayoutMode.MINIMAL
        if width >= self.WIDE:
            return LayoutMode.WIDE
        return LayoutMode.NORMAL

    def build(
        self,
        conversation: RenderableType,
        plan: RenderableType | None = None,
        activity: RenderableType | None = None,
        code: RenderableType | None = None,
        memory: RenderableType | None = None,
        audit: RenderableType | None = None,
        status: RenderableType | None = None,
        verification: RenderableType | None = None,
        recovery: RenderableType | None = None,
    ) -> Layout:
        """Sole composition authority.  All rendering decisions live here.

        Breakpoints (deterministic):
          < 70 cols  → MINIMAL  (conversation only)
          70–119     → NORMAL   (plan + conversation)
          ≥ 120      → WIDE     (plan + conversation + activity)
        """
        mode = self.detect_mode()
        width = self.console.size.width
        root = Layout(name="root")

        # Workspaces replace content area while preserving structure
        workspace_content = None
        if mode == LayoutMode.CODE and code is not None:
            workspace_content = code
        elif mode == LayoutMode.MEMORY and memory is not None:
            workspace_content = memory
        elif mode == LayoutMode.AUDIT and audit is not None:
            workspace_content = audit

        if workspace_content is not None:
            # Workspaces replace the content area but preserve the root structure
            # (status + content + input pattern). The status bar and input prompt
            # are rendered by the caller (render_task_screen) outside this layout.
            root.split_column(Layout(workspace_content, name="workspace"))
            return root

        if mode == LayoutMode.MINIMAL:
            root.split_column(Layout(conversation, name="conversation"))
            return root

        # FOCUS: conversation maximized, no side panels
        if mode == LayoutMode.FOCUS:
            root.split_column(Layout(conversation, name="conversation", ratio=1))
            return root

        # PLAN mode: force plan visible even below 120 cols
        show_plan = (
            self.config.panels["plan"].visible
            and plan is not None
        )
        if mode == LayoutMode.PLAN and plan is not None:
            show_plan = True

        # Activity visible in WIDE and ACTIVITY modes
        show_activity = (
            mode in (LayoutMode.WIDE, LayoutMode.ACTIVITY)
            and self.config.panels["activity"].visible
            and activity is not None
        )

        parts: list[Layout] = []
        if show_plan:
            left = Layout(name="plan", size=max(20, int(width * 0.20)))
            left.update(self._wrap("plan", plan))
            parts.append(left)

        parts.append(Layout(conversation, name="conversation", ratio=1))

        if show_activity:
            right = Layout(name="activity", size=max(22, int(width * 0.22)))
            right.update(self._wrap("activity", activity))
            parts.append(right)

        if len(parts) == 1:
            root.split_column(parts[0])
        else:
            main = Layout(name="main")
            main.split_row(*parts)
            root.split_column(main)
        return root

    def _wrap(self, name: str, content: RenderableType) -> Panel:
        title = PANEL_TITLES.get(name, name.upper())
        return Panel(
            content,
            title=title,
            title_align="left",
            border_style=COLORS.border,
            padding=(0, 1),
            expand=True,
        )

    def status_line(
        self,
        mode: str = "AGENT",
        model: str = "—",
        tokens: str = "—",
        tools: int = 0,
        memory_on: bool = False,
        time_str: str = "",
        connection: str = "ONLINE",
    ) -> Text:
        """Kept for compatibility; prefer Renderer.render_status()."""
        sep = self._symbols["separator"]
        parts = [
            Text("JARVIS", style="bold jarvis.primary"),
            Text(f" {sep} ", style="jarvis.muted"),
            Text(mode.upper(), style="jarvis.accent"),
            Text(f" {sep} ", style="jarvis.muted"),
            Text(model, style="jarvis.secondary"),
            Text(f" {sep} ", style="jarvis.muted"),
            Text(tokens, style="jarvis.dim"),
        ]
        if tools:
            parts += [Text(f" {sep} ", style="jarvis.muted"), Text(f"{tools} TOOLS", style="jarvis.dim")]
        if memory_on:
            parts += [Text(f" {sep} ", style="jarvis.muted"), Text("MEMORY", style="jarvis.success")]
        parts += [
            Text(f" {sep} ", style="jarvis.muted"),
            Text(connection, style="jarvis.success" if connection == "ONLINE" else "jarvis.warning"),
        ]
        if time_str:
            parts += [Text(f" {sep} ", style="jarvis.muted"), Text(time_str, style="jarvis.dim")]
        return Text.assemble(*parts)
