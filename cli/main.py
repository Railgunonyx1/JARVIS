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
# The deprecated google.generativeai SDK warns via a stacklevel that points at
# importlib, so module-scoped filters never match — filter on the message text.
warnings.filterwarnings("ignore", category=FutureWarning,
                        message=r"(?s).*google\.generativeai")

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
            router=router,
            registry=registry,
            project=project,
            mode=mode,
            max_iterations=max_iterations,
            max_tokens=max_tokens,
            mem=mem,
            confirmation_handler=confirmation_handler,
        )
    finally:
        profiler.end_trace()


def _status_getter(loop) -> dict:
    return {
        "mode": str(loop.permissions.mode),
        "provider": getattr(loop.router, "_last_provider", None),
        "model": getattr(loop.router, "_last_model", None),
    }


def _emit_response(text: str) -> None:
    """Print an assistant response: Markdown on an interactive terminal, plain
    otherwise (pipes, tests) so machine-readable output stays byte-exact."""
    if sys.stdout.isatty():
        from cli.renderer import render_markdown
        console.print(render_markdown(text))
    else:
        print(text)


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
        _emit_response(result.response)
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
        _emit_response(result.response)
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
        enable=not json_output,
        renderable_provider=(renderer.render_task_screen if renderer is not None else None),
        screen=screen,
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


# ── transport (in-process only; no daemon) ───────────────────────────────────

def _resolve_project_dir(project_dir: str | None) -> str:
    return str((Path(project_dir) if project_dir else Path.cwd()).resolve())


def _render_status_bar_dict(status: dict) -> Text:
    """Status-bar line rendered from an engine status dict."""
    bits = [Text("JARVIS", style="bold cyan")]
    bits.append(Text(f"mode={status.get('mode', 'agent')}", style="green"))
    if status.get("provider"):
        label = f"{status.get('model')}/{status.get('provider')}"
        if len(label) > 30:
            label = label[:28] + "…"
        bits.append(Text(label, style="magenta"))
    bits.append(Text(f"tools={status.get('tools', 0)}", style="yellow"))
    mem = status.get("mem_stats") or {}
    if mem:
        bits.append(Text(f"mem={mem.get('decisions', 0)}d/{mem.get('knowledge', 0)}k", style="dim"))
    if status.get("busy"):
        bits.append(Text("busy", style="bold red blink"))
    bits.append(Text(f"time={datetime.datetime.now().strftime('%H:%M:%S')}", style="dim"))
    return Text("  │  ").join(bits)


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


def perf_cli(argv) -> int:
    """`jarvis perf [latest|slowest|summary]` — read persisted performance data.

    Opens its own read-only connection to the performance SQLite database
    (WAL-safe), written on every request via ``runtime.observability.exporters``.
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
        print("no performance data yet — run a request first", file=sys.stderr)
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


def entry() -> None:
    """Console entry point: route `perf` before typer, else run the app."""
    if len(sys.argv) > 1 and sys.argv[1] == "perf":
        sys.exit(perf_cli(sys.argv[2:]))
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
    from cli.bridge import AgentBridge
    from cli.cockpit import render_cockpit, render_notifications, render_status_bar
    from cli.commands import CommandRegistry
    from cli.details import render_expanded
    from cli.history import HistoryStore
    from cli.input import InputReader, PaletteRequest
    from cli.renderer import Renderer
    from cli.startup_profile import get_profiler

    profiler = get_profiler()
    console.clear()
    console.print(Text("JARVIS MK-X — terminal-first agent", style="bold cyan"))
    console.print(Text("/help for commands · /cockpit for the dashboard", style="dim"))

    # The Event/State Bus owns the engine→UI contract for the whole session.
    bridge = AgentBridge(renderer=Renderer(console=console))
    commands = CommandRegistry(bridge.renderer, bridge=bridge)
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
                    holder["loop"] = _build_loop(
                        mode, max_iterations, max_tokens, project_dir,
                        confirmation_handler=bridge.confirmation_call,
                    )
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

    history = HistoryStore()
    reader = InputReader()
    reader.set_history(history.to_list())

    def _read_command(prompt: str = "JARVIS> ") -> str:
        """Read a line; Ctrl+K opens the command palette and re-prompts."""
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
            bridge.attach_loop(loop)
            bridge.pull_status()
            loop.router.warm()
            console.print(Text("  ✓ kernel ready", style="dim"))
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
            typer.secho(f"backend messages: {'ON' if _verbose else 'OFF'}", fg="green")
        elif line == "/plan":
            loop.permissions.set_mode("plan")
            bridge.pull_status()
            notifications.append(("info", "mode → plan (read-only)"))
            typer.secho("mode → plan (read-only)", fg="green")
        elif line == "/tokens" or line == "/compact":
            _print_context(loop)
        elif line == "/tree":
            _print_tree(loop.project)
        elif line.startswith("/history"):
            _cmd_history(line)
        elif line == "/resume":
            goal = getattr(loop, "_last_goal", None)
            if not goal:
                typer.secho("no previous goal to resume", err=True, fg="red")
            else:
                try:
                    asyncio.run(_run_once(goal, loop, collapsed=True, notifications=notifications, bridge=bridge, screen=True))
                except Exception as exc:
                    typer.secho(f"error: {exc}", err=True, fg="red")
        elif line.startswith("/"):
            # The v2 command registry owns every other slash command; it talks
            # to the engine exclusively through the bridge.
            commands.dispatch(line)
        else:
            try:
                asyncio.run(_run_once(line, loop, collapsed=True, notifications=notifications, bridge=bridge, screen=True))
            except KeyboardInterrupt:
                typer.secho("(interrupted)", dim=True)
            except Exception as exc:
                typer.secho(f"error: {exc}", err=True, fg="red")

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


def _cmd_audit(line: str, limit_default: int = 12) -> None:
    """`/audit [trace <id> | <n> | <tool>]` — read the security audit log
    (stats + recent actions + per-trace replay). Reads the shared
    ``~/.jarvis/data/audit.db``."""
    from security.audit import get_audit_log

    parts = line.split(maxsplit=1)
    args = parts[1].strip() if len(parts) == 2 else ""
    log = get_audit_log()
    stats = log.get_stats()
    print(f"audit: {stats['total_actions']} actions · "
          f"{stats['denied']} denied · {stats['failed']} failed")
    if stats["top_tools"]:
        top = ", ".join(f"{k}={v}" for k, v in list(stats["top_tools"].items())[:5])
        print(f"top tools: {top}")
    if args.startswith("trace "):
        trace_id = args[6:].strip()
        entries = log.query_trace(trace_id)
        if not entries:
            typer.secho(f"no audit entries for trace {trace_id}", err=True, fg="red")
            return
        for e in entries:
            ts = datetime.datetime.fromtimestamp(e["timestamp"]).strftime("%H:%M:%S")
            ok = "ok" if e["success"] else "fail"
            flag = "" if e["allowed"] else " DENIED"
            print(f"{ts} {e['tool'] or e['action']:<28} {ok}{flag} "
                  f"{e['duration_ms']:.0f}ms {e.get('session_id', '')[:8]}")
        return
    limit = limit_default
    tool = args or None
    if args.isdigit():
        limit = int(args)
        tool = None
    entries = log.query(tool=tool, limit=limit)
    if not entries:
        print("no audit entries yet")
        return
    for e in entries:
        ts = datetime.datetime.fromtimestamp(e["timestamp"]).strftime("%H:%M:%S")
        ok = "ok" if e["success"] else "fail"
        flag = "" if e["allowed"] else " DENIED"
        print(f"{ts} {e['tool'] or e['action']:<28} {ok}{flag} "
              f"{e['duration_ms']:.0f}ms {e.get('session_id', '')[:8]}")


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
    print("/audit          security audit log (stats + recent actions)")
    print("/audit trace <id>   replay an audit trace")
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
