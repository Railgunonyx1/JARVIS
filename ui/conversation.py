"""JARVIS MK-X Textual conversation client — the presentation layer.

Runs inside Windows Terminal (or any VT100 host). It is a *client* of the
JARVIS daemon, never a direct owner of AgentLoop/providers/memory/executor.
The daemon is the authority; this app renders the agent's event stream and
sends goals over the existing transport (``ui.backend.TuiDataSource``).

Layout (from the MK-X architecture):
    Header          JARVIS MK-X │ ● Connected │ mode │ model │ tokens
    Main            Conversation / Agent Stream + right System/Task sidebar
    Input bar       jarvis> ______________________

Events arrive push-based (task.started / step.started / step.completed /
tool.* / task.finished) and update the conversation and sidebar incrementally
— no polling for task state, no "are you still running?".
"""

from __future__ import annotations

import asyncio
import datetime
import time

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
)

from ui.backend import TuiDataSource

__all__ = ["JarvisApp"]

_MODES = ("plan", "controlled", "smart", "agent")


# ------------------------------------------------------------------ helpers

def _fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


_STATUS_MARK = {"ok": "[green]✓[/green]", "error": "[red]✗[/red]",
                "denied": "[yellow]x[/yellow]", "running": "[cyan]◉[/cyan]"}

_HELP = """\
/help        show this help
/mode        show current mode
/mode <m>    switch mode (plan|controlled|smart|agent)
/status      daemon status
/models      provider availability
/memory      memory stats
/memory add <k>=<v>   remember a fact
/reconnect   force daemon reconnect
/clear       clear conversation
/exit        quit JARVIS"""


# ------------------------------------------------------------------ widgets

class Header(Static):
    """JARVIS MK-X header: connection ●, mode, model, tokens."""

    conn = reactive(False)
    mode = reactive("agent")
    model = reactive("")
    tokens = reactive(0)

    def render(self) -> Text:
        dot = "[green]● Connected[/green]" if self.conn else "[red]○ Offline[/red]"
        bits = [
            Text("JARVIS MK-X", style="bold cyan"),
            Text(dot, style="bold"),
        ]
        if self.mode:
            bits.append(Text(f"mode={self.mode}", style="magenta"))
        if self.model:
            bits.append(Text(self.model, style="yellow"))
        if self.tokens:
            bits.append(Text(f"{self.tokens:,} tokens", style="dim"))
        return Text("   │   ").join(bits)


class ConversationLog(RichLog):
    """The agent stream: user goals, assistant answers, tool events."""

    def __init__(self, **kwargs):
        super().__init__(wrap=True, markup=True, highlight=True,
                         auto_scroll=True, **kwargs)

    def user(self, text: str) -> None:
        self.write("")
        self.write(Text("YOU", style="bold blue"))
        self.write(Text(text))

    def assistant(self, text: str) -> None:
        self.write("")
        self.write(Text("JARVIS", style="bold green"))
        self.write(Text(text))

    def tool(self, name: str, status: str, detail: str = "") -> None:
        mark = _STATUS_MARK.get(status, "?")
        line = Text(f"  {mark} {name}", style="dim")
        if detail:
            line.append(f"  {detail[:160]}", style="italic dim")
        self.write(line)

    def error(self, text: str) -> None:
        self.write("")
        self.write(Text("ERROR", style="bold red"))
        self.write(Text(text, style="red"))

    def system(self, text: str) -> None:
        self.write(Text(f"  · {text}", style="italic dim"))


class DaemonBox(Static):
    """Sidebar block: connection state, pid, uptime, mode."""

    connected = reactive(False)
    status = reactive({})

    def render(self) -> Text:
        lines = [Text("DAEMON", style="bold")]
        if self.connected:
            lines.append(Text("● ONLINE", style="green bold"))
            lines.append(Text(f"pid      {self.status.get('pid', '-')}"))
            lines.append(Text(f"uptime   {_fmt_uptime(float(self.status.get('uptime', 0)))}"))
        else:
            lines.append(Text("○ OFFLINE", style="red bold"))
        lines.append(Text(f"mode     {self.status.get('mode', '-')}"))
        lines.append(Text(f"tools    {self.status.get('tools', '-')}"))
        mem = self.status.get("mem_stats") or {}
        if mem:
            lines.append(Text(f"memory   {mem.get('decisions', 0)}d/{mem.get('knowledge', 0)}k"))
        return Text("\n").join(lines)


class SystemBox(Static):
    """Sidebar block: live CPU / RAM bars + latencies."""

    cpu = reactive(0.0)
    ram = reactive(0.0)

    def render(self) -> Text:
        def bar(ratio: float, width: int = 10) -> str:
            filled = max(0, min(width, int(round(ratio * width))))
            return "█" * filled + "░" * (width - filled)

        cpu_style = "green" if self.cpu < 70 else ("yellow" if self.cpu < 90 else "red")
        ram_style = "green" if self.ram < 80 else ("yellow" if self.ram < 95 else "red")
        lines = [
            Text("SYSTEM", style="bold"),
            Text(f"cpu  {self.cpu:>3.0f}%  ", style=cpu_style) + Text(bar(self.cpu / 100)),
            Text(f"ram  {self.ram:>3.0f}%  ", style=ram_style) + Text(bar(self.ram / 100)),
        ]
        return Text("\n").join(lines)


class TaskBox(Static):
    """Sidebar block: current task, running step, token counter."""

    goal = reactive("")
    step_label = reactive("")
    progress = reactive(0.0)
    tokens = reactive(0)

    def render(self) -> Text:
        lines = [Text("TASK", style="bold")]
        if not self.goal:
            lines.append(Text("idle — type a goal below", style="dim"))
        else:
            lines.append(Text(f"goal   {self.goal[:40]}"))
            lines.append(Text(self.step_label or "…", style="cyan"))
            width = 10
            filled = max(0, min(width, int(round(self.progress * width))))
            lines.append(Text("█" * filled + "░" * (width - filled), style="green"))
            lines.append(Text(f"tokens {self.tokens:,}", style="dim"))
        return Text("\n").join(lines)


class Sidebar(Vertical):
    def compose(self) -> ComposeResult:
        yield DaemonBox(id="daemon-box")
        yield SystemBox(id="system-box")
        yield TaskBox(id="task-box")


class InputBar(Horizontal):
    def compose(self) -> ComposeResult:
        yield Static("jarvis>", id="prompt")
        yield Input(placeholder="ask JARVIS…", id="cmd-input")


# ---------------------------------------------------------------------- app

class JarvisApp(App):
    CSS_PATH = "conversation.tcss"
    TITLE = "JARVIS MK-X"
    BINDINGS = [
        ("ctrl+c", "cancel", "Cancel task"),
        ("ctrl+l", "clear", "Clear conversation"),
        ("ctrl+r", "reconnect", "Reconnect daemon"),
        ("ctrl+m", "focus_input", "Focus input"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, data_source: TuiDataSource | None = None,
                 mock: bool = False, url: str | None = None,
                 project_dir: str | None = None) -> None:
        super().__init__()
        self._data = data_source or TuiDataSource(
            mock=mock, url=url, project_dir=project_dir)
        self._run_task: asyncio.Task | None = None
        self._started_at = time.time()

    @property
    def data_source(self) -> TuiDataSource:
        return self._data

    def compose(self) -> ComposeResult:
        yield Header(id="header")
        with Container(id="main"):
            yield ConversationLog(id="conversation")
            yield Sidebar(id="sidebar")
        yield InputBar(id="input-bar")

    def on_mount(self) -> None:
        header = self.query_one(Header)
        header.conn = False
        header.mode = "agent"
        self.set_interval(1.0, self._tick)
        self.set_interval(2.0, self._try_reconnect)
        self.set_interval(1.0, self._update_system)
        self.set_interval(5.0, self._refresh_status)
        asyncio.create_task(self._connect())
        self.query_one("#cmd-input", Input).focus()

    # ── connection lifecycle ─────────────────────────────────────────────

    async def _connect(self) -> None:
        log = self.query_one(ConversationLog)
        log.system("connecting to JARVIS daemon…")
        await self._data.connect()
        self._sync_connected()

    async def _try_reconnect(self) -> None:
        if self._data.connected:
            return
        if self._run_task and not self._run_task.done():
            return
        await self._data.try_reconnect()
        if self._data.connected:
            self._sync_connected()
            self.query_one(ConversationLog).system("daemon reconnected")
        self._sync_connected()

    def _sync_connected(self) -> None:
        header = self.query_one(Header)
        header.conn = self._data.connected
        box = self.query_one(DaemonBox)
        box.connected = self._data.connected
        box.status = self._data.status

    # ── periodic refreshes ───────────────────────────────────────────────

    def _tick(self) -> None:
        header = self.query_one(Header)
        if self._data.status:
            header.mode = self._data.status.get("mode", header.mode)
            header.model = (
                f"{self._data.status.get('model', '')}/{self._data.status.get('provider', '')}"
                or header.model)

    def _update_system(self) -> None:
        snap = self._data.snapshot()
        box = self.query_one(SystemBox)
        box.cpu = snap["cpu_percent"]
        box.ram = snap["ram_percent"]

    async def _refresh_status(self) -> None:
        if not self._data.connected:
            return
        await self._data.refresh()
        self._sync_connected()

    # ── commands ─────────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        event.input.value = ""
        if not command:
            return
        if command.startswith("/"):
            self._slash_command(command)
            return
        log = self.query_one(ConversationLog)
        log.user(command)
        task = self.query_one(TaskBox)
        task.goal = command
        task.step_label = "starting…"
        task.progress = 0.0
        if not self._data.connected:
            log.error("daemon offline — start it with `jarvis daemon start`")
            task.goal = ""
            return
        self._run_task = asyncio.create_task(self._run_goal(command))

    def _slash_command(self, line: str) -> None:
        log = self.query_one(ConversationLog)
        cmd, _, arg = line.partition(" ")
        arg = arg.strip()

        if cmd in ("/help", "/?"):
            log.system(_HELP)
        elif cmd == "/clear":
            self.action_clear()
        elif cmd == "/reconnect":
            self.action_reconnect()
        elif cmd == "/mode" and not arg:
            log.system(f"mode: {self._data.status.get('mode', '-')}")
        elif cmd == "/mode" and arg:
            if arg not in _MODES:
                log.error(f"unknown mode '{arg}' — use {', '.join(_MODES)}")
            elif self._data.connected:
                asyncio.create_task(self._set_mode(arg, log))
            else:
                log.error("daemon offline")
        elif cmd == "/status":
            self._print_status(log)
        elif cmd == "/models":
            asyncio.create_task(self._print_models(log))
        elif cmd == "/memory":
            self._print_memory(log)
        elif cmd == "/exit" or cmd == "/quit":
            self.exit()
        else:
            log.error(f"unknown command {cmd} — /help for the list")

    async def _set_mode(self, mode: str, log: ConversationLog) -> None:
        try:
            await self._data._client.set_mode(mode)
        except Exception as exc:
            log.error(str(exc))
            return
        self._data.status["mode"] = mode
        self._sync_connected()
        log.system(f"mode → {mode}")

    def _print_status(self, log: ConversationLog) -> None:
        s = self._data.status
        if not s:
            log.system("daemon offline")
            return
        log.system(
            f"mode={s.get('mode')} tools={s.get('tools')} "
            f"model={s.get('model')}/{s.get('provider')} "
            f"mem={s.get('mem_stats')}")

    async def _print_models(self, log: ConversationLog) -> None:
        try:
            models = await self._data._client.models()
        except Exception as exc:
            log.error(str(exc))
            return
        for name, info in (models.get("data", models) or {}).items():
            ok = "yes" if info.get("available") else "no"
            log.system(f"{name:<12} {info.get('model', '')}  avail={ok}")

    def _print_memory(self, log: ConversationLog) -> None:
        mem = self._data.status.get("mem_stats")
        log.system(f"memory: {mem}" if mem else "no memory stats")

    # ── goal execution with push events ──────────────────────────────────

    async def _run_goal(self, goal: str) -> None:
        log = self.query_one(ConversationLog)
        task = self.query_one(TaskBox)
        header = self.query_one(Header)

        def _on_event(name: str, payload: dict) -> None:
            _handle_event(name, payload, log, task, header)

        try:
            result = await self._data.run_goal(goal, on_event=_on_event)
        except Exception as exc:
            log.error(f"run failed: {exc}")
            task.goal = ""
            return

        _render_result(result, log, task, header)
        task.goal = ""


def _handle_event(name: str, payload: dict, log: ConversationLog,
                  task: TaskBox, header: Header) -> None:
    if name == "task.started":
        task.goal = payload.get("goal", task.goal)
        task.progress = 0.0
        task.step_label = "planning…"
    elif name == "step.started":
        tool = payload.get("tool", "")
        task.step_label = f"{tool}…"
        log.tool(tool, "running")
    elif name == "step.completed":
        status = payload.get("status", "ok")
        tool = payload.get("tool", "")
        dur = payload.get("duration_ms", 0)
        log.tool(tool, status, f"{dur:.0f}ms")
        task.step_label = f"{tool} {status}"
    elif name == "task.finished":
        status = payload.get("status", "")
        if status == "completed":
            task.progress = 1.0
        header.tokens = payload.get("tokens", header.tokens)
    elif name == "permission.observed" and not payload.get("allowed"):
        log.system(f"permission denied for {payload.get('tool')}: {payload.get('reason', '')}")
    elif name == "task.cancelled":
        log.system("task cancelled")


def _render_result(result: dict, log: ConversationLog, task: TaskBox,
                   header: Header) -> None:
    state = result.get("state") or {}
    if result.get("success"):
        log.assistant(result.get("response", ""))
    else:
        log.error(result.get("error", "unknown error"))
    calls = state.get("tool_calls", [])
    if calls:
        chain = ", ".join(f"{c['name']}({c.get('duration_ms', 0):.0f}ms)" for c in calls)
        log.system(f"tools: {chain}")
    if state.get("tokens_used"):
        header.tokens = state["tokens_used"]
    task.progress = 1.0
    task.step_label = "done"


# ----------------------------------------------------------------- actions

    def action_clear(self) -> None:
        self.query_one(ConversationLog).clear()

    def action_reconnect(self) -> None:
        log = self.query_one(ConversationLog)
        log.system("reconnecting…")
        self._data._connected = False
        asyncio.create_task(self._reconnect_now())

    async def _reconnect_now(self) -> None:
        log = self.query_one(ConversationLog)
        try:
            await self._data.try_reconnect()
        except Exception as exc:
            log.error(f"reconnect failed: {exc}")
            self._sync_connected()
            return
        self._sync_connected()
        log.system("daemon connected" if self._data.connected else "still offline")

    def action_cancel(self) -> None:
        log = self.query_one(ConversationLog)
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
            self._run_task = None
            log.system("task cancelled")
            self.query_one(TaskBox).goal = ""
        else:
            self.query_one(ConversationLog).system("no task running")

    def action_focus_input(self) -> None:
        self.query_one("#cmd-input", Input).focus()

    def action_quit(self) -> None:
        self.exit()


if __name__ == "__main__":
    JarvisApp().run()
