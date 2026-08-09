"""JARVIS MK-X CLI — one-shot and interactive agent entrypoint (M0 + Phase 4 UX).

Usage:
    python -m cli "create hello.txt containing JARVIS MK-X operational"
    python -m cli --mode plan --json "analyze this repo"
    python -m cli --json "list files"     # machine-readable output for pipes
    python -m cli                          # interactive command center
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import sys
import threading
import time
import warnings
from pathlib import Path

_IMPORT_START = time.perf_counter()

import typer
from rich.console import Console
from rich.text import Text

# Pipes on Windows default to cp1252, which cannot encode arrows/dashes the
# cockpit uses — force UTF-8 everywhere with a lossless fallback.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Quiet by default: suppress library progress bars / telemetry before any
# provider is imported (google.generativeai, transformers, huggingface_hub…).
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore")

# Heavy modules (config, providers, tools, memory, UI panels) are imported
# lazily inside the functions that need them so the interactive prompt can
# appear before the kernel finishes booting.

app = typer.Typer(add_completion=False)
console = Console()

_IMPORT_MS = (time.perf_counter() - _IMPORT_START) * 1000.0

_MODES = ("plan", "controlled", "smart", "agent")


def _configure_noise(verbose: bool) -> None:
    """Route all non-jarvis logger output to ERROR unless verbose is on."""
    warnings.filterwarnings("default" if verbose else "ignore")
    level = logging.NOTSET if verbose else logging.ERROR
    for name, logger in list(logging.root.manager.loggerDict.items()):
        if isinstance(logger, logging.Logger) and not name.startswith("jarvis"):
            logger.setLevel(level)


def _setup_logging(verbose: bool) -> None:
    from core.utils import setup_logging
    setup_logging(level="INFO" if verbose else "WARNING")
    _configure_noise(verbose)


def _build_router():
    from core.config import Config
    from providers.router import ProviderRouter

    config = Config.instance()
    return ProviderRouter(config.get_section("models"), config.api_keys)


def _build_loop(mode: str, max_iterations: int, max_tokens: int | None,
                project_dir: str | None):
    from cli.startup_profile import get_profiler
    from core.agent.loop import AgentLoop
    from core.config import Config
    from core.project import ProjectContext
    from memory.mem import get_mem
    from tools import build_default_registry

    profiler = get_profiler()
    profiler.begin_trace()
    try:
        with profiler.phase("config.load"):
            Config.instance()
        with profiler.phase("tools.registry"):
            registry = build_default_registry()
        with profiler.phase("project.discover"):
            project = ProjectContext.discover(project_dir) if project_dir else ProjectContext.discover()
        with profiler.phase("providers.router"):
            router = _build_router()
        with profiler.phase("memory.open"):
            mem = get_mem()
            mem.import_project_docs(str(project.root_path), project.root_path)
        if not getattr(_build_loop, "_mem_cleanup_registered", False):
            _build_loop._mem_cleanup_registered = True
            import atexit
            atexit.register(mem.close)
        return AgentLoop(
            router=router,
            registry=registry,
            project=project,
            mode=mode,
            max_iterations=max_iterations,
            max_tokens=max_tokens,
            mem=mem,
        )
    finally:
        profiler.end_trace()


def _status_getter(loop) -> dict:
    return {
        "mode": str(loop.permissions.mode),
        "provider": getattr(loop.router, "_last_provider", None),
        "model": getattr(loop.router, "_last_model", None),
    }


def _print_result(result) -> None:
    state = result.state
    obs = result.observation or {}
    steps = obs.get("steps", [])
    if steps:
        marks = {"ok": "ok", "error": "err", "denied": "deny", "running": "run"}
        chain = " → ".join(
            f"{s['tool']}[{marks.get(s['status'], s['status'])} {s['duration_ms']}ms]"
            for s in steps
        )
        print(f"[steps] {chain}")
    if state.tool_calls:
        calls = ", ".join(f"{c['name']}({c['duration_ms']}ms)" for c in state.tool_calls)
        print(f"[tools] {calls}")
    for call in state.tool_calls:
        diff = call.get("diff")
        if diff:
            print(f"[diff] {call.get('output', '')}")
            print(diff)
    if result.success:
        print(result.response)
    else:
        print(f"ERROR: {result.error}", file=sys.stderr)
    print(f"[trace {result.trace_id}] provider={state.provider} model={state.model} "
          f"tokens={state.tokens_used} duration_ms={obs.get('duration_ms', '')}")
    usage = obs.get("context_usage") or {}
    if usage:
        compact = " [compacted]" if usage.get("compacted") else ""
        print(f"[context] {usage.get('total_tokens', 0)}/{usage.get('total_budget', 0)} "
              f"tokens system={usage.get('system_tokens', 0)} "
              f"memory={usage.get('memory_tokens', 0)} files={usage.get('files_tokens', 0)} "
              f"messages={usage.get('messages_tokens', 0)}{compact}")


def _print_collapsed(result) -> None:
    """Conversation-dominant result: answer + one collapsed summary line."""
    from cli.details import render_summary

    state = result.state
    if result.success:
        console.print(Text(result.response))
    else:
        typer.secho(f"ERROR: {result.error}", err=True, fg="red")
    for call in state.tool_calls:
        diff = call.get("diff")
        if diff:
            print(f"[diff] {call.get('output', '')}")
            print(diff)
    console.print(Text(f"  ▶ {render_summary(result)}  (Enter to expand)", style="dim"))


def _capture_notification(name: str, payload: dict, notifications: list) -> None:
    """Map observer events to the rolling notification log."""
    if name == "task.finished":
        status = payload.get("status", "")
        mark = "ok" if status in ("completed", "ok") else "err"
        notifications.append((mark, f"task {payload.get('task_id', '')[:8]} {status} "
                                     f"in {payload.get('duration_ms', 0):.0f}ms"))
    elif name == "step.failed":
        notifications.append(("err", f"step failed: {payload.get('error', '')[:60]}"))
    elif name == "permission.observed" and not payload.get("allowed"):
        notifications.append(("warn", f"{payload.get('tool')} denied"))
    elif name == "context.compacted":
        notifications.append(("info", "context compacted"))


async def _run_once(goal: str, loop, json_output: bool = False,
                    collapsed: bool = False, notifications: list | None = None,
                    perf: bool = False) -> None:
    from cli.ux import LiveTaskDisplay

    loop._last_goal = goal
    notifications = notifications if notifications is not None else []
    display = LiveTaskDisplay(
        status_getter=(lambda: _status_getter(loop)),
        enable=not json_output,
    )

    def _on_event(name: str, payload: dict) -> None:
        _capture_notification(name, payload, notifications)
        if not json_output:
            display._on_event(name, payload)

    if not json_output:
        display.attach(loop.observer)
    loop.observer.on_event = _on_event
    if not json_output:
        display.start()
    try:
        result = await loop.run(goal)
    finally:
        display.stop()
    loop._last_result = result
    if json_output:
        payload = result.to_dict()
        state = payload.pop("state", {})
        print(json.dumps({"goal": goal, **state, **payload}, indent=2, default=str))
    elif collapsed:
        _print_collapsed(result)
    else:
        _print_result(result)
    if perf:
        _print_perf_trace(result)
        _print_ui_render(display)
    loop.logger.flush()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    goal: str | None = typer.Argument(None, help="One-shot goal. Omit for the interactive prompt."),
    mode: str = typer.Option("agent", help="Execution mode: plan | controlled | smart | agent"),
    max_iterations: int = typer.Option(10, help="Maximum agent loop iterations."),
    max_tokens: int | None = typer.Option(None, help="Max tokens per LLM call."),
    project_dir: str | None = typer.Option(None, help="Project root for path resolution."),
    verbose: bool = typer.Option(False, help="Enable INFO logging."),
    json_output: bool = typer.Option(False, "--json", help="Emit a JSON result for scripts/pipes."),
    profile_startup: bool = typer.Option(False, "--profile-startup",
                                         help="Print a startup phase timing report."),
    daemon: bool = typer.Option(False, "--daemon",
                                help="Use (and start if needed) the persistent kernel daemon."),
    standalone: bool = typer.Option(False, "--standalone",
                                    help="Boot an in-process kernel (ignore any running daemon)."),
    perf: bool = typer.Option(False, "--perf",
                              help="Print a request performance timeline after the run."),
) -> None:
    """JARVIS MK-X — terminal-first autonomous engineering agent."""
    if ctx.invoked_subcommand is not None:
        return
    if mode not in _MODES:
        typer.secho(f"Unknown mode '{mode}'. Choose from {', '.join(_MODES)}.", err=True, fg="red")
        raise typer.Exit(code=1)

    _setup_logging(verbose)

    if goal:
        client = _resolve_transport(daemon, standalone, project_dir)
        if client is not None:
            from daemon.client import DaemonDisconnected, DaemonError

            try:
                _daemon_one_shot(goal, client, json_output=json_output,
                                 perf=perf)
            except (DaemonDisconnected, DaemonError, ConnectionError, OSError) as exc:
                if daemon:
                    typer.secho(f"daemon connection failed: {exc}", err=True, fg="red")
                    raise typer.Exit(code=1) from None
                client = None
        if client is None:
            loop = _build_loop(mode, max_iterations, max_tokens, project_dir)
            asyncio.run(_run_once(goal, loop, json_output=json_output, perf=perf))
        if profile_startup:
            _print_startup_report()
    else:
        client = _resolve_transport(daemon, standalone, project_dir)
        if client is not None:
            _interactive_daemon(client, profile_startup=profile_startup)
        else:
            _interactive(mode, max_iterations, max_tokens, project_dir,
                         profile_startup=profile_startup)


# ── daemon transport ────────────────────────────────────────────────────────

def _resolve_project_dir(project_dir: str | None) -> str:
    return str((Path(project_dir) if project_dir else Path.cwd()).resolve())


def _resolve_transport(force_daemon: bool, force_standalone: bool,
                       project_dir: str | None):
    """Return a DaemonClient for this project when a daemon should be used.

    ``--standalone`` forces an in-process kernel. Otherwise a healthy daemon
    for this project is reused; if it is dead or absent it is resurrected
    automatically so the CLI never pays a cold kernel boot when a resident
    daemon can be (re)started instead. ``--daemon`` additionally treats a
    start failure as fatal. The client is returned unconnected; the caller
    connects on its own event loop (a transport can't cross loops).
    """
    from daemon.client import DaemonClient
    from daemon.lifecycle import find_matching, start_daemon

    project = _resolve_project_dir(project_dir)
    entry = None
    if not force_standalone:
        entry = find_matching(project)
        if entry is None:
            entry = start_daemon(project)
    if entry is None and force_daemon:
        typer.secho("daemon failed to start — run `jarvis daemon status` "
                    "or check ~/.jarvis/daemon.log", err=True, fg="red")
        raise typer.Exit(code=1)
    if entry is None:
        return None
    return DaemonClient(port=entry["port"], token=entry["token"],
                        project_id=entry["project_id"])


def _render_status_bar_dict(status: dict) -> Text:
    """Status-bar line rendered from a daemon status dict."""
    bits = ["JARVIS"]
    bits.append(f"mode={status.get('mode', 'agent')}")
    if status.get("provider"):
        bits.append(f"{status.get('model')}/{status.get('provider')}")
    bits.append(f"tools={status.get('tools', 0)}")
    mem = status.get("mem_stats") or {}
    if mem:
        bits.append(f"mem={mem.get('decisions', 0)}d/{mem.get('knowledge', 0)}k")
    if status.get("busy"):
        bits.append("busy")
    return Text("  │  ".join(bits))


def _print_result_dict(result: dict) -> None:
    """Render a daemon result dict exactly like a local AgentResult."""
    state = result.get("state", {}) or {}
    obs = result.get("observation", {}) or {}
    steps = obs.get("steps", [])
    if steps:
        marks = {"ok": "ok", "error": "err", "denied": "deny", "running": "run"}
        chain = " → ".join(
            f"{s['tool']}[{marks.get(s['status'], s['status'])} {s['duration_ms']}ms]"
            for s in steps
        )
        print(f"[steps] {chain}")
    calls = state.get("tool_calls", [])
    if calls:
        chain = ", ".join(f"{c['name']}({c['duration_ms']}ms)" for c in calls)
        print(f"[tools] {chain}")
    for call in calls:
        diff = call.get("diff")
        if diff:
            print(f"[diff] {call.get('output', '')}")
            print(diff)
    if result.get("success"):
        print(result.get("response", ""))
    else:
        print(f"ERROR: {result.get('error', '')}", file=sys.stderr)
    usage = obs.get("context_usage") or state.get("context_usage") or {}
    compact = " [compacted]" if usage.get("compacted") else ""
    print(f"[trace {result.get('trace_id')}] provider={state.get('provider')} "
          f"model={state.get('model')} tokens={state.get('tokens_used')} "
          f"duration_ms={state.get('duration_ms', '')}")
    if usage:
        print(f"[context] {usage.get('total_tokens', 0)}/{usage.get('total_budget', 0)} "
              f"tokens system={usage.get('system_tokens', 0)} "
              f"memory={usage.get('memory_tokens', 0)} files={usage.get('files_tokens', 0)} "
              f"messages={usage.get('messages_tokens', 0)}{compact}")


def _print_collapsed_dict(result: dict) -> None:
    """Collapsed (conversation-dominant) rendering of a daemon result dict."""
    state = result.get("state", {}) or {}
    if result.get("success"):
        console.print(Text(result.get("response", "")))
    else:
        typer.secho(f"ERROR: {result.get('error', '')}", err=True, fg="red")
    for call in state.get("tool_calls", []):
        diff = call.get("diff")
        if diff:
            print(f"[diff] {call.get('output', '')}")
            print(diff)
    summary = (f"{len(state.get('tool_calls', []))} tools · "
               f"{state.get('tokens_used', 0)} tokens · "
               f"{state.get('duration_ms', 0):.0f}ms")
    console.print(Text(f"  ▶ {summary}  (Enter to expand)", style="dim"))


async def _run_once_daemon(goal: str, client, json_output: bool = False,
                           collapsed: bool = False,
                           notifications: list | None = None,
                           perf: bool = False) -> dict:
    """Run a goal against the daemon, streaming observer events to the UX."""
    from cli.ux import LiveTaskDisplay

    notifications = notifications if notifications is not None else []
    display = LiveTaskDisplay(
        status_getter=(lambda: client.cached_status),
        enable=not json_output,
    )

    def _on_event(name: str, payload: dict) -> None:
        _capture_notification(name, payload, notifications)
        if not json_output:
            display._on_event(name, payload)

    if not json_output:
        display.start()
    try:
        await client.connect()
        result = await client.run(goal, on_event=_on_event)
    finally:
        display.stop()
        await client.close()
    if json_output:
        print(json.dumps({"goal": goal, **result}, indent=2, default=str))
    elif collapsed:
        _print_collapsed_dict(result)
    else:
        _print_result_dict(result)
    if perf:
        _print_perf_trace(result)
        _print_ui_render(display)
    return result


def _print_perf_trace(result) -> None:
    """Render the request performance timeline (opt-in, stderr, no Rich)."""
    trace = (result.perf if hasattr(result, "perf") else result.get("perf")) or {}
    if not trace:
        return
    from runtime.observability.dashboard import render_trace

    print(render_trace(trace), file=sys.stderr)


def _print_ui_render(display) -> None:
    if display.renders == 0:
        return
    print(
        f"[ui] {display.renders} renders, avg {display.render_ms / display.renders:.2f} ms"
        f" last {display.last_render_ms:.2f} ms",
        file=sys.stderr,
    )


def _daemon_one_shot(goal: str, client, json_output: bool = False,
                     perf: bool = False) -> None:
    asyncio.run(_run_once_daemon(goal, client, json_output=json_output, perf=perf))


def _client_call(client, coro):
    """Run one coroutine on a fresh event loop with a fresh connection."""
    async def _wrapped():
        await client.connect()
        try:
            return await coro
        finally:
            await client.close()
    return asyncio.run(_wrapped())


def _interactive_daemon(client, profile_startup: bool = False) -> None:
    """Interactive command center against a persistent daemon kernel."""
    from cli.cockpit import render_notifications

    console.clear()
    console.print(Text("JARVIS MK-X — persistent daemon kernel", style="bold cyan"))
    console.print(Text("/help for commands", style="dim"))

    notifications: list = []
    _configure_noise(verbose=False)

    try:
        status = _client_call(client, client.status())
    except Exception as exc:
        typer.secho(f"daemon connection failed: {exc}", err=True, fg="red")
        return
    if not status:
        typer.secho("daemon connection failed", err=True, fg="red")
        return
    console.print(_render_status_bar_dict(status))
    if profile_startup:
        _print_startup_report()

    last_goal = ""
    last_result: dict | None = None

    while True:
        try:
            line = input("JARVIS> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            if last_result is not None:
                _print_result_dict(last_result)
            continue
        if line in ("/exit", "/quit"):
            break
        if line == "/help":
            _print_help()
        elif line == "/clear":
            console.clear()
        elif line == "/notifications":
            console.print(render_notifications(notifications))
        elif line == "/plan":
            _client_call(client, client.set_mode("plan"))
            notifications.append(("info", "mode → plan (read-only)"))
            typer.secho("mode → plan (read-only)", fg="green")
        elif line == "/mode":
            info = _client_call(client, client.status())
            print(f"mode: {info.get('mode')}")
        elif line.startswith("/mode "):
            new_mode = line[6:].strip()
            if new_mode not in _MODES:
                typer.secho(f"Unknown mode '{new_mode}'.", err=True, fg="red")
            else:
                _client_call(client, client.set_mode(new_mode))
                notifications.append(("info", f"mode → {new_mode}"))
                typer.secho(f"mode → {new_mode}", fg="green")
        elif line == "/model":
            info = _client_call(client, client.status())
            print(f"model={info.get('model')} provider={info.get('provider')}")
        elif line == "/models":
            _print_models_dict(_client_call(client, client.models()))
        elif line == "/status":
            info = _client_call(client, client.status())
            print(f"provider={info.get('provider')} model={info.get('model')}")
            print(f"tools: {info.get('tools', 0)} registered")
            print(f"mode: {info.get('mode')}")
            print(f"memory: {info.get('mem_stats')}")
            print(f"busy: {info.get('busy')}")
        elif line == "/tools":
            info = _client_call(client, client.status())
            print(f"tools: {info.get('tools', 0)} registered (daemon)")
        elif line in ("/context", "/tokens", "/compact", "/cockpit", "/tree", "/verbose"):
            typer.secho(f"{line} is local-only — not available via the daemon",
                        err=True, fg="yellow")
        elif line.startswith("/memory"):
            _cmd_memory_daemon(client, line)
        elif line.startswith("/history"):
            _cmd_history_daemon(client, line)
        elif line == "/resume":
            if not last_goal:
                typer.secho("no previous goal to resume", err=True, fg="red")
            else:
                last_result = asyncio.run(_run_once_daemon(
                    last_goal, client, collapsed=True, notifications=notifications))
        else:
            last_goal = line
            try:
                last_result = asyncio.run(_run_once_daemon(
                    line, client, collapsed=True, notifications=notifications))
            except KeyboardInterrupt:
                typer.secho("(interrupted)", dim=True)
                last_result = None
            except (ConnectionError, OSError) as exc:
                typer.secho(f"daemon connection lost: {exc}", err=True, fg="red")
                last_result = None


def _print_models_dict(data: dict) -> None:
    from rich.table import Table

    table = Table(title="Model status (daemon)")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Available")
    for name, info in data.items():
        table.add_row(
            name, info.get("model", ""),
            "yes" if info.get("available") else "no",
        )
    console.print(table)


def _cmd_memory_daemon(client, line: str) -> None:
    parts = line.split(maxsplit=2)
    if len(parts) == 1:
        info = _client_call(client, client.status())
        print(info.get("mem_stats"))
        return
    action = parts[1]
    if action == "search" and len(parts) == 3:
        hits = _client_call(client, client.memory_search(parts[2], top_k=5))
        for hit in hits:
            print(f"[{hit['source']}:{hit['score']:.2f}] {hit['content'][:160]}")
    elif action == "add" and len(parts) == 3:
        key, _, value = parts[2].partition("=")
        message = _client_call(
            client, client.memory_add(key.strip() or "note", value.strip()))
        print(message)
    else:
        typer.secho("usage: /memory [search <query> | add <key>=<value>]", err=True, fg="red")


def _cmd_history_daemon(client, line: str) -> None:
    parts = line.split(maxsplit=1)
    task_id = parts[1].strip() if len(parts) == 2 else ""
    data = _client_call(client, client.history(task_id))
    if task_id:
        for event in data.get("events", []):
            ts = datetime.datetime.fromtimestamp(event["timestamp"]).strftime("%H:%M:%S")
            print(f"{ts} {event['name']} {json.dumps(event['data'], default=str)[:120]}")
    else:
        for trace in data.get("traces", []):
            ts = datetime.datetime.fromtimestamp(trace["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            print(f"{trace['trace_id']}  {ts}")


def daemon_cli(argv) -> int:
    """`jarvis daemon start|stop|status|list` — dispatched at the entry point.

    Lives outside the typer app because click consumes the first positional
    token as the callback's ``goal`` argument, making a typer subcommand named
    ``daemon`` unreachable. ``entry()`` routes here before typer parses.
    """
    import argparse

    from daemon.lifecycle import (
        daemon_status,
        list_daemons,
        start_daemon,
        stop_daemon,
        sweep_stale_entries,
    )

    parser = argparse.ArgumentParser(
        prog="jarvis daemon",
        description="Control the persistent kernel daemon for this project.",
    )
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("start", help="start (and reuse if already running) the daemon")
    sub.add_parser("stop", help="stop the daemon for this project")
    sub.add_parser("status", help="show daemon status for this project")
    sub.add_parser("list", help="list all running daemons")
    sub.add_parser("sweep", help="remove registry entries for dead/unreachable daemons")
    args = parser.parse_args(argv)

    project = _resolve_project_dir(None)
    if args.action == "start":
        entry = start_daemon(project)
        if entry is None:
            typer.secho("daemon failed to start — check ~/.jarvis/daemon.log",
                        err=True, fg="red")
            return 1
        print(f"daemon running: pid={entry['pid']} port={entry['port']} "
              f"project={entry['project']}")
        return 0
    if args.action == "sweep":
        removed = sweep_stale_entries()
        if not removed:
            print("no stale daemons to remove")
            return 0
        for entry in removed:
            print(f"removed stale: {entry['project']}  pid={entry.get('pid')}  "
                  f"port={entry.get('port')}")
        return 0
    if args.action == "stop":
        ok = stop_daemon(project)
        print("daemon stopped" if ok else "no daemon running / stop failed")
        return 0 if ok else 1
    if args.action == "status":
        info = daemon_status(project)
        if info is None:
            print("no daemon running for this project")
            return 1
        for key, value in info.items():
            print(f"{key}: {value}")
        return 0
    entries = list_daemons()
    if not entries:
        print("no daemons running")
    for entry in entries:
        print(f"{entry['project']}  pid={entry['pid']}  port={entry['port']}  "
              f"healthy={entry['healthy']}")
    return 0


def perf_cli(argv) -> int:
    """`jarvis perf [latest|slowest|summary]` — read persisted performance data.

    Runs in a separate process from the daemon, opening its own read-only
    connection to the performance SQLite database (WAL-safe). Persisted by
    the daemon on every request via ``runtime.observability.exporters``.
    """
    import argparse

    from runtime.observability.dashboard import render_summary, render_trace, trace_table
    from runtime.observability.exporters import perf_db_path, read_latest, read_slowest, read_summary

    parser = argparse.ArgumentParser(
        prog="jarvis perf",
        description="Show persisted JARVIS performance data.",
    )
    sub = parser.add_subparsers(dest="action")
    latest = sub.add_parser("latest", help="most recent request traces")
    latest.add_argument("-n", type=int, default=5)
    slowest = sub.add_parser("slowest", help="slowest request traces")
    slowest.add_argument("-n", type=int, default=5)
    sub.add_parser("summary", help="aggregate phase timings and counters")
    args = parser.parse_args(argv)

    path = perf_db_path()
    if not path.exists():
        print("no performance data yet — run a request through the daemon first", file=sys.stderr)
        print(f"(db: {path})", file=sys.stderr)
        return 1

    if args.action == "slowest":
        traces = read_slowest(path, limit=args.n)
        print(trace_table(traces))
        print()
        for trace in traces:
            print(render_trace(trace))
            print()
    elif args.action == "latest":
        traces = read_latest(path, limit=args.n)
        print(trace_table(traces))
        print()
        for trace in traces:
            print(render_trace(trace))
            print()
    else:
        print(render_summary(read_summary(path)))
        print()
        for trace in read_latest(path, limit=3):
            print(render_trace(trace))
            print()
    return 0


def tui_cli(argv) -> int:
    """`jarvis tui` — launch the Textual dashboard, a client of the daemon.

    Imported lazily so the default REPL keeps a tiny startup profile; the
    TUI talks to the running daemon over TCP (or the named pipe) and falls
    back to a mock provider when no daemon is up.
    """
    import argparse

    from ui.tui import JarvisApp

    parser = argparse.ArgumentParser(
        prog="jarvis tui",
        description="Textual dashboard for a running JARVIS daemon.",
    )
    parser.add_argument("--mock", action="store_true",
                        help="force mock providers even if a daemon is reachable")
    parser.add_argument("--url", default=None,
                        help="daemon TCP URL override (default: auto-discover)")
    args = parser.parse_args(argv)

    JarvisApp(mock=args.mock, url=args.url).run()
    return 0


def entry() -> None:
    """Console entry point: route `daemon`/`perf`/`tui` before typer, else run the app."""
    if len(sys.argv) > 1 and sys.argv[1] == "daemon":
        sys.exit(daemon_cli(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "perf":
        sys.exit(perf_cli(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "tui":
        sys.exit(tui_cli(sys.argv[2:]))
    app()


# ── interactive command center ──────────────────────────────────────────────

def _print_startup_report() -> None:
    """Print the startup phase report to stderr (keeps --json stdout clean)."""
    from cli.startup_profile import get_profiler

    report = get_profiler().report()
    lines = report.splitlines()
    lines.insert(2, f"  {'import cli.main':<24} {_IMPORT_MS:>7.1f} ms")
    print("\n".join(lines), file=sys.stderr)


def _interactive(mode: str, max_iterations: int, max_tokens: int | None,
                 project_dir: str | None, profile_startup: bool = False) -> None:
    from cli.cockpit import render_cockpit, render_notifications, render_status_bar
    from cli.details import render_expanded
    from cli.startup_profile import get_profiler

    profiler = get_profiler()
    console.clear()
    console.print(Text("JARVIS MK-X — terminal-first agent", style="bold cyan"))
    console.print(Text("/help for commands · /cockpit for the dashboard", style="dim"))

    # Stage A/B split: the banner and prompt appear immediately; the kernel
    # (config, providers, memory) finishes booting in a background thread so
    # the user can start typing while heavy SDKs load.
    holder: dict = {}
    ready = threading.Event()

    def _boot() -> None:
        try:
            profiler.begin_trace()
            try:
                profiler.begin("kernel.boot")
                try:
                    holder["loop"] = _build_loop(mode, max_iterations, max_tokens, project_dir)
                finally:
                    profiler.end("kernel.boot")
            finally:
                profiler.end_trace()
        except Exception as exc:  # pragma: no cover - startup failure path
            holder["error"] = exc
        finally:
            ready.set()

    threading.Thread(target=_boot, daemon=True, name="jarvis-kernel-boot").start()
    console.print(Text("  ⏳ starting kernel…", style="dim"))

    notifications: list = []
    _configure_noise(verbose=False)
    loop = None

    while True:
        if loop is None:
            console.print("JARVIS> ", style="dim", end="")
            sys.stdout.flush()
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not ready.is_set():
                typer.secho("(waiting for kernel startup…)", dim=True)
                try:
                    ready.wait()
                except KeyboardInterrupt:
                    print()
                    break
            loop = holder.get("loop")
            if loop is None:
                typer.secho(f"startup failed: {holder.get('error', 'unknown error')}",
                            err=True, fg="red")
                break
            loop.router.warm()
            console.print(Text("  ✓ kernel ready", style="dim"))
            if profile_startup:
                _print_startup_report()
            console.print(render_status_bar(loop))
            line = line.strip()
        else:
            console.print(render_status_bar(loop))
            try:
                line = input("JARVIS> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
        if not line:
            last = getattr(loop, "_last_result", None)
            if last is not None:
                console.print(render_expanded(last))
            continue

        if line in ("/exit", "/quit"):
            break
        if line == "/help":
            _print_help()
        elif line == "/clear":
            console.clear()
        elif line == "/cockpit":
            console.clear()
            console.print(render_cockpit(loop))
        elif line == "/notifications":
            console.print(render_notifications(notifications))
        elif line == "/verbose":
            _verbose = not getattr(loop, "_verbose", False)
            loop._verbose = _verbose
            _configure_noise(_verbose)
            logging.getLogger().setLevel(logging.INFO if _verbose else logging.WARNING)
            typer.secho(f"backend messages: {'ON' if _verbose else 'OFF'}", fg="green")
        elif line == "/tools":
            for tool in loop.registry.list():
                print(f"  {tool.name} — {tool.description}")
        elif line == "/plan":
            loop.permissions.set_mode("plan")
            notifications.append(("info", "mode → plan (read-only)"))
            typer.secho("mode → plan (read-only)", fg="green")
        elif line == "/mode":
            print(f"mode: {loop.permissions.mode}")
        elif line.startswith("/mode "):
            new_mode = line[6:].strip()
            if new_mode not in _MODES:
                typer.secho(f"Unknown mode '{new_mode}'.", err=True, fg="red")
            else:
                loop.permissions.set_mode(new_mode)
                notifications.append(("info", f"mode → {new_mode}"))
                typer.secho(f"mode → {new_mode}", fg="green")
        elif line == "/model":
            print(f"model={loop.router._last_model} provider={loop.router._last_provider}")
        elif line == "/models":
            _print_models(loop)
        elif line == "/status":
            print(f"provider={loop.router._last_provider} model={loop.router._last_model}")
            print(f"tools: {len(loop.registry.list())} registered")
            print(f"mode: {loop.permissions.mode}")
            if loop.mem is not None:
                print(f"memory: {loop.mem.get_stats()}")
        elif line == "/context":
            _print_context(loop)
        elif line == "/tokens" or line == "/compact":
            _print_context(loop)
        elif line == "/tree":
            _print_tree(loop.project)
        elif line.startswith("/memory"):
            _cmd_memory(loop, line)
        elif line.startswith("/history"):
            _cmd_history(line)
        elif line == "/resume":
            goal = getattr(loop, "_last_goal", None)
            if not goal:
                typer.secho("no previous goal to resume", err=True, fg="red")
            else:
                asyncio.run(_run_once(goal, loop, collapsed=True, notifications=notifications))
        else:
            try:
                asyncio.run(_run_once(line, loop, collapsed=True, notifications=notifications))
            except KeyboardInterrupt:
                typer.secho("(interrupted)", dim=True)
            console.print(render_cockpit(loop))

    if loop is not None:
        loop.logger.flush()


def _print_models(loop) -> None:
    from rich.table import Table

    table = Table(title="Model status")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Available")
    for name, info in loop.router.status.items():
        table.add_row(
            name, info.get("model", ""),
            "yes" if info.get("available") else "no",
        )
    console.print(table)


def _print_context(loop) -> None:
    report = loop.context_manager.last_report
    if report is None:
        print("no context report yet — run a task first")
        return
    data = report.to_dict()
    print(f"[context] {data['total_tokens']}/{data['total_budget']} tokens"
          + (" [compacted]" if data["compacted"] else ""))
    for section in data.get("sections", []):
        bar = "█" * max(0, int(section["ratio"] * 12)) + "░" * max(0, 12 - int(section["ratio"] * 12))
        print(f"  {section['section']:<9} {bar} {section['tokens']}/{section['budget']}")


def _print_tree(project, depth: int = 1) -> None:
    root = project.root_path
    skip = {".git", "venv", "node_modules", "__pycache__", "_quarantine", ".pytest_cache"}
    try:
        children = sorted(root.iterdir())
    except OSError as e:
        print(f"error listing tree: {e}")
        return
    for child in children:
        if child.name.startswith(".") or child.name in skip:
            continue
        if child.is_dir():
            print(f"[dir] {child.name}/")
            if depth and child.is_dir():
                try:
                    subs = sorted(child.iterdir())[:12]
                except OSError:
                    subs = []
                for sub in subs:
                    if sub.name.startswith(".") or sub.name in skip:
                        continue
                    print(f"      {sub.name}")
        else:
            print(f"      {child.name}")


def _cmd_memory(loop, line: str) -> None:
    if loop.mem is None:
        typer.secho("memory disabled in this loop", err=True, fg="red")
        return
    parts = line.split(maxsplit=2)
    if len(parts) == 1:
        print(loop.mem.get_stats())
        return
    action = parts[1]
    if action == "search" and len(parts) == 3:
        for hit in loop.mem.retrieve(parts[2], project=str(loop.project.root_path), top_k=5):
            print(f"[{hit['source']}:{hit['score']:.2f}] {hit['content'][:160]}")
    elif action == "add" and len(parts) == 3:
        key, _, value = parts[2].partition("=")
        print(loop.mem.remember(key.strip() or "note", value.strip(), category="notes"))
    else:
        typer.secho("usage: /memory [search <query> | add <key>=<value>]", err=True, fg="red")


def _cmd_history(line: str) -> None:
    from core.event_store import get_event_store
    store = get_event_store()
    parts = line.split(maxsplit=1)
    task_id = parts[1].strip() if len(parts) == 2 else ""
    if task_id:
        events = store.query(trace_id=task_id, limit=200)
        if not events:
            typer.secho(f"no events for trace {task_id}", err=True, fg="red")
            return
        for event in events:
            ts = datetime.datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
            print(f"{ts} {event.name} {json.dumps(event.data, default=str)[:120]}")
    else:
        traces = store.recent_traces(limit=10)
        if not traces:
            print("no task history yet")
            return
        for trace in traces:
            ts = datetime.datetime.fromtimestamp(trace["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            print(f"{trace['trace_id']}  {ts}")


def _print_help() -> None:
    print("/help           show commands")
    print("/tools          list available tools")
    print("/mode           show current mode")
    print("/mode <m>       switch mode (plan|controlled|smart|agent)")
    print("/plan           switch to read-only plan mode")
    print("/model          show last model + provider")
    print("/models         show all providers")
    print("/status         show provider, mode, memory stats")
    print("/context        show last context budget report")
    print("/tokens         show context usage + compacted flag")
    print("/memory         show memory stats")
    print("/memory search <q>   semantic memory retrieval")
    print("/memory add <k>=<v>  remember a fact")
    print("/history        list recent tasks")
    print("/history <id>   replay a task timeline")
    print("/tree           show project tree")
    print("/resume         re-run the last goal")
    print("/cockpit        heavy diagnostic dashboard (on demand)")
    print("/notifications  rolling event log")
    print("/verbose        toggle backend messages")
    print("/clear          clear screen")
    print("/exit           quit")
    print("")
    print("press Enter on an empty line to expand the last task details")


if __name__ == "__main__":
    entry()
