"""
JARVIS MK-X Layout Manager

Locked responsive rules:
  Always: status bar + content + input
  ≥ 90 cols : PLAN + CONVERSATION
  ≥ 120 cols: PLAN + CONVERSATION + ACTIVITY
  < 70 cols : CONVERSATION only

Workspaces (Code / Memory / Audit) are on-demand and replace
the content area; they do not permanently pollute the agent view.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from .theme import COLORS, PANEL_TITLES, get_symbols


class LayoutMode(str, Enum):
    MINIMAL = "minimal"       # conversation only
    NORMAL = "normal"         # plan + conversation (+ activity if wide)
    FOCUS = "focus"           # conversation maximized
    PLAN = "plan"             # force plan + conversation
    ACTIVITY = "activity"     # force activity + conversation
    CODE = "code"             # code workspace
    MEMORY = "memory"         # memory workspace
    AUDIT = "audit"           # audit workspace


@dataclass
class PanelState:
    name: str
    visible: bool = True
    collapsed: bool = False
    width_ratio: float = 0.22


@dataclass
class LayoutConfig:
    mode: LayoutMode = LayoutMode.NORMAL
    panels: Dict[str, PanelState] = field(default_factory=dict)
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
    LARGE = 120
    MEDIUM = 90
    SMALL = 70

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()
        self.config = LayoutConfig()
        self._symbols = get_symbols(True)
        self._force_mode: Optional[LayoutMode] = None

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
        if self._force_mode is not None:
            return self._force_mode
        width = self.console.size.width
        height = self.console.size.height
        if width < self.SMALL or height < 16:
            return LayoutMode.MINIMAL
        if width < self.MEDIUM:
            return LayoutMode.PLAN if self.config.panels["plan"].visible else LayoutMode.FOCUS
        return LayoutMode.NORMAL

    def build(
        self,
        conversation: RenderableType,
        plan: Optional[RenderableType] = None,
        activity: Optional[RenderableType] = None,
        code: Optional[RenderableType] = None,
        memory: Optional[RenderableType] = None,
        audit: Optional[RenderableType] = None,
        status: Optional[RenderableType] = None,
    ) -> Layout:
        mode = self.detect_mode()
        width = self.console.size.width
        root = Layout(name="root")

        # Workspaces replace content area
        if mode == LayoutMode.CODE and code is not None:
            root.split_column(Layout(code, name="code"))
            return root
        if mode == LayoutMode.MEMORY and memory is not None:
            root.split_column(Layout(memory, name="memory"))
            return root
        if mode == LayoutMode.AUDIT and audit is not None:
            root.split_column(Layout(audit, name="audit"))
            return root

        if mode == LayoutMode.MINIMAL:
            root.split_column(Layout(conversation, name="conversation"))
            return root

        show_plan = (
            mode in (LayoutMode.PLAN, LayoutMode.NORMAL, LayoutMode.ACTIVITY)
            and self.config.panels["plan"].visible
            and plan is not None
        )
        show_activity = (
            (mode == LayoutMode.ACTIVITY or (mode == LayoutMode.NORMAL and width >= self.LARGE))
            and self.config.panels["activity"].visible
            and activity is not None
        )

        parts: List[Layout] = []
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
            title=f"[jarvis.muted]{title}[/]",
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
