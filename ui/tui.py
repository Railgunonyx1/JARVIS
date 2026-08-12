"""
JARVIS MK-X terminal console — Textual implementation.

A faithful terminal port of the dockview console prototype in
``extracted_ui/``: warm dark panels, amber accent, chat + agent
timeline + telemetry + logs + memory + tasks visible at once, with
skills / providers / agent plan in a bottom rail. The app is a *client*
of JARVIS's existing daemon (``daemon/client.py`` + ``daemon/lifecycle.py``)
through one data seam (``ui.backend.TuiDataSource``) so the UI never
touches sockets directly.

Data sources:
    live (psutil)          CPU / RAM / disk / uptime
    live (daemon)          provider health, skills, memory, status
    mock (marked)          tasks, plan, memory, files (roadmap follow-ups)

Run ``pip install textual`` once, then ``python -m ui.tui`` or
``jarvis tui``.
"""

from __future__ import annotations

import asyncio
import datetime
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import (
    DataTable,
    Input,
    Label,
    Log,
    ProgressBar,
    Select,
    Sparkline,
    Static,
)

from ui.backend import TuiDataSource

ACCENT = "#c98a3d"
ONLINE = "#6ee7a8"
WARN = "#e8c46a"
ERROR = "#e0695c"
INFO = "#74b3f0"
MUTED = "#9b968b"


def _fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


MOCK_MEMORY = [
    {"kind": "fact", "key": "project/jarvis/transport", "score": 0.92,
     "value": "The daemon talks to clients over the TCP loopback transport"},
    {"kind": "preference", "key": "ui/theme", "score": 0.81,
     "value": "Operator prefers the warm dark engineering console theme"},
    {"kind": "entity", "key": "entity/daemon", "score": 0.76,
     "value": "JARVIS daemon — TCP server with skill registry + event store"},
    {"kind": "episode", "key": "session/2026-08-12/tui", "score": 0.64,
     "value": "Port of the MK-X dockview console into the Textual terminal app"},
]  # MOCK — real entries come from the daemon memory backend


# ------------------------------------------------------------------- widgets

class TopBar(Horizontal):
    MODES = [("PLAN", "plan"), ("CONTROLLED", "controlled"),
             ("SMART", "smart"), ("AGENT", "agent")]

    def compose(self) -> ComposeResult:
        yield Static("JARVIS // CONSOLE", id="topbar-title")
        yield Static("model: -", id="topbar-model")
        yield Static("● offline", id="topbar-daemon")
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
        if not mode:
            return
        self.query_one("#mode-select", Select).value = mode

    def set_model(self, model: str) -> None:
        self.query_one("#topbar-model", Static).update(f"model: {model or '-'}")

    def set_daemon_state(self, connected: bool) -> None:
        select = self.query_one("#mode-select", Select)
        select.disabled = not connected
        dot = self.query_one("#topbar-daemon", Static)
        dot.update(f"[{ONLINE}]● online[/{ONLINE}]"
                   if connected else f"[{ERROR}]● offline[/{ERROR}]")

    async def on_select_changed(self, event: Select.Changed) -> None:
        mode = str(event.value)
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


class Panel(Vertical):
    """Bordered panel with a title label — the basic unit of the console."""

    def __init__(self, title: str, panel_id: str, **kwargs):
        super().__init__(id=panel_id, classes="panel", **kwargs)
        self._title = title

    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="panel-title")


class ChatPanel(Panel):
    """Message transcript + composer (the HTML console's chat dock)."""

    def __init__(self):
        super().__init__("CHAT · session conversation", "panel-chat")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Log(id="chat-view", auto_scroll=True)
        yield Static("", id="chat-status")
        yield Input(placeholder="message jarvis…  (enter to send, /help for commands)",
                    id="chat-input")

    def _line(self, who: str, color: str, text: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.query_one("#chat-view", Log).write_line(
            f"[{MUTED}]{ts}[/{MUTED}] [{color}]{who}[/{color}] {text}")

    def add_user(self, message: str) -> None:
        self._line("you", INFO, message)

    def add_assistant(self, message: str) -> None:
        self._line("jarvis", ACCENT, message)

    def add_system(self, message: str) -> None:
        self._line("system", MUTED, message)

    def set_running(self, running: bool) -> None:
        self.query_one("#chat-status", Static).update(
            f"[{ACCENT}]▮ jarvis is working…[/{ACCENT}]" if running else "")


class TimelinePanel(Panel):
    """Agent phases + tool calls, grouped by run (the HTML timeline dock)."""

    def __init__(self):
        super().__init__("AGENT TIMELINE", "panel-timeline")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Log(id="timeline-view", auto_scroll=True)

    @staticmethod
    def _phase_color(name: str) -> str:
        n = name.lower()
        if "error" in n or "failed" in n or "rejected" in n:
            return ERROR
        if "completed" in n or "done" in n or "passed" in n or n.endswith("ok"):
            return ONLINE
        if ("tool" in n or "step" in n or "command" in n or "action" in n
                or "execute" in n):
            return WARN
        if "memory" in n or "observe" in n or "context" in n:
            return INFO
        return ACCENT

    def write_event(self, name: str, payload: dict | None = None) -> None:
        payload = payload or {}
        color = self._phase_color(name)
        detail = payload.get("tool") or payload.get("action") or ""
        if detail:
            name = f"{name}  {detail}"
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.query_one("#timeline-view", Log).write_line(
            f"[{MUTED}]{ts}[/{MUTED}] [{color}]▸[/{color}] {name}")

    def clear(self):
        self.query_one("#timeline-view", Log).clear()


class TelemetryPanel(Panel):
    """CPU / RAM / disk bars + CPU sparkline (the HTML telemetry dock)."""

    def __init__(self):
        super().__init__("SYSTEM TELEMETRY", "panel-telemetry")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Label("CPU USAGE", id="tel-cpu-label")
        yield ProgressBar(total=100, id="tel-cpu-bar", show_eta=False)
        yield Label("MEMORY USAGE", id="tel-ram-label")
        yield ProgressBar(total=100, id="tel-ram-bar", show_eta=False)
        yield Label("DISK USAGE", id="tel-disk-label")
        yield ProgressBar(total=100, id="tel-disk-bar", show_eta=False)
        yield Sparkline([0.0] * 60, id="tel-spark")
        yield Static("", id="tel-details")

    def update_snapshot(self, snap: dict, cpu_history: list[float]) -> None:
        self.query_one("#tel-cpu-bar", ProgressBar).update(progress=snap["cpu_percent"])
        self.query_one("#tel-ram-bar", ProgressBar).update(progress=snap["ram_percent"])
        disk_pct = (snap["disk_used_gb"] / snap["disk_total_gb"] * 100) \
            if snap["disk_total_gb"] else 0
        self.query_one("#tel-disk-bar", ProgressBar).update(progress=disk_pct)
        self.query_one("#tel-spark", Sparkline).data = cpu_history
        self.query_one("#tel-details", Static).update(
            f"RAM  {snap['ram_used_gb']:.0f} MB / {snap['ram_total_gb']:.0f} GB   "
            f"DISK  {snap['disk_used_gb']:.0f} / {snap['disk_total_gb']:.0f} GB\n"
            f"TASKS  {snap['active_tasks']}   UPTIME  {_fmt_uptime(snap['uptime_s'])}"
        )


class MemoryPanel(Panel):
    """Memory entries with kind chip + importance score (the HTML memory dock)."""

    def __init__(self):
        super().__init__("MEMORY", "panel-memory")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Static("", id="memory-view")

    _KIND_COLOR = {"fact": INFO, "preference": ACCENT,
                   "entity": ONLINE, "episode": WARN}

    def update_data(self, entries: list[dict] | None = None) -> None:
        entries = entries or MOCK_MEMORY
        if not entries:
            self.query_one("#memory-view", Static).update("no memories stored yet")
            return
        lines = []
        for entry in entries:
            kind = entry.get("kind", "fact")
            color = self._KIND_COLOR.get(kind, MUTED)
            score = float(entry.get("score", 0.0))
            bar_len = int(max(0.0, min(1.0, score)) * 12)
            bar = "\u2588" * bar_len + "\u2591" * (12 - bar_len)
            lines.append(
                f"[{color}][{kind.upper():10s}][/{color}] "
                f"[{MUTED}]{entry.get('key', '')}[/{MUTED}]\n"
                f"    {entry.get('value', '')}\n"
                f"    [{ACCENT}]{bar}[/{ACCENT}] {score * 100:.0f}"
            )
        self.query_one("#memory-view", Static).update("\n".join(lines))


class FilesPanel(Panel):
    """Bounded project tree with sizes (the HTML files dock)."""

    _MAX_DEPTH = 2
    _MAX_ENTRIES = 40

    def __init__(self, project_dir: str = "."):
        super().__init__("FILES", "panel-files")
        self._project_dir = project_dir

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Static("", id="files-view")

    def on_mount(self) -> None:
        self.update_data()

    def update_data(self, root: str | None = None) -> None:
        root = Path(root or self._project_dir)
        lines = []
        count = 0

        def _walk(path: Path, prefix: str, depth: int) -> None:
            nonlocal count
            if count >= self._MAX_ENTRIES:
                return
            try:
                children = sorted(os.scandir(path),
                                  key=lambda e: (not e.is_dir(), e.name.lower()))
            except OSError:
                return
            for i, entry in enumerate(children):
                if count >= self._MAX_ENTRIES:
                    return
                is_last = i == len(children) - 1
                connector = "\u2514" if is_last else "\u251c"
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    is_dir = False
                size = "" if is_dir else f"  {entry.stat().st_size / 1024:.0f}K"
                lines.append(
                    f"{prefix}{connector} "
                    f"[{ACCENT if is_dir else MUTED}]{entry.name}[/{ACCENT if is_dir else MUTED}]"
                    f"[{MUTED}]{size}[/{MUTED}]"
                )
                count += 1
                if is_dir and depth < self._MAX_DEPTH:
                    _walk(Path(entry.path), prefix + ("   " if is_last else "\u2502  "),
                          depth + 1)

        _walk(root, "", 0)
        self.query_one("#files-view", Static).update(
            f"[{MUTED}]{root}[/{MUTED}]\n" + "\n".join(lines))


class ProvidersPanel(Panel):
    def __init__(self):
        super().__init__("PROVIDERS", "panel-providers")

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
            status_markup = f"[{ONLINE}]{status}[/{ONLINE}]" \
                if status == "ONLINE" else f"[{ERROR}]{status}[/{ERROR}]"
            table.add_row(name, status_markup, latency, rate, model)


class TasksPanel(Panel):
    def __init__(self):
        super().__init__("TASKS", "panel-tasks")

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
            status_markup = f"[{ONLINE}]{status}[/{ONLINE}]" \
                if status == "RUNNING" else f"[{MUTED}]{status}[/{MUTED}]"
            bar = "\u2588" * (progress // 10) + "\u2591" * (10 - progress // 10)
            progress_cell = f"[{ONLINE}]{bar}[/{ONLINE}] {progress}%" if progress else "-"
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
            state_markup = f"[{ONLINE}]DONE[/{ONLINE}]" \
                if state == "DONE" else f"[{MUTED}]PENDING[/{MUTED}]"
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
            status_markup = f"[{ONLINE}]READY[/{ONLINE}]" \
                if status == "READY" else f"[{MUTED}]LOCKED[/{MUTED}]"
            table.add_row(name, version, status_markup)


class LogsPanel(Panel):
    _TAG_STYLES = {
        "tool": f"[{ONLINE}][TOOL][/{ONLINE}]",
        "ok": f"[{ONLINE}][OK][/{ONLINE}]",
        "memory": f"[#BA68C8][MEMORY][/#BA68C8]",
        "gate": "[dim][GATE][/dim]",
        "task": f"[{WARN}][TASK][/{WARN}]",
        "user": f"[{INFO}][USER][/{INFO}]",
        "err": f"[{ERROR}][ERR][/{ERROR}]",
        "info": f"[{INFO}][INFO][/{INFO}]",
    }

    def __init__(self):
        super().__init__("LOGS", "panel-logs")

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Log(id="logs-view", auto_scroll=True)

    def write(self, message: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.query_one("#logs-view", Log).write_line(f"[{MUTED}]{ts}[/{MUTED}] | {message}")

    def write_event(self, event_name: str):
        """Write a daemon observer event as a tagged activity-stream line."""
        name = event_name.lower()
        if "memory" in name:
            tag = "memory"
        elif "error" in name or "failed" in name or "rejected" in name:
            tag = "err"
        elif "tool" in name or "step" in name or "command" in name:
            tag = "tool"
        elif "user" in name or "input" in name or "utterance" in name:
            tag = "user"
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


# ---------------------------------------------------------------------- app

class JarvisApp(App):
    CSS_PATH = "jarvis_tui.tcss"
    TITLE = "JARVIS MK-X Console"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+l", "focus_chat", "Focus chat"),
    ]

    def __init__(self, data_source: TuiDataSource | None = None,
                 mock: bool = False, url: str | None = None):
        super().__init__()
        self._data = data_source or TuiDataSource(mock=mock, url=url)

    @property
    def data_source(self) -> TuiDataSource:
        return self._data

    def compose(self) -> ComposeResult:
        yield TopBar(id="topbar")
        with Grid(id="mkx-grid"):
            yield ChatPanel()
            yield TimelinePanel()
            yield TelemetryPanel()
            yield LogsPanel()
            yield MemoryPanel()
            yield TasksPanel()
        with Horizontal(id="bottom-rail"):
            yield FilesPanel(self._data.project_dir)
            yield SkillsPanel()
            yield ProvidersPanel()
            yield AgentPlanPanel()

    def action_focus_chat(self) -> None:
        self.query_one("#chat-input", Input).focus()

    def _panel(self, cls):
        """Look up a widget type, returning None while the screen is still mounting."""
        try:
            return self.query_one(cls)
        except NoMatches:
            return None

    def on_mount(self) -> None:
        logs = self.query_one(LogsPanel)
        logs.write("console started")
        self.query_one(TasksPanel).update_data(self._data.task_rows)
        if self._data.using_mock_tasks:
            logs.write("tasks: mock data (no task endpoint on the daemon yet)")
        self.query_one(AgentPlanPanel).update_data(self._data.plan_rows)
        if self._data.using_mock_plan:
            logs.write("agent plan: mock data (no plan endpoint on the daemon yet)")
        self.query_one(SkillsPanel).update_data(self._data.skill_rows)
        if self._data.using_mock_skills:
            logs.write("skills: mock data (daemon offline — start with `jarvis daemon start`)")
        self.query_one(FilesPanel).update_data()
        self.query_one(TopBar).set_daemon_state(self._data.connected)
        self.set_interval(20.0, self._refresh)
        self.set_interval(5.0, self._reconnect)
        self.set_interval(30.0, self._refresh_live)
        asyncio.create_task(self._connect())
        self.query_one("#chat-input", Input).focus()

    async def _connect(self) -> None:
        logs = self._panel(LogsPanel)
        await self._data.connect()
        if self._data.connected:
            if logs:
                logs.write("daemon connected")
            await self._refresh_live()
        else:
            if logs:
                logs.write(f"daemon offline: {self._data.last_error} — showing mock data")
                logs.write("start it in another terminal with `jarvis daemon start`")
        top = self._panel(TopBar)
        if top:
            top.set_daemon_state(self._data.connected)
            top.sync_mode(self._data.status.get("mode", ""))
        hits = await self._data.memory_search("")
        if hits:
            mem = self._panel(MemoryPanel)
            if mem:
                mem.update_data(
                    [{"kind": "fact", "key": h.get("key", str(h)), "value": str(h),
                      "score": h.get("score", 0.5)} for h in hits])

    async def _reconnect(self) -> None:
        if self._data.connected:
            return
        logs = self._panel(LogsPanel)
        await self._data.try_reconnect()
        if self._data.connected:
            if logs:
                logs.write("daemon connected")
            await self._refresh_live()
        top = self._panel(TopBar)
        if top:
            top.set_daemon_state(self._data.connected)
            top.sync_mode(self._data.status.get("mode", ""))

    async def _refresh_live(self) -> None:
        await self._data.refresh()
        providers = self._panel(ProvidersPanel)
        if providers:
            providers.update_data(self._data.provider_rows)
        skills = self._panel(SkillsPanel)
        if skills:
            skills.update_data(self._data.skill_rows)
        top = self._panel(TopBar)
        if top:
            top.set_model(self._data.status.get("model", ""))
            top.sync_mode(self._data.status.get("mode", ""))

    def _refresh(self) -> None:
        snap = self._data.snapshot()
        self.query_one(TelemetryPanel).update_snapshot(snap, self._data.cpu_history)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "chat-input":
            return
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if text.startswith("/"):
            self.query_one(LogsPanel).write(f"> {text}")
            asyncio.create_task(self._run_command(text))
        else:
            asyncio.create_task(self._submit_goal(text))

    async def _submit_goal(self, goal: str) -> None:
        chat = self.query_one(ChatPanel)
        logs = self.query_one(LogsPanel)
        timeline = self.query_one(TimelinePanel)
        chat.add_user(goal)
        if not self._data.connected:
            chat.add_system("daemon offline — start with `jarvis daemon start`")
            return

        def _on_event(name: str, payload: dict) -> None:
            logs.write_event(name)
            timeline.write_event(name, payload)

        chat.set_running(True)
        result = await self._data.run_goal(goal, on_event=_on_event)
        chat.set_running(False)
        if result.get("success"):
            trace = result.get("trace_id", "")
            chat.add_assistant(f"done ✓{(' (' + trace + ')') if trace else ''}")
        else:
            chat.add_assistant(f"failed: {result.get('error', 'unknown error')}")

    async def _run_command(self, command: str) -> None:
        logs = self.query_one(LogsPanel)
        if command.startswith("/"):
            await self._run_slash(command)
            return
        if not self._data.connected:
            logs.write("not sent — daemon offline (start with `jarvis daemon start`)")
            return
        result = await self._data.run_goal(command, on_event=logs.write_event)
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
                "  /skill <name>    show a skill's full detail",
                "  /history [n|id]  recent sessions, or one task's event log",
                "  /reconnect       reconnect to the daemon",
                "  /clear           clear the log",
                "  /exit            quit the console",
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
                color = ONLINE if online else ERROR
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

        if cmd == "/history":
            task_id = "" if arg.isdigit() or not arg else arg
            limit = int(arg) if arg.isdigit() else 50
            result = await self._data.history(limit=limit, task_id=task_id)
            if task_id:
                events = result.get("events") or []
                if not events:
                    logs.write(f"no events for task {task_id!r}")
                    return
                logs.write(f"history: {len(events)} events for task {task_id}")
                for event in events:
                    ts = float(event.get("timestamp") or 0.0)
                    stamp = (datetime.datetime.fromtimestamp(ts)
                             .strftime("%H:%M:%S")) if ts else "-"
                    logs.write(f"  {stamp}  {event.get('name', '?')}")
                return
            traces = result.get("traces") or []
            if not traces:
                logs.write("history: no sessions recorded yet")
                return
            logs.write(f"history: {len(traces)} recent sessions")
            for trace in traces:
                ts = float(trace.get("timestamp") or 0.0)
                stamp = (datetime.datetime.fromtimestamp(ts)
                         .strftime("%Y-%m-%d %H:%M:%S")) if ts else "-"
                logs.write(f"  {stamp}  {trace.get('trace_id', '-')}")
            return

        if cmd in ("/skills", "/skill"):
            result = await self._data.search_skills(arg)
            skills = result.get("skills") or []
            if cmd == "/skill":
                if not arg:
                    logs.write("usage: /skill <name>")
                    return
                detail = next(
                    (s for s in skills if s.get("name", "").lower() == arg.lower()),
                    None,
                )
                if detail is None:
                    logs.write(f"no skill named {arg!r}")
                    return
                mode = self._data.status.get("mode", "")
                ready = (not mode) or mode in (detail.get("supported_modes") or [])
                logs.write(
                    f"{detail.get('name')} v{detail.get('version')} "
                    f"[risk {detail.get('max_risk')}] "
                    f"{'READY' if ready else 'LOCKED'}"
                )
                if detail.get("description"):
                    logs.write(f"  {detail.get('description')}")
                caps = detail.get("capabilities") or []
                if caps:
                    logs.write(f"  capabilities: {', '.join(caps)}")
                perms = detail.get("permissions") or []
                if perms:
                    logs.write(f"  permissions: {', '.join(perms)}")
                modes = detail.get("supported_modes") or []
                if modes:
                    logs.write(f"  modes: {', '.join(modes)}")
                if detail.get("entry_point"):
                    logs.write(f"  entry: {detail.get('entry_point')}")
                return
            if not skills:
                if arg:
                    logs.write(f"no skill hits for {arg!r}")
                else:
                    logs.write("skills: daemon offline (start with `jarvis daemon start`)")
                return
            logs.write(f"skills: {result.get('total')} of {result.get('catalog')} "
                       f"matched ({arg!r})")
            for skill in skills:
                logs.write(
                    f"  {skill.get('name')} v{skill.get('version')} "
                    f"[risk {skill.get('max_risk')}] — {skill.get('description', '')}"
                )
            return

        if not self._data.connected:
            logs.write("not sent — daemon offline (start with `jarvis daemon start`)")
            return

        logs.write(f"unknown command: {cmd} (try /help)")


if __name__ == "__main__":
    JarvisApp().run()
