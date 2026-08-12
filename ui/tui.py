"""
JARVIS terminal dashboard — Textual implementation (512-MB UI roadmap item).

Adapted from the reference implementation in ``files.zip`` (external
``ipc/`` transport discarded): the app is a *client* of JARVIS's existing
daemon (``daemon/client.py`` + ``daemon/lifecycle.py``). Design rules from
the reference are kept: white/black engineering-console theme with green
reserved for active/healthy status only, and a single data seam
(``ui.backend.TuiDataSource``) so the UI never touches sockets directly.

Data sources:
    live (psuit)          CPU / RAM / disk / uptime
    live (daemon)          provider health + status  (when daemon is up)
    mock (marked)          task list, token sparkline  (daemon has no
                            task/token endpoints yet — roadmap follow-up)

Run ``pip install textual`` once, then ``python -m ui.tui`` or
``jarvis tui``.
"""

from __future__ import annotations

import asyncio
import datetime

from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import (
    DataTable,
    Input,
    Label,
    ListItem,
    ListView,
    Log,
    ProgressBar,
    Select,
    Sparkline,
    Static,
)

from ui.backend import TuiDataSource


def _fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


SIDEBAR_ITEMS = [
    "DASHBOARD", "CONVERSATIONS", "TASKS", "MEMORY", "TOOLS", "PROVIDERS",
    "SETTINGS", "PERFORMANCE", "LOGS", "DOCUMENTS", "RESEARCH", "SKILLS",
    "AGENTS", "PLUGINS", "EXIT",
]


# ------------------------------------------------------------------- widgets

class TopBar(Horizontal):
    MODES = [("PLAN", "plan"), ("CONTROLLED", "controlled"),
             ("SMART", "smart"), ("AGENT", "agent")]

    def compose(self) -> ComposeResult:
        yield Static("JARVIS TERMINAL", id="topbar-title")
        yield Static("SYSTEM DASHBOARD", id="topbar-center")
        yield Select(self.MODES, value="smart", allow_blank=False,
                     prompt="MODE", compact=True, id="mode-select")
        yield Static(self._now(), id="topbar-clock")

    def _now(self) -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        self.query_one("#topbar-clock", Static).update(self._now())

    def sync_mode(self, mode: str) -> None:
        """Sync the selector with the daemon's current mode (no-op if blank)."""
        if not mode:
            return
        self.query_one("#mode-select", Select).value = mode

    def set_daemon_state(self, connected: bool) -> None:
        self.query_one("#mode-select", Select).disabled = not connected

    async def on_select_changed(self, event: Select.Changed) -> None:
        mode = str(event.value)
        # Skip offline and programmatic-sync echoes (mount/refresh set the
        # value too, which also fires Changed).
        if not self.app.data_source.connected:
            return
        if self.app.data_source.status.get("mode") == mode:
            return
        logs = self.app.query_one(LogsPanel)
        result = await self.app.data_source.set_mode(mode)
        if result.get("success"):
            logs.write(f"mode set to {result.get('mode')}")
        else:
            logs.write(f"mode change failed: {result.get('error')}")
            current = self.app.data_source.status.get("mode", "smart")
            self.query_one("#mode-select", Select).value = current


class Sidebar(Vertical):
    def compose(self) -> ComposeResult:
        yield ListView(
            *[ListItem(Label(name)) for name in SIDEBAR_ITEMS],
            id="sidebar-list",
        )
        yield Static("DAEMON STATUS\n\nconnecting…", id="daemon-box")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._update_daemon_box)

    def _update_daemon_box(self) -> None:
        data = self.app.data_source
        if data.connected:
            status = data.status
            line = "[b]\u25cf[/b] [#1DB954]DAEMON CONNECTED[/#1DB954]"
            pid = status.get("pid", "-")
            uptime = _fmt_uptime(float(status.get("uptime", 0.0)))
        else:
            line = "[b]\u25cf[/b] [#B00020]DAEMON OFFLINE[/#B00020] (mock data)"
            pid = "-"
            uptime = "-"
        self.query_one("#daemon-box", Static).update(
            "DAEMON STATUS\n\n"
            f"{line}\n\n"
            f"PID: {pid}\n"
            f"UPTIME: {uptime}\n"
            f"MODE: {data.status.get('mode', '-')}"
        )


class Panel(Vertical):
    """Bordered panel with a title label — the basic unit of the dashboard."""

    def __init__(self, title: str, panel_id: str, **kwargs):
        super().__init__(id=panel_id, classes="panel", **kwargs)
        self._title = title

    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="panel-title")


class SystemOverviewPanel(Panel):
    def __init__(self):
        super().__init__("SYSTEM OVERVIEW", "panel-overview")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Label("CPU USAGE", id="ov-cpu-label")
        yield ProgressBar(total=100, id="ov-cpu-bar", show_eta=False)
        yield Label("MEMORY USAGE", id="ov-ram-label")
        yield ProgressBar(total=100, id="ov-ram-bar", show_eta=False)
        yield Label("DISK USAGE", id="ov-disk-label")
        yield ProgressBar(total=100, id="ov-disk-bar", show_eta=False)
        yield Static("", id="ov-details")

    def update_snapshot(self, snap: dict):
        self.query_one("#ov-cpu-bar", ProgressBar).update(progress=snap["cpu_percent"])
        self.query_one("#ov-ram-bar", ProgressBar).update(progress=snap["ram_percent"])
        disk_pct = (snap["disk_used_gb"] / snap["disk_total_gb"] * 100) \
            if snap["disk_total_gb"] else 0
        self.query_one("#ov-disk-bar", ProgressBar).update(progress=disk_pct)
        self.query_one("#ov-details", Static).update(
            f"MEMORY   {snap['ram_used_gb']:.0f} MB / {snap['ram_total_gb']:.0f} GB\n"
            f"DISK     {snap['disk_used_gb']:.0f} GB / {snap['disk_total_gb']:.0f} GB\n"
            f"ACTIVE TASKS   {snap['active_tasks']}\n"
            f"UPTIME   {_fmt_uptime(snap['uptime_s'])}\n"
            f"JARVIS VERSION   0.1.0"
        )


class SparklinePanel(Panel):
    def __init__(self, title: str, panel_id: str, spark_id: str, show_token_usage: bool = False):
        super().__init__(title, panel_id)
        self._spark_id = spark_id
        self._show_token_usage = show_token_usage

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Sparkline([0] * 60, id=self._spark_id)
        if self._show_token_usage:
            yield Static("0 tokens", id=f"token-count-{self._spark_id}", classes="token-count")

    def update_data(self, data: list[float], token_count: int = 0, token_total: int = 0):
        self.query_one(f"#{self._spark_id}", Sparkline).data = data
        if self._show_token_usage:
            count_widget = self.query_one(f"token-count-{self._spark_id}", Static)
            if token_total > 0:
                count_widget.update(f"{token_count} / {token_total} tokens ({token_count/token_total*100:.0f}%)")
            else:
                count_widget.update(f"{token_count} tokens")


class ProvidersPanel(Panel):
    def __init__(self):
        super().__init__("PROVIDER STATUS", "panel-providers")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield DataTable(id="providers-table")

    def on_mount(self):
        table = self.query_one("#providers-table", DataTable)
        table.add_columns("PROVIDER", "STATUS", "LATENCY", "RATE LIMIT", "MODEL")
        table.cursor_type = "row"

    def update_data(self, rows):
        table = self.query_one("#providers-table", DataTable)
        table.clear()
        for name, status, latency, rate, model in rows:
            status_markup = f"[#1DB954]{status}[/#1DB954]" \
                if status == "ONLINE" else f"[#B00020]{status}[/#B00020]"
            table.add_row(name, status_markup, latency, rate, model)


class TasksPanel(Panel):
    def __init__(self):
        super().__init__("ACTIVE TASKS", "panel-tasks")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield DataTable(id="tasks-table")

    def on_mount(self):
        table = self.query_one("#tasks-table", DataTable)
        table.add_columns("ID", "TASK", "STATUS", "PROGRESS", "TIME LEFT")
        table.cursor_type = "row"

    def update_data(self, rows):
        table = self.query_one("#tasks-table", DataTable)
        table.clear()
        for task_id, name, status, progress, time_left in rows:
            status_markup = f"[#1DB954]{status}[/#1DB954]" \
                if status == "RUNNING" else f"[dim]{status}[/dim]"
            bar = "\u2588" * (progress // 10) + "\u2591" * (10 - progress // 10)
            progress_cell = f"[#1DB954]{bar}[/#1DB954] {progress}%" if progress else "-"
            table.add_row(task_id, name, status_markup, progress_cell, time_left)


class AgentPlanPanel(Panel):
    """Agent plan steps with completion states (mock until the daemon
    exposes a plan endpoint)."""

    def __init__(self):
        super().__init__("AGENT PLAN", "panel-plan")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield DataTable(id="plan-table")

    def on_mount(self):
        table = self.query_one("#plan-table", DataTable)
        table.add_columns("#", "STEP", "STATUS")
        table.cursor_type = "row"

    def update_data(self, rows):
        table = self.query_one("#plan-table", DataTable)
        table.clear()
        done = sum(1 for _, _, state in rows if state == "DONE")
        for num, step, state in rows:
            state_markup = "[#1DB954]DONE[/#1DB954]" \
                if state == "DONE" else "[dim]PENDING[/dim]"
            table.add_row(num, step, state_markup)
        self.query_one(".panel-title", Static).update(f"AGENT PLAN ({done}/{len(rows)})")


class SkillsPanel(Panel):
    """Live skill registry from the daemon (mock when offline)."""

    def __init__(self):
        super().__init__("SKILL REGISTRY", "panel-skills")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield DataTable(id="skills-table")

    def on_mount(self):
        table = self.query_one("#skills-table", DataTable)
        table.add_columns("SKILL", "VERSION", "STATUS")
        table.cursor_type = "row"

    def update_data(self, rows):
        table = self.query_one("#skills-table", DataTable)
        table.clear()
        for name, version, status in rows:
            status_markup = "[#1DB954]READY[/#1DB954]" \
                if status == "READY" else "[dim]LOCKED[/dim]"
            table.add_row(name, version, status_markup)


class LogsPanel(Panel):
    _TAG_STYLES = {
        "tool": "[#1DB954][TOOL][/#1DB954]",
        "ok": "[#1DB954][OK][/#1DB954]",
        "memory": "[b][MEMORY][/b]",
        "gate": "[dim][GATE][/dim]",
        "task": "[b][TASK][/b]",
        "info": "[INFO]",
    }

    def __init__(self):
        super().__init__("SYSTEM LOGS", "panel-logs")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Log(id="logs-view", auto_scroll=True)

    def write(self, message: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.query_one("#logs-view", Log).write_line(f"[{ts}] | {message}")

    def write_event(self, event_name: str):
        """Write a daemon observer event as a tagged activity-stream line."""
        name = event_name.lower()
        if "memory" in name:
            tag = "memory"
        elif "tool" in name or "step" in name:
            tag = "tool"
        elif "permission" in name:
            tag = "gate"
        elif "task" in name:
            tag = "task"
        elif "completed" in name or name.endswith("ok") or "passed" in name:
            tag = "ok"
        else:
            tag = "info"
        self.write(f"{self._TAG_STYLES[tag]} {event_name}")

    def clear(self):
        self.query_one("#logs-view", Log).clear()


class TodoPanel(Panel):
    """Panel showing a todo list with toggleable border."""

    def __init__(self):
        super().__init__("TODO LIST (Ctrl+T)", "panel-todo")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Static(
            "[ ] Buy groceries\n"
            "[ ] Fix bug #123\n"
            "[ ] Update documentation\n"
            "[ ] Deploy to production\n"
            "[ ] Test new feature\n"
            "[ ] Review PR #42\n"
            "[ ] Write tests\n"
            "[ ] Optimize performance\n"
            "[ ] Refactor module X\n"
            "[ ] Archive old data",
            id="todo-list",
        )


class ContextPanel(Panel):
    """Panel showing LLM conversation context with toggleable border."""

    def __init__(self):
        super().__init__("CONTEXT (Ctrl+C)", "panel-context")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Static(
            "No active context\n"
            "Start a conversation or load a session to see context here.",
            id="context-display",
            classes="context-display",
        )


class CommandBar(Horizontal):
    def compose(self) -> ComposeResult:
        yield Static("jarvis>", id="command-prompt")
        yield Input(placeholder="Type your command...", id="command-input")


# ---------------------------------------------------------------------- app

class JarvisApp(App):
    CSS_PATH = "jarvis_tui.tcss"
    TITLE = "JARVIS Terminal"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "toggle_todo", "Toggle todo"),
        ("ctrl+t", "toggle_todo", "Toggle todo"),
        ("c", "toggle_context", "Toggle context"),
        ("ctrl+c", "toggle_context", "Toggle context"),
    ]

    def __init__(self, data_source: TuiDataSource | None = None,
                 mock: bool = False, url: str | None = None):
        super().__init__()
        self._data = data_source or TuiDataSource(mock=mock, url=url)
        self._todo_collapsed = False
        self._context_collapsed = False

    @property
    def data_source(self) -> TuiDataSource:
        return self._data

    def compose(self) -> ComposeResult:
        yield TopBar(id="topbar")
        with Horizontal():
            yield Sidebar(id="sidebar")
            with Grid(id="dashboard-grid"):
                yield SystemOverviewPanel()
                yield SparklinePanel("CPU USAGE", "panel-cpu", "cpu-spark")
                yield ProvidersPanel()
                yield SparklinePanel("TOKEN USAGE", "panel-tokens", "token-spark", show_token_usage=True)
                yield TasksPanel()
                yield LogsPanel()
                yield TodoPanel()
                yield ContextPanel()
                yield SparklinePanel("MEMORY USAGE", "panel-mem", "mem-spark")
                yield AgentPlanPanel()
                yield SkillsPanel()
        yield CommandBar(id="command-bar")

    def toggle_todo(self) -> None:
        self._todo_collapsed = not self._todo_collapsed
        todo_panel = self.query_one("#panel-todo", Panel)
        if self._todo_collapsed:
            todo_panel.add_class("panel-collapsed")
            todo_panel.remove_class("panel-expanded")
            todo_panel.query_one("#todo-list").display = False
        else:
            todo_panel.add_class("panel-expanded")
            todo_panel.remove_class("panel-collapsed")
            todo_panel.query_one("#todo-list").display = True

    def toggle_context(self) -> None:
        self._context_collapsed = not self._context_collapsed
        context_panel = self.query_one("#panel-context", Panel)
        if self._context_collapsed:
            context_panel.add_class("panel-collapsed")
            context_panel.remove_class("panel-expanded")
            context_panel.query_one("#context-display").display = False
        else:
            context_panel.add_class("panel-expanded")
            context_panel.remove_class("panel-collapsed")
            context_panel.query_one("#context-display").display = True

    def on_mount(self) -> None:
        logs = self.query_one(LogsPanel)
        logs.write("Dashboard started")
        self.query_one(TasksPanel).update_data(self._data.task_rows)
        if self._data.using_mock_tasks:
            logs.write("tasks: mock data (no task endpoint on the daemon yet)")
        self.query_one(AgentPlanPanel).update_data(self._data.plan_rows)
        if self._data.using_mock_plan:
            logs.write("agent plan: mock data (no plan endpoint on the daemon yet)")
        self.query_one(SkillsPanel).update_data(self._data.skill_rows)
        if self._data.using_mock_skills:
            logs.write("skills: mock data (daemon offline — start with `jarvis daemon start`)")
        self.query_one(TopBar).set_daemon_state(self._data.connected)
        self.set_interval(20.0, self._refresh)
        self.set_interval(5.0, self._reconnect)
        self.set_interval(30.0, self._refresh_live)
        asyncio.create_task(self._connect())
        self.query_one("#command-input", Input).focus()

    async def _connect(self) -> None:
        logs = self.query_one(LogsPanel)
        await self._data.connect()
        if self._data.connected:
            logs.write("daemon connected")
            await self._refresh_live()
        else:
            logs.write(f"daemon offline: {self._data.last_error} — showing mock data")
            logs.write("start it in another terminal with `jarvis daemon start`")
        self.query_one(TopBar).set_daemon_state(self._data.connected)
        self.query_one(TopBar).sync_mode(self._data.status.get("mode", ""))

    async def _reconnect(self) -> None:
        if self._data.connected:
            return
        logs = self.query_one(LogsPanel)
        await self._data.try_reconnect()
        if self._data.connected:
            logs.write("daemon connected")
            await self._refresh_live()
        self.query_one(TopBar).set_daemon_state(self._data.connected)
        self.query_one(TopBar).sync_mode(self._data.status.get("mode", ""))

    async def _refresh_live(self) -> None:
        await self._data.refresh()
        self.query_one(ProvidersPanel).update_data(self._data.provider_rows)
        if self._data.using_mock_providers:
            logs = self.query_one(LogsPanel)
            logs.write("providers: mock data (no keys configured on the daemon)")
        self.query_one(SkillsPanel).update_data(self._data.skill_rows)
        if self._data.using_mock_skills:
            logs = self.query_one(LogsPanel)
            logs.write("skills: mock data (daemon offline — start with `jarvis daemon start`)")
        self.query_one(TopBar).sync_mode(self._data.status.get("mode", ""))

    def _refresh(self) -> None:
        snap = self._data.snapshot()
        self.query_one(SystemOverviewPanel).update_snapshot(snap)
        self.query_one("#cpu-spark", Sparkline).data = self._data.cpu_history
        self.query_one("#mem-spark", Sparkline).data = self._data.ram_history
        token_data = self._data.token_history()
        token_used, token_total = self._data.token_usage()
        self.query_one("#token-spark", Sparkline).data = token_data
        self.query_one("#panel-tokens", SparklinePanel).update_data(
            token_data, token_count=token_used, token_total=token_total,
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        event.input.value = ""
        if not command:
            return
        self.query_one(LogsPanel).write(f"> {command}")
        asyncio.create_task(self._run_command(command))

    async def _run_command(self, command: str) -> None:
        logs = self.query_one(LogsPanel)
        if command.startswith("/"):
            await self._run_slash(command)
            return
        if not self._data.connected:
            logs.write("not sent — daemon offline (start with `jarvis daemon start`)")
            return

        def _on_event(name: str, payload: dict) -> None:
            logs.write_event(name)

        result = await self._data.run_goal(command, on_event=_on_event)
        if result.get("success"):
            trace = result.get("trace_id", "")
            logs.write(f"  done \u2713 {('(' + trace + ')') if trace else ''}")
        else:
            logs.write(f"  failed: {result.get('error', 'unknown error')}")

    async def _run_slash(self, command: str) -> None:
        logs = self.query_one(LogsPanel)
        parts = command.split(maxsplit=1)
        cmd, arg = parts[0].lower(), parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/help":
            for line in (
                "commands:",
                "  /help            show this help",
                "  /mode [name]     show or set mode (plan/controlled/smart/agent)",
                "  /status          show daemon status",
                "  /models          show provider model status",
                "  /memory <query>  search daemon memory",
                "  /skills [q]      discover skills in the registry",
                "  /reconnect       reconnect to the daemon",
                "  /clear           clear the log",
                "  /exit            quit the dashboard",
            ):
                logs.write(line)
            return

        if cmd == "/clear":
            logs.clear()
            return

        if cmd == "/exit":
            self.exit()
            return

        if cmd == "/reconnect":
            await self._data.try_reconnect()
            if self._data.connected:
                logs.write("daemon reconnected")
                await self._refresh_live()
            else:
                logs.write(f"daemon still offline: {self._data.last_error}")
            self.query_one(TopBar).set_daemon_state(self._data.connected)
            self.query_one(TopBar).sync_mode(self._data.status.get("mode", ""))
            return

        if not self._data.connected:
            logs.write("not sent — daemon offline (start with `jarvis daemon start`)")
            return

        if cmd == "/status":
            status = self._data.status
            logs.write(
                f"pid={status.get('pid', '-')} mode={status.get('mode', '-')} "
                f"port={status.get('port', '-')} provider={status.get('provider', '-')}"
            )
            logs.write(
                f"model={status.get('model', '-')} tools={status.get('tools', '-')} "
                f"busy={status.get('busy', '-')} last_goal={status.get('last_goal', '-')!r}"
            )
            return

        if cmd == "/models":
            models = self._data.models
            if not models:
                logs.write("no models configured")
                return
            for name in sorted(models):
                info = models[name] or {}
                online = bool(info.get("available")) and bool(info.get("package_ok", True))
                color = "#1DB954" if online else "#B00020"
                logs.write(
                    f"[{color}]{'ONLINE' if online else 'OFFLINE'}[/{color}] "
                    f"{name.upper()} -> {info.get('model', 'unknown')}"
                )
            return

        if cmd == "/mode":
            if not arg:
                logs.write(f"current mode: {self._data.status.get('mode', '-')}")
                return
            result = await self._data.set_mode(arg)
            if result.get("success"):
                logs.write(f"mode set to {result.get('mode')}")
            else:
                logs.write(f"mode change failed: {result.get('error')}")
            self.query_one(TopBar).sync_mode(self._data.status.get("mode", ""))
            self.query_one(SkillsPanel).update_data(self._data.skill_rows)
            return

        if cmd == "/memory":
            if not arg:
                logs.write("usage: /memory <query>")
                return
            hits = await self._data.memory_search(arg)
            if not hits:
                logs.write(f"no memory hits for {arg!r}")
                return
            for hit in hits:
                logs.write(f"  {hit}")
            return

        if cmd == "/skills":
            result = await self._data.search_skills(arg)
            if not result.get("skills"):
                if arg:
                    logs.write(f"no skill hits for {arg!r}")
                else:
                    logs.write("skills: daemon offline (start with `jarvis daemon start`)")
                return
            logs.write(f"skills: {result.get('total')} of {result.get('catalog')} "
                       f"matched ({arg!r})")
            for skill in result.get("skills", []):
                logs.write(
                    f"  {skill.get('name')} v{skill.get('version')} "
                    f"[risk {skill.get('max_risk')}]"
                )
            return

        logs.write(f"unknown command: {cmd} (try /help)")


if __name__ == "__main__":
    JarvisApp().run()
