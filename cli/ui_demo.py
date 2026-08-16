"""JARVIS MK-X terminal UI prototype (visual reference only).

Run ``python -m cli.ui_demo`` to see the mockup-style terminal UI with fake
events. This module is intentionally self-contained and NOT wired into the
real engine: the production path is ``engine → cli/bridge.py → AppState →
Renderer``. Use this file only as a visual target for the real renderer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text


console = Console()


# ============================================================
# THEME
# ============================================================

class Theme:
    BRAND = "cyan"
    AGENT = "cyan"
    USER = "white"

    SUCCESS = "green"
    ERROR = "red"
    WARNING = "yellow"
    INFO = "blue"

    MUTED = "dim"
    BORDER = "bright_black"

    BG = "default"


# ============================================================
# MODE
# ============================================================

class Mode(str, Enum):
    AGENT = "AGENT"
    PLAN = "PLAN"
    CONTROLLED = "CONTROLLED"
    SMART = "SMART"


# ============================================================
# TOOL STATE
# ============================================================

class ToolStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class ToolEvent:
    id: str
    name: str
    detail: str

    status: ToolStatus = ToolStatus.RUNNING

    result: str = ""
    duration: str = ""

    expanded: bool = False


# ============================================================
# PLAN
# ============================================================

class PlanStatus(str, Enum):
    COMPLETE = "complete"
    ACTIVE = "active"
    PENDING = "pending"
    FAILED = "failed"


@dataclass
class PlanStep:
    title: str
    status: PlanStatus


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def current(self) -> Optional[PlanStep]:
        for step in self.steps:
            if step.status == PlanStatus.ACTIVE:
                return step

        return None


# ============================================================
# MESSAGE
# ============================================================

@dataclass
class Message:
    role: str
    content: str


# ============================================================
# APPLICATION STATE
# ============================================================

@dataclass
class AppState:
    mode: Mode = Mode.AGENT

    model: str = "gemini-2.5-pro"
    provider: str = "Google"

    input_tokens: int = 12400
    output_tokens: int = 0
    context_limit: int = 32000

    memory_online: bool = True
    online: bool = True

    messages: list[Message] = field(default_factory=list)
    tools: list[ToolEvent] = field(default_factory=list)

    plan: Plan = field(default_factory=Plan)

    current_workspace: str = "chat"

    confirmation: Optional[str] = None

    streaming: bool = False
    streaming_text: str = ""


# ============================================================
# MAIN UI
# ============================================================

class JarvisTerminalUI:

    def __init__(self):
        self.state = AppState()

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    def render_header(self) -> Text:

        text = Text()

        text.append("JARVIS", style=f"bold {Theme.BRAND}")
        text.append("  ")

        text.append(
            f"[{self.state.mode.value}]",
            style=Theme.AGENT
        )

        text.append("  ")

        text.append(
            self.state.model,
            style="white"
        )

        text.append("  ")

        text.append(
            f"{self.state.input_tokens:,}/{self.state.context_limit:,}",
            style=Theme.MUTED
        )

        text.append("  ")

        active_tools = sum(
            1 for x in self.state.tools
            if x.status == ToolStatus.RUNNING
        )

        if active_tools:
            text.append(
                f"{active_tools} TOOL"
                f"{'S' if active_tools != 1 else ''}",
                style=Theme.WARNING
            )

            text.append("  ")

        if self.state.memory_online:
            text.append("MEMORY", style=Theme.SUCCESS)
            text.append("  ")

        if self.state.online:
            text.append("ONLINE", style=Theme.SUCCESS)
        else:
            text.append("OFFLINE", style=Theme.ERROR)

        return text

    # --------------------------------------------------------
    # User message
    # --------------------------------------------------------

    def render_user(self, message: str) -> Group:

        return Group(
            Text(
                "> " + message,
                style="white"
            ),
            Text("")
        )

    # --------------------------------------------------------
    # Assistant message
    # --------------------------------------------------------

    def render_assistant(self, message: str) -> Group:

        return Group(
            Markdown(message),
            Text("")
        )

    # --------------------------------------------------------
    # Tool event
    # --------------------------------------------------------

    def render_tool(self, tool: ToolEvent) -> Group:

        if tool.status == ToolStatus.RUNNING:
            icon = "●"
            color = Theme.WARNING

        elif tool.status == ToolStatus.SUCCESS:
            icon = "✓"
            color = Theme.SUCCESS

        elif tool.status == ToolStatus.FAILED:
            icon = "✗"
            color = Theme.ERROR

        else:
            icon = "○"
            color = Theme.MUTED

        title = Text()

        title.append(
            f"{icon} ",
            style=f"bold {color}"
        )

        title.append(
            tool.name,
            style="bold white"
        )

        lines = [
            title,
            Text(
                f"  {tool.detail}",
                style=Theme.MUTED
            )
        ]

        if tool.result:

            result_color = (
                Theme.SUCCESS
                if tool.status == ToolStatus.SUCCESS
                else Theme.ERROR
            )

            lines.append(
                Text(
                    f"\n  {tool.result}",
                    style=result_color
                )
            )

        if tool.duration:

            lines.append(
                Text(
                    f"  {tool.duration}",
                    style=Theme.MUTED
                )
            )

        if tool.expanded and tool.result:

            lines.append(
                Panel(
                    Text(tool.result),
                    title="Output",
                    border_style=Theme.BORDER,
                    box=box.ROUNDED
                )
            )

        return Group(*lines, Text(""))

    # --------------------------------------------------------
    # Conversation
    # --------------------------------------------------------

    def render_conversation(self) -> Group:

        output = []

        for message in self.state.messages:

            if message.role == "user":

                output.append(
                    self.render_user(message.content)
                )

            elif message.role == "assistant":

                output.append(
                    self.render_assistant(message.content)
                )

        for tool in self.state.tools:

            output.append(
                self.render_tool(tool)
            )

        if self.state.streaming:

            output.append(
                Markdown(self.state.streaming_text)
            )

        return Group(*output)

    # --------------------------------------------------------
    # Plan
    # --------------------------------------------------------

    def render_plan(self) -> Panel:

        lines = []

        for step in self.state.plan.steps:

            if step.status == PlanStatus.COMPLETE:
                icon = "✓"
                style = Theme.SUCCESS

            elif step.status == PlanStatus.ACTIVE:
                icon = "→"
                style = Theme.AGENT

            elif step.status == PlanStatus.FAILED:
                icon = "✗"
                style = Theme.ERROR

            else:
                icon = "○"
                style = Theme.MUTED

            line = Text()

            line.append(
                f"{icon} ",
                style=f"bold {style}"
            )

            line.append(
                step.title,
                style="white"
                if step.status != PlanStatus.PENDING
                else Theme.MUTED
            )

            lines.append(line)

        return Panel(
            Group(*lines),
            title="PLAN",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )

    # --------------------------------------------------------
    # Activity
    # --------------------------------------------------------

    def render_activity(self) -> Panel:

        table = Table(
            show_header=False,
            box=None,
            padding=(0, 1)
        )

        table.add_column(
            width=2
        )

        table.add_column(
            ratio=1
        )

        for tool in self.state.tools:

            if tool.status == ToolStatus.RUNNING:
                icon = Text("●", style=Theme.WARNING)

            elif tool.status == ToolStatus.SUCCESS:
                icon = Text("✓", style=Theme.SUCCESS)

            elif tool.status == ToolStatus.FAILED:
                icon = Text("✗", style=Theme.ERROR)

            else:
                icon = Text("○", style=Theme.MUTED)

            details = Text()

            details.append(
                tool.name,
                style="bold"
            )

            details.append(
                f"\n  {tool.detail}",
                style=Theme.MUTED
            )

            table.add_row(
                icon,
                details
            )

        return Panel(
            table,
            title="ACTIVITY",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    def render_status(self) -> Panel:

        table = Table(
            show_header=False,
            box=None
        )

        table.add_column(style=Theme.MUTED)
        table.add_column(style="white")

        table.add_row(
            "Mode",
            self.state.mode.value
        )

        table.add_row(
            "Provider",
            self.state.provider
        )

        table.add_row(
            "Model",
            self.state.model
        )

        table.add_row(
            "Context",
            f"{self.state.input_tokens:,}/{self.state.context_limit:,}"
        )

        table.add_row(
            "Memory",
            "ONLINE"
            if self.state.memory_online
            else "OFFLINE"
        )

        table.add_row(
            "Connection",
            "ONLINE"
            if self.state.online
            else "OFFLINE"
        )

        return Panel(
            table,
            title="STATUS",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )

    # --------------------------------------------------------
    # Input
    # --------------------------------------------------------

    def render_input(self) -> Panel:

        prompt = Text()

        prompt.append(
            f"JARVIS [{self.state.mode.value}]> ",
            style=f"bold {Theme.BRAND}"
        )

        prompt.append(
            "_",
            style="white"
        )

        return Panel(
            prompt,
            border_style=Theme.BORDER,
            box=box.ROUNDED,
            padding=(0, 1)
        )

    # --------------------------------------------------------
    # Confirmation
    # --------------------------------------------------------

    def render_confirmation(self) -> Panel:

        return Panel(
            Group(
                Text(
                    "JARVIS wants to execute:",
                    style="bold yellow"
                ),
                Text(""),
                Text(
                    f"  {self.state.confirmation}",
                    style="white"
                ),
                Text(""),
                Text(
                    "Allow? [y/N]",
                    style="bold yellow"
                )
            ),
            title="CONFIRMATION REQUIRED",
            border_style=Theme.WARNING,
            box=box.ROUNDED
        )

    # --------------------------------------------------------
    # Command palette
    # --------------------------------------------------------

    def render_palette(self) -> Panel:

        table = Table(
            show_header=False,
            box=None
        )

        table.add_column(
            style="bold cyan",
            width=16
        )

        table.add_column(
            style="dim"
        )

        commands = [
            ("/plan", "Execution plan"),
            ("/code", "Code viewer"),
            ("/memory", "Memory"),
            ("/audit", "Audit log"),
            ("/status", "System status"),
            ("/activity", "Agent activity"),
            ("/model", "Change model"),
            ("/tools", "Available tools"),
        ]

        for command, description in commands:

            table.add_row(
                command,
                description
            )

        return Panel(
            table,
            title="JARVIS COMMAND PALETTE",
            border_style=Theme.BRAND,
            box=box.ROUNDED
        )

    # --------------------------------------------------------
    # Code viewer
    # --------------------------------------------------------

    def render_code(self) -> Panel:

        code = """def validate_token(token):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"]
        )

        return payload

    except jwt.ExpiredSignatureError:
        return None
"""

        syntax = Syntax(
            code,
            "python",
            line_numbers=True,
            word_wrap=False,
            theme="monokai"
        )

        return Panel(
            syntax,
            title="JARVIS [CODE] · security/auth.py",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )

    # --------------------------------------------------------
    # Memory viewer
    # --------------------------------------------------------

    def render_memory(self) -> Panel:

        table = Table(
            show_header=True,
            box=None
        )

        table.add_column(
            "Memory",
            style="white"
        )

        table.add_column(
            "Age",
            style=Theme.MUTED
        )

        memories = [
            ("Authentication uses JWT", "2m"),
            ("Token expiration bug fixed", "5m"),
            ("Tests: 186 passed", "10m"),
            ("Project uses Python + Rich", "1h"),
            ("Previous auth investigation", "3d"),
        ]

        for memory, age in memories:

            table.add_row(
                memory,
                age
            )

        return Panel(
            table,
            title="JARVIS [MEMORY]",
            border_style=Theme.BORDER,
            box=box.ROUNDED
        )

    # --------------------------------------------------------
    # Main renderer
    # --------------------------------------------------------

    def render(self):

        width = console.size.width

        header = self.render_header()

        # ----------------------------------------------------
        # Special workspaces
        # ----------------------------------------------------

        if self.state.current_workspace == "plan":

            body = self.render_plan()

        elif self.state.current_workspace == "activity":

            body = self.render_activity()

        elif self.state.current_workspace == "status":

            body = self.render_status()

        elif self.state.current_workspace == "code":

            body = self.render_code()

        elif self.state.current_workspace == "memory":

            body = self.render_memory()

        elif self.state.current_workspace == "palette":

            body = self.render_palette()

        else:

            # ------------------------------------------------
            # Normal conversation
            # ------------------------------------------------

            conversation = Panel(
                self.render_conversation(),
                border_style=Theme.BORDER,
                box=box.ROUNDED
            )

            # Wide terminal:
            # conversation + activity
            if width >= 120:

                layout = Layout()

                layout.split_row(
                    Layout(
                        conversation,
                        ratio=7
                    ),
                    Layout(
                        self.render_activity(),
                        ratio=3
                    )
                )

                body = layout

            else:

                body = conversation

        elements = [
            header,
            Text(""),
            body,
            Text(""),
        ]

        if self.state.confirmation:

            elements.append(
                self.render_confirmation()
            )

        elements.append(
            self.render_input()
        )

        return Group(*elements)


# ============================================================
# DEMO
# ============================================================

def demo():

    ui = JarvisTerminalUI()

    ui.state.messages.append(
        Message(
            "user",
            "analyze authentication and fix the failing tests"
        )
    )

    ui.state.messages.append(
        Message(
            "assistant",
            "I'll inspect the authentication implementation "
            "and reproduce the failing tests first."
        )
    )

    ui.state.plan = Plan([
        PlanStep(
            "Understand request",
            PlanStatus.COMPLETE
        ),
        PlanStep(
            "Locate authentication code",
            PlanStatus.COMPLETE
        ),
        PlanStep(
            "Inspect token validation",
            PlanStatus.ACTIVE
        ),
        PlanStep(
            "Run authentication tests",
            PlanStatus.PENDING
        ),
        PlanStep(
            "Fix discovered issues",
            PlanStatus.PENDING
        ),
        PlanStep(
            "Verify changes",
            PlanStatus.PENDING
        ),
    ])

    with Live(
        ui.render(),
        console=console,
        refresh_per_second=12,
        screen=True,
    ):

        # ----------------------------------------------------
        # Search
        # ----------------------------------------------------

        search = ToolEvent(
            id="1",
            name="repo.search",
            detail='rg "authentication|jwt|token"',
            status=ToolStatus.RUNNING
        )

        ui.state.tools.append(search)

        time.sleep(1)

        search.status = ToolStatus.SUCCESS
        search.result = "8 files found"
        search.duration = "0.3s"

        ui.state.plan.steps[2].status = PlanStatus.ACTIVE

        time.sleep(0.7)

        # ----------------------------------------------------
        # Read auth
        # ----------------------------------------------------

        auth = ToolEvent(
            id="2",
            name="filesystem.read",
            detail="security/auth.py",
            status=ToolStatus.SUCCESS,
            result="214 lines",
            duration="0.1s"
        )

        ui.state.tools.append(auth)

        time.sleep(0.5)

        # ----------------------------------------------------
        # Read tests
        # ----------------------------------------------------

        tests = ToolEvent(
            id="3",
            name="filesystem.read",
            detail="tests/test_auth.py",
            status=ToolStatus.SUCCESS,
            result="167 lines",
            duration="0.1s"
        )

        ui.state.tools.append(tests)

        time.sleep(0.5)

        # ----------------------------------------------------
        # Assistant response
        # ----------------------------------------------------

        ui.state.messages.append(
            Message(
                "assistant",
                "The authentication implementation is concentrated "
                "in `security/auth.py`. I'll run the authentication "
                "tests next."
            )
        )

        ui.state.plan.steps[2].status = PlanStatus.COMPLETE
        ui.state.plan.steps[3].status = PlanStatus.ACTIVE

        time.sleep(0.7)

        # ----------------------------------------------------
        # Running tests
        # ----------------------------------------------------

        test = ToolEvent(
            id="4",
            name="shell.execute",
            detail="pytest tests/test_auth.py",
            status=ToolStatus.RUNNING
        )

        ui.state.tools.append(test)

        time.sleep(2)

        test.status = ToolStatus.FAILED
        test.result = "27 passed, 2 failed"
        test.duration = "4.8s"

        ui.state.plan.steps[3].status = PlanStatus.FAILED
        ui.state.plan.steps[4].status = PlanStatus.ACTIVE

        time.sleep(1)

        # ----------------------------------------------------
        # Fix
        # ----------------------------------------------------

        ui.state.messages.append(
            Message(
                "assistant",
                "The failures are related to token expiration "
                "handling. I'll correct the validation path."
            )
        )

        fix = ToolEvent(
            id="5",
            name="filesystem.edit",
            detail="security/auth.py",
            status=ToolStatus.SUCCESS,
            result="1 change applied",
            duration="0.2s"
        )

        ui.state.tools.append(fix)

        time.sleep(1)

        ui.state.plan.steps[4].status = PlanStatus.COMPLETE
        ui.state.plan.steps[5].status = PlanStatus.ACTIVE

        # ----------------------------------------------------
        # Tests again
        # ----------------------------------------------------

        retest = ToolEvent(
            id="6",
            name="shell.execute",
            detail="pytest tests/test_auth.py",
            status=ToolStatus.RUNNING
        )

        ui.state.tools.append(retest)

        time.sleep(2)

        retest.status = ToolStatus.SUCCESS
        retest.result = "29 passed, 2 skipped"
        retest.duration = "4.6s"

        ui.state.plan.steps[5].status = PlanStatus.COMPLETE

        ui.state.messages.append(
            Message(
                "assistant",
                "All authentication tests are now passing."
            )
        )

        time.sleep(2)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    demo()
