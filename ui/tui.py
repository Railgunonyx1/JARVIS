"""
JARVIS terminal dashboard — Textual implementation (512-MB UI roadmap item).

Adapted from the reference implementation in ``files.zip`` (external
``ipc/`` transport discarded): the app is a *client* of JARVIS's existing
daemon (``daemon/client.py`` + ``daemon/lifecycle.py``). Design rules from
the reference are kept: white/black engineering-console theme with green
reserved for active/healthy status only, and a single data seam
(``ui.backend.TuiDataSource``) so the UI never touches sockets directly.

Data sources:
    live (psutil)          CPU / RAM / disk / uptime
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
    def compose(self) -> ComposeResult:
        yield Static("JARVIS TERMINAL", id="topbar-title")
        yield Static("SYSTEM DASHBOARD", id="topbar-center")
        yield Static(self._now(), id="topbar-clock")

    def _now(self) -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        self.query_one("#topbar-clock", Static).update(self._now())


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
            line = "[b]\u25cf[/b] [green]DAEMON CONNECTED[/green]"
            pid = status.get("pid", "-")
            uptime = _fmt_uptime(float(status.get("uptime", 0.0)))
        else:
            line = "[b]\u25cf[/b] [red]DAEMON OFFLINE[/red] (mock data)"
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
    def __init__(self, title: str, panel_id: str, spark_id: str):
        super().__init__(title, panel_id)
        self._spark_id = spark_id

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Sparkline([0] * 60, id=self._spark_id)

    def update_data(self, data: list[float]):
        self.query_one(f"#{self._spark_id}", Sparkline).data = data


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
            status_markup = f"[green]{status}[/green]" \
                if status == "ONLINE" else f"[red]{status}[/red]"
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
            status_markup = f"[green]{status}[/green]" \
                if status == "RUNNING" else f"[dim]{status}[/dim]"
            bar = "\u2588" * (progress // 10) + "\u2591" * (10 - progress // 10)
            progress_cell = f"[green]{bar}[/green] {progress}%" if progress else "-"
            table.add_row(task_id, name, status_markup, progress_cell, time_left)


class LogsPanel(Panel):
    def __init__(self):
        super().__init__("SYSTEM LOGS", "panel-logs")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Log(id="logs-view", auto_scroll=True)

    def write(self, message: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.query_one("#logs-view", Log).write_line(f"[{ts}] | {message}")


class CommandBar(Horizontal):
    def compose(self) -> ComposeResult:
        yield Static("jarvis>", id="command-prompt")
        yield Input(placeholder="Type your command...", id="command-input")


# ---------------------------------------------------------------------- app

class JarvisApp(App):
    CSS_PATH = "jarvis_tui.tcss"
    TITLE = "JARVIS Terminal"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, data_source: TuiDataSource | None = None,
                 mock: bool = False, url: str | None = None):
        super().__init__()
        self._data = data_source or TuiDataSource(mock=mock, url=url)

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
                yield SparklinePanel("MEMORY USAGE", "panel-mem", "mem-spark")
                yield ProvidersPanel()
                yield TasksPanel()
                yield LogsPanel()
                yield SparklinePanel("TOKEN USAGE", "panel-tokens", "token-spark")
        yield CommandBar(id="command-bar")

    def on_mount(self) -> None:
        logs = self.query_one(LogsPanel)
        logs.write("Dashboard started")
        self.query_one(TasksPanel).update_data(self._data.task_rows)
        if self._data.using_mock_tasks:
            logs.write("tasks: mock data (no task endpoint on the daemon yet)")
        self.set_interval(1.0, self._refresh)
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

    async def _reconnect(self) -> None:
        if self._data.connected:
            return
        logs = self.query_one(LogsPanel)
        await self._data.try_reconnect()
        if self._data.connected:
            logs.write("daemon connected")
            await self._refresh_live()

    async def _refresh_live(self) -> None:
        await self._data.refresh()
        self.query_one(ProvidersPanel).update_data(self._data.provider_rows)
        if self._data.using_mock_providers:
            logs = self.query_one(LogsPanel)
            logs.write("providers: mock data (no keys configured on the daemon)")

    def _refresh(self) -> None:
        snap = self._data.snapshot()
        self.query_one(SystemOverviewPanel).update_snapshot(snap)
        self.query_one("#cpu-spark", Sparkline).data = self._data.cpu_history
        self.query_one("#mem-spark", Sparkline).data = self._data.ram_history
        self.query_one("#token-spark", Sparkline).data = self._data.token_history()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        event.input.value = ""
        if not command:
            return
        self.query_one(LogsPanel).write(f"> {command}")
        asyncio.create_task(self._run_command(command))

    async def _run_command(self, command: str) -> None:
        logs = self.query_one(LogsPanel)
        if not self._data.connected:
            logs.write("not sent — daemon offline (start with `jarvis daemon start`)")
            return

        def _on_event(name: str, payload: dict) -> None:
            logs.write(f"  \u21b3 {name}")

        result = await self._data.run_goal(command, on_event=_on_event)
        if result.get("success"):
            trace = result.get("trace_id", "")
            logs.write(f"  done \u2713 {('(' + trace + ')') if trace else ''}")
        else:
            logs.write(f"  failed: {result.get('error', 'unknown error')}")


if __name__ == "__main__":
    JarvisApp().run()
