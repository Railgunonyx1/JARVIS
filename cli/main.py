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

from cli.theme import build_rich_theme

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
warnings.filterwarnings("ignore", category=FutureWarning,
                        message=r"(?s).*google\.generativeai")

app = typer.Typer(add_completion=False)
console = Console(theme=build_rich_theme())

_IMPORT_MS = (time.perf_counter() - _IMPORT_START) * 1000.0

_MODES = ("plan", "controlled", "smart", "agent")


def _configure_noise(verbose: bool) -> None:
    # In interactive mode, never let library loggers write to stderr.
    # All logging goes to file via setup_logging().
    for name, lg in list(logging.root.manager.loggerDict.items()):
        if isinstance(lg, logging.Logger) and not name.startswith("jarvis"):
            lg.setLevel(logging.CRITICAL + 1)  # effectively silenced


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
                project_dir: str | None, confirmation_handler=None):
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
            router=router, registry=registry, project=project,
            mode=mode, max_iterations=max_iterations,
            max_tokens=max_tokens, mem=mem,
            confirmation_handler=confirmation_handler,
        )
    finally:
        profiler.end_trace()


def _status_getter(loop) -> dict:
    return {
        "mode": str(loop.mode),
        "provider": getattr(loop.router, "_last_provider", None),
        "model": getattr(loop.router, "_last_model", None),
    }


def _print_result(result) -> None:
    """Print agent result. Always outputs something — never silent."""
    from cli.renderer import render_markdown

    try:
        if result.success and result.response:
            if sys.stdout.isatty():
                console.print(render_markdown(result.response))
            else:
                print(result.response)
        elif not result.success:
            console.print(Text(f"  error: {result.error[:200]}", style="jarvis.error"))
        else:
            console.print(Text("  (no response)", style="jarvis.dim"))
    except Exception as e:
        console.print(Text(f"  (output error: {e})", style="jarvis.error"))

    if sys.stdout.isatty():
        try:
            from cli.details import render_summary
            console.print(Text(f"  {render_summary(result)}", style="dim"))
        except Exception:
            pass


def _print_collapsed(result) -> None:
    """Print result after Live display stops."""
    _print_result(result)


def _capture_notification(name: str, payload: dict, notifications: list) -> None:
    """Map observer events to the rolling notification log."""
    if name == "run.queued":
        notifications.append(("warn", "queued — a previous task is still running"))
    elif name == "task.finished":
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
                    perf: bool = False, bridge=None, screen: bool = False) -> None:
    from cli.ux import LiveTaskDisplay

    loop._last_goal = goal
    notifications = notifications if notifications is not None else []
    renderer = getattr(bridge, "renderer", None) if bridge is not None else None
    display = LiveTaskDisplay(
        status_getter=(lambda: _status_getter(loop)),
        enable=not json_output and not collapsed,
        renderable_provider=(renderer.render_task_screen if renderer is not None else None),
        screen=screen,
        transient=not collapsed,
    )

    def _on_event(name: str, payload: dict) -> None:
        _capture_notification(name, payload, notifications)
        if bridge is not None:
            bridge.on_event(name, payload)
        if not json_output:
            display._on_event(name, payload)

    if bridge is not None:
        bridge.start_run(goal)
    if not json_output:
        display.attach(loop.observer)
        if renderer is not None:
            renderer.attach_live(display)
    loop.observer.on_event = _on_event
    if not json_output:
        display.start()
    try:
        if bridge is not None:
            async def _on_chunk(delta: str) -> None:
                bridge.stream_delta(delta)
                if not json_output:
                    display.stream_delta(delta)
            result = await loop.run(goal, on_chunk=_on_chunk)
        else:
            result = await loop.run(goal)
    except Exception as exc:
        if bridge is not None:
            bridge.fail_run(str(exc))
        raise
    finally:
        display.stop()
        if renderer is not None:
            renderer.detach_live()
        # Force a clean newline after Live display stops to prevent
        # transient=True from eating the output.
        console.line()

    loop._last_result = result
    if bridge is not None:
        bridge.finish_run(result)
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
        loop = _build_loop(mode, max_iterations, max_tokens, project_dir)
        asyncio.run(_run_once(goal, loop, json_output=json_output, perf=perf))
        if profile_startup:
            _print_startup_report()
    else:
        _interactive(mode, max_iterations, max_tokens, project_dir,
                     profile_startup=profile_startup)


# ── execution backend ──────────────────────────────────────────────────

def _resolve_project_dir(project_dir: str | None) -> str:
    return str((Path(project_dir) if project_dir else Path.cwd()).resolve())


def _print_perf_trace(result) -> None:
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


def perf_cli(argv) -> int:
    import argparse
    from runtime.observability.dashboard import render_summary, render_trace, trace_table
    from runtime.observability.exporters import perf_db_path, read_latest, read_slowest, read_summary

    parser = argparse.ArgumentParser(prog="jarvis perf", description="Show persisted JARVIS performance data.")
    sub = parser.add_subparsers(dest="action")
    latest = sub.add_parser("latest", help="most recent request traces")
    latest.add_argument("-n", type=int, default=5)
    slowest = sub.add_parser("slowest", help="slowest request traces")
    slowest.add_argument("-n", type=int, default=5)
    sub.add_parser("summary", help="aggregate phase timings and counters")
    args = parser.parse_args(argv)

    path = perf_db_path()
    if not path.exists():
        print("no performance data yet — run a request first", file=sys.stderr)
        print(f"(db: {path})", file=sys.stderr)
        return 1

    if args.action == "slowest":
        traces = read_slowest(path, limit=args.n)
        print(trace_table(traces))
        for trace in traces:
            print(render_trace(trace))
    elif args.action == "latest":
        traces = read_latest(path, limit=args.n)
        print(trace_table(traces))
        for trace in traces:
            print(render_trace(trace))
    else:
        print(render_summary(read_summary(path)))
        for trace in read_latest(path, limit=3):
            print(render_trace(trace))
    return 0


def entry() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "perf":
        sys.exit(perf_cli(sys.argv[2:]))
    app()


# ── interactive command center ──────────────────────────────────────────────

def _print_startup_report() -> None:
    from cli.startup_profile import get_profiler
    report = get_profiler().report()
    lines = report.splitlines()
    lines.insert(2, f"  {'import cli.main':<24} {_IMPORT_MS:>7.1f} ms")
    print("\n".join(lines), file=sys.stderr)


def _interactive(mode: str, max_iterations: int, max_tokens: int | None,
                 project_dir: str | None, profile_startup: bool = False) -> None:
    from cli.bridge import AgentBridge
    from cli.cockpit import render_cockpit, render_notifications
    from cli.commands import CommandRegistry
    from cli.details import render_expanded
    from cli.history import HistoryStore
    from cli.input import InputReader, PaletteRequest
    from cli.renderer import Renderer
    from cli.startup_profile import get_profiler

    profiler = get_profiler()
    # No startup banner — the conversation IS the UI.

    bridge = AgentBridge(renderer=Renderer(console=console))
    commands = CommandRegistry(bridge.renderer, bridge=bridge)
    holder: dict = {}
    ready = threading.Event()

    def _boot() -> None:
        try:
            profiler.begin_trace()
            try:
                profiler.begin("kernel.boot")
                try:
                    holder["loop"] = _build_loop(
                        mode, max_iterations, max_tokens, project_dir,
                        confirmation_handler=bridge.confirmation_call,
                    )
                finally:
                    profiler.end("kernel.boot")
            finally:
                profiler.end_trace()
        except Exception as exc:
            holder["error"] = exc
        finally:
            ready.set()

    threading.Thread(target=_boot, daemon=True, name="jarvis-kernel-boot").start()

    notifications: list = []
    _configure_noise(verbose=False)
    loop = None

    history = HistoryStore()
    reader = InputReader()
    reader.set_history(history.to_list())

    def _read_command() -> str:
        mode = str(loop.mode).lower() if loop else "agent"
        prompt = f"JARVIS [{mode}] > "
        while True:
            try:
                return reader.read_line(prompt)
            except PaletteRequest:
                try:
                    commands.dispatch("/palette")
                except SystemExit:
                    raise

    while True:
        if loop is None:
            try:
                line = _read_command()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            line = line.strip()
            history.add(line)
            history.save()
            if not ready.is_set():
                try:
                    ready.wait()
                except KeyboardInterrupt:
                    print()
                    break
            loop = holder.get("loop")
            if loop is None:
                console.print(Text(f"  startup failed: {holder.get('error', 'unknown')}", style="jarvis.error"))
                break
            bridge.attach_loop(loop)
            bridge.pull_status()
            loop.router.warm()
            if profile_startup:
                _print_startup_report()
        else:
            try:
                line = _read_command().strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            history.add(line)
            history.save()
        if not line:
            last = getattr(loop, "_last_result", None)
            if last is not None:
                console.print(render_expanded(last))
            continue

        if line in ("/exit", "/quit"):
            break
        if line == "/clear":
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
            console.print(Text(f"  backend: {'ON' if _verbose else 'OFF'}", style="jarvis.success"))
        elif line == "/plan":
            loop.set_mode("plan")
            bridge.pull_status()
            notifications.append(("info", "mode -> plan"))
            console.print(Text("  mode -> plan", style="jarvis.success"))
        elif line == "/tokens" or line == "/compact":
            _print_context(loop)
        elif line == "/tree":
            _print_tree(loop.project)
        elif line.startswith("/history"):
            _cmd_history(line)
        elif line == "/resume":
            goal = getattr(loop, "_last_goal", None)
            if not goal:
                console.print(Text("  no previous goal", style="jarvis.error"))
            else:
                try:
                    asyncio.run(_run_once(goal, loop, collapsed=True, notifications=notifications, bridge=bridge, screen=False))
                except Exception as exc:
                    console.print(Text(f"  error: {exc}", style="jarvis.error"))
        elif line.startswith("/"):
            commands.dispatch(line)
        else:
            try:
                asyncio.run(_run_once(line, loop, collapsed=True, notifications=notifications, bridge=bridge, screen=False))
            except KeyboardInterrupt:
                console.print(Text("  (interrupted)", style="dim"))
            except Exception as exc:
                console.print(Text(f"  error: {exc}", style="jarvis.error"))

    if loop is not None:
        loop.logger.flush()
    history.save()


def _print_models(loop) -> None:
    from rich.table import Table
    table = Table(title="Model status")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Available")
    for name, info in loop.router.status.items():
        table.add_row(name, info.get("model", ""), "yes" if info.get("available") else "no")
    console.print(table)


def _print_context(loop) -> None:
    report = loop.context_manager.last_report
    if report is None:
        console.print(Text("  no context yet", style="dim"))
        return
    data = report.to_dict()
    console.print(Text(f"  {data['total_tokens']}/{data['total_budget']} tokens"
                       + (" [compacted]" if data["compacted"] else ""), style="dim"))
    for section in data.get("sections", []):
        bar = "#" * max(0, int(section["ratio"] * 12)) + "-" * max(0, 12 - int(section["ratio"] * 12))
        console.print(Text(f"    {section['section']:<9} {bar} {section['tokens']}/{section['budget']}", style="dim"))


def _print_tree(project, depth: int = 1) -> None:
    root = project.root_path
    skip = {".git", "venv", "node_modules", "__pycache__", "_quarantine", ".pytest_cache"}
    try:
        children = sorted(root.iterdir())
    except OSError as e:
        console.print(Text(f"  error: {e}", style="jarvis.error"))
        return
    for child in children:
        if child.name.startswith(".") or child.name in skip:
            continue
        if child.is_dir():
            console.print(Text(f"  {child.name}/", style="jarvis.accent"))
            if depth and child.is_dir():
                try:
                    subs = sorted(child.iterdir())[:12]
                except OSError:
                    subs = []
                for sub in subs:
                    if sub.name.startswith(".") or sub.name in skip:
                        continue
                    console.print(Text(f"    {sub.name}", style="jarvis.dim"))
        else:
            console.print(Text(f"    {child.name}", style="jarvis.dim"))


def _cmd_memory(loop, line: str) -> None:
    if loop.mem is None:
        console.print(Text("  memory disabled", style="jarvis.error"))
        return
    parts = line.split(maxsplit=2)
    if len(parts) == 1:
        console.print(Text(f"  {loop.mem.get_stats()}", style="dim"))
        return
    action = parts[1]
    if action == "search" and len(parts) == 3:
        for hit in loop.mem.retrieve(parts[2], project=str(loop.project.root_path), top_k=5):
            console.print(Text(f"  [{hit['source']}:{hit['score']:.2f}] {hit['content'][:160]}", style="dim"))
    elif action == "add" and len(parts) == 3:
        key, _, value = parts[2].partition("=")
        console.print(Text(f"  {loop.mem.remember(key.strip() or 'note', value.strip(), category='notes')}", style="dim"))
    else:
        console.print(Text("  usage: /memory [search <q> | add <k>=<v>]", style="jarvis.error"))


def _cmd_audit(line: str, limit_default: int = 12) -> None:
    from security.audit import get_audit_log
    parts = line.split(maxsplit=1)
    args = parts[1].strip() if len(parts) == 2 else ""
    log = get_audit_log()
    stats = log.get_stats()
    console.print(Text(f"  {stats['total_actions']} actions | {stats['denied']} denied | {stats['failed']} failed", style="dim"))
    if stats["top_tools"]:
        top = ", ".join(f"{k}={v}" for k, v in list(stats["top_tools"].items())[:5])
        console.print(Text(f"  top: {top}", style="dim"))
    if args.startswith("trace "):
        trace_id = args[6:].strip()
        entries = log.query_trace(trace_id)
        if not entries:
            console.print(Text(f"  no entries for trace {trace_id}", style="jarvis.error"))
            return
        for e in entries:
            ts = datetime.datetime.fromtimestamp(e["timestamp"]).strftime("%H:%M:%S")
            ok = "ok" if e["success"] else "fail"
            flag = "" if e["allowed"] else " DENIED"
            console.print(Text(f"  {ts} {e['tool'] or e['action']:<28} {ok}{flag} {e['duration_ms']:.0f}ms", style="dim"))
        return
    limit = limit_default
    tool = args or None
    if args.isdigit():
        limit = int(args)
        tool = None
    entries = log.query(tool=tool, limit=limit)
    if not entries:
        console.print(Text("  no audit entries", style="dim"))
        return
    for e in entries:
        ts = datetime.datetime.fromtimestamp(e["timestamp"]).strftime("%H:%M:%S")
        ok = "ok" if e["success"] else "fail"
        flag = "" if e["allowed"] else " DENIED"
        console.print(Text(f"  {ts} {e['tool'] or e['action']:<28} {ok}{flag} {e['duration_ms']:.0f}ms", style="dim"))


def _cmd_history(line: str) -> None:
    from core.event_store import get_event_store
    store = get_event_store()
    parts = line.split(maxsplit=1)
    task_id = parts[1].strip() if len(parts) == 2 else ""
    if task_id:
        events = store.query(trace_id=task_id, limit=200)
        if not events:
            console.print(Text(f"  no events for trace {task_id}", style="jarvis.error"))
            return
        for event in events:
            ts = datetime.datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
            console.print(Text(f"  {ts} {event.name} {json.dumps(event.data, default=str)[:120]}", style="dim"))
    else:
        traces = store.recent_traces(limit=10)
        if not traces:
            console.print(Text("  no history yet", style="dim"))
            return
        for trace in traces:
            ts = datetime.datetime.fromtimestamp(trace["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            console.print(Text(f"  {trace['trace_id']}  {ts}", style="dim"))
