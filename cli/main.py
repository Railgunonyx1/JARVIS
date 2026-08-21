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
logger = logging.getLogger("jarvis.cli")

_IMPORT_MS = (time.perf_counter() - _IMPORT_START) * 1000.0

_MODES = ("plan", "controlled", "smart", "agent")


def _configure_noise(verbose: bool) -> None:
    # Library loggers: silenced unless verbose mode is on.
    # All jarvis loggers go to file via setup_logging(); these affect stderr.
    level = logging.NOTSET if verbose else logging.CRITICAL + 1
    for name, lg in list(logging.root.manager.loggerDict.items()):
        if isinstance(lg, logging.Logger) and not name.startswith("jarvis"):
            lg.setLevel(level)


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
    """Print result after agent finishes. Uses console.print to ensure
    Rich terminal state is correct. Always outputs something."""
    from cli.renderer import render_markdown
    try:
        if result and result.success and result.response:
            # Start on a fresh line so the response doesn't jam against the
            # Live display's footer prompt (e.g. 'JARVIS [agent] > _').
            print()  # newline separator
            console.print(render_markdown(result.response))
            console.print()
        elif result and not result.success:
            err = getattr(result, 'error', 'unknown error')
            console.print(Text(f"  error: {err[:200]}", style="jarvis.error"))
        else:
            console.print(Text("  (no response)", style="jarvis.dim"))
    except Exception as e:
        console.print(Text(f"  (output error: {e})", style="jarvis.error"))


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

    global _main_task_running
    loop._last_goal = goal
    loop._last_task_id = f"task_{int(time.time())}"
    _main_task_running = True
    _cancel_event = asyncio.Event()  # Set to cancel the current task gracefully
    notifications = notifications if notifications is not None else []
    renderer = getattr(bridge, "renderer", None) if bridge is not None else None
    # Live display is ALWAYS enabled (except --json pipe mode).
    # In interactive mode: transient=False shows the Claude-style UI during
    # execution AND keeps the conversation visible after stop.
    # The final result is also printed below by _print_collapsed.
    # In one-shot mode: transient=False keeps the full conversation on screen.
    use_live = not json_output
    display = LiveTaskDisplay(
        status_getter=(lambda: _status_getter(loop)),
        enable=use_live,
        renderable_provider=(renderer.render_task_screen if renderer is not None else None),
        screen=screen,
        transient=False,
    )

    def _on_event(name: str, payload: dict) -> None:
        _capture_notification(name, payload, notifications)
        if bridge is not None:
            bridge.on_event(name, payload)
        if use_live:
            display._on_event(name, payload)

    if bridge is not None:
        bridge.start_run(goal)
    if use_live:
        display.attach(loop.observer)
        if renderer is not None:
            renderer.attach_live(display)
    loop.observer.on_event = _on_event
    if use_live:
        display.start()
    # Cascade routing: confidence-based with draft-then-verify
    # 1B handles simple tasks directly, 3B handles tools, 4B for complex.
    # Medium-confidence tasks: 1B drafts, then 3B verifies.
    _cascade = None
    _draft_first = False
    try:
        from core.agent.loop import AgentResult
        from providers.model_registry import ModelRegistry
        _registry = ModelRegistry.instance()
        if _registry.cascade_mode:
            _cascade = _registry.resolve_cascade(goal)
            _draft_first = _cascade.get("draft_first", False)
            if _cascade.get("deterministic"):
                # Deterministic command — skip LLM, handle inline
                logger.info("Deterministic command: %s", goal[:60])
                result = AgentResult(
                    success=True, response="", trace_id="", state=None,
                    error="deterministic_command",
                )
                if use_live:
                    display.stop()
                _print_collapsed(result)
                sys.stdout.flush()
                return
            _worker = _cascade.get("worker") or _cascade.get("heavy")
            if _worker:
                loop._preferred_model = _worker
                logger.info("Cascade: %s (conf=%.2f) → %s for: %s",
                            _cascade["task_type"], _cascade["confidence"],
                            _worker, goal[:60])
        else:
            _resolved = _registry.resolve_model(goal)
            if _resolved:
                loop._preferred_model = _resolved
                logger.info("Auto-routed to %s for: %s", _resolved, goal[:60])
    except Exception:
        pass  # Auto-routing is best-effort
    try:
        if _draft_first:
            # Draft-then-verify: 1B generates draft, 3B verifies/fixes
            # First run with 1B router to get a draft
            _router_model = _cascade.get("router") or "qwen2.5:1.5b"
            loop._preferred_model = _router_model
            logger.info("Draft phase: using %s for initial draft", _router_model)
            if bridge is not None:
                async def _on_chunk_draft(delta: str) -> None:
                    bridge.stream_delta(delta)
                    if use_live:
                        display.stream_delta(delta)
                draft_result = await loop.run(goal, on_chunk=_on_chunk_draft)
            else:
                draft_result = await loop.run(goal)
            # If 1B produced a text response, pass it to 3B for verification
            if draft_result.success and draft_result.response:
                _verify_model = _cascade.get("worker")
                if _verify_model:
                    loop._preferred_model = _verify_model
                    logger.info("Verify phase: using %s to check draft", _verify_model)
                verify_goal = (
                    f"Here is a draft response to the user's request. "
                    f"Verify it is correct, fix any issues, and return the improved version.\n\n"
                    f"User request: {goal}\n\nDraft response:\n{draft_result.response}\n\n"
                    f"Please verify and return the corrected response."
                )
                if bridge is not None:
                    async def _on_chunk_verify(delta: str) -> None:
                        bridge.stream_delta(delta)
                        if use_live:
                            display.stream_delta(delta)
                    result = await loop.run(verify_goal, on_chunk=_on_chunk_verify)
                else:
                    result = await loop.run(verify_goal)
            else:
                result = draft_result
        else:
            if bridge is not None:
                async def _on_chunk(delta: str) -> None:
                    bridge.stream_delta(delta)
                    if use_live:
                        display.stream_delta(delta)
                result = await loop.run(goal, on_chunk=_on_chunk)
            else:
                result = await loop.run(goal)
    except Exception as exc:
        if bridge is not None:
            bridge.fail_run(str(exc))
        console.print(Text(f"  error: {str(exc)[:200]}", style="jarvis.error"))
        raise
    finally:
        _main_task_running = False
        if use_live:
            display.stop()
            if renderer is not None:
                renderer.detach_live()
            # After Live stops: transient=True cleared the screen.
            # Print the final result so the user sees it.
            if collapsed and 'result' in dir():
                pass  # will print below
        sys.stderr.flush()

    loop._last_result = result
    # Record performance for adaptive routing
    try:
        from providers.model_registry import ModelRegistry
        _perf_registry = ModelRegistry.instance()
        _model_used = result.state.model if result.state else "unknown"
        _latency = 0.0
        if result.perf and "spans" in result.perf:
            for span in result.perf["spans"]:
                if span.get("name") == "provider.complete":
                    _latency = span.get("duration_ms", 0.0)
                    break
        _perf_registry.record_performance(
            model=_model_used, success=result.success,
            latency_ms=_latency,
        )
    except Exception:
        pass  # Performance recording is best-effort
    if bridge is not None:
        bridge.finish_run(result)
    if json_output:
        payload = result.to_dict()
        state = payload.pop("state", {})
        print(json.dumps({"goal": goal, **state, **payload}, indent=2, default=str))
    elif collapsed:
        # transient=True cleared the Live display. Print the final result.
        _print_collapsed(result)
        sys.stdout.flush()
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
    max_iterations: int = typer.Option(20, help="Maximum agent loop iterations."),
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


# Interrupt executor globals (initialized in _interactive after kernel boots)
_interrupt_executor = None
_interrupt_classifier = None
_main_task_running = False


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
            # Wire router rate-limit events to the UI via the observer
            loop.router.on_provider_event = lambda name, payload: (
                getattr(loop.observer, 'on_event', lambda n, p: None)(name, payload)
            )
            loop.router.warm()
            # Initialize interrupt executor for parallel lightweight queries
            global _interrupt_executor, _interrupt_classifier, _main_task_running
            try:
                from core.agent.lanes import InterruptExecutor, RequestClassifier
                _interrupt_classifier = RequestClassifier()
                _interrupt_executor = InterruptExecutor(
                    router=loop.router,
                    registry=loop.registry,
                    mem=loop.mem,
                    project=loop.project,
                )
            except Exception:
                _interrupt_classifier = None
                _interrupt_executor = None
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
        elif line.startswith("/remember "):
            _cmd_remember(line, loop)
        elif line == "/memory":
            _cmd_memory_list(loop)
        elif line.startswith("/model"):
            _cmd_model(line, loop)
        elif line == "/providers":
            _cmd_providers(loop)
        elif line == "/status":
            _cmd_status(loop)
        elif line == "/memory prompt":
            _cmd_memory_prompt(loop)
        elif line == "/cancel":
            _cmd_cancel(loop)
        elif line.startswith("/"):
            commands.dispatch(line)
        else:
            # Check if this is an interrupt (lightweight query while main task runs)
            _is_interrupt = False
            if _main_task_running and _interrupt_classifier is not None:
                _classification = _interrupt_classifier.classify(
                    line,
                    active_task_id=getattr(loop, '_last_task_id', None),
                    active_task_status="executing",
                )
                if _classification.lane.value == "interrupt":
                    _is_interrupt = True
                    try:
                        _result = asyncio.run(_interrupt_executor.execute(
                            line, _classification
                        ))
                        if _result["success"]:
                            console.print(Text(f"  {_result['response']}", style="cyan"))
                            console.print(Text(f"  (interrupt · {_result['latency_ms']:.0f}ms · 1B)", style="dim"))
                        else:
                            err = _result.get("error", "no response")
                            console.print(Text(f"  interrupt error: {err}", style="jarvis.error"))
                    except Exception as exc:
                        console.print(Text(f"  interrupt error: {exc}", style="jarvis.error"))
            if not _is_interrupt:
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


def _cmd_remember(line: str, loop) -> None:
    """Store a memory: /remember key = value [category]"""
    parts = line.split(None, 1)
    if len(parts) < 2:
        console.print(Text("  usage: /remember key = value [category]", style="jarvis.error"))
        return
    arg = parts[1].strip()
    if '=' not in arg:
        console.print(Text("  usage: /remember key = value [category]", style="jarvis.error"))
        return
    key, _, rest = arg.partition('=')
    key = key.strip()
    rest = rest.strip()
    # Split value and optional category
    tokens = rest.split()
    category = 'notes'
    if len(tokens) > 1 and tokens[-1] in ('identity', 'priorities', 'preferences', 'notes', 'project'):
        category = tokens.pop()
    value = ' '.join(tokens)
    if not key or not value:
        console.print(Text("  usage: /remember key = value [category]", style="jarvis.error"))
        return
    if loop.mem is not None:
        loop.mem.remember(key, value, category=category)
        console.print(Text(f"  remembered: {category}/{key} = {value}", style="jarvis.success"))
    else:
        console.print(Text("  memory disabled", style="jarvis.error"))


def _cmd_providers(loop) -> None:
    """Show provider status, latency, and availability."""
    from rich.table import Table
    table = Table(title="Provider Status")
    table.add_column("Provider", style="bold")
    table.add_column("Model")
    table.add_column("Status")
    table.add_column("Latency")
    table.add_column("Errors")
    for name, info in loop.router.status.items():
        available = info.get("available", False)
        status_style = "green" if available else "red"
        status_text = "online" if available else "offline"
        latency = info.get("latency_ms", 0)
        errors = info.get("errors", 0)
        table.add_row(
            name,
            info.get("model", "-")[:30],
            Text(status_text, style=status_style),
            f"{latency:.0f}ms" if latency else "-",
            str(errors) if errors else "0",
        )
    console.print(table)


def _cmd_status(loop) -> None:
    """Show quick system status."""
    from rich.table import Table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value")
    # Mode
    mode = str(loop.mode).lower()
    table.add_row("Mode", Text(mode, style="cyan"))
    # Provider/model
    provider = getattr(loop.router, "_last_provider", "-")
    model = getattr(loop.router, "_last_model", "-")
    table.add_row("Provider", provider or "-")
    table.add_row("Model", (model or "-")[:40])
    # Memory
    if loop.mem is not None:
        try:
            stats = loop.mem.get_stats()
            kv_count = stats.get("kv_count", stats.get("memories", "?"))
            table.add_row("Memories", str(kv_count))
        except Exception:
            table.add_row("Memories", "?")
    # Cascade
    try:
        from providers.model_registry import ModelRegistry
        reg = ModelRegistry.instance()
        cascade_status = "on" if reg.cascade_mode else "off"
        table.add_row("Cascade", cascade_status)
        if reg.cascade_mode:
            table.add_row("  Router", reg.CASCADE_ROUTER)
            table.add_row("  Worker", reg.CASCADE_WORKER)
            table.add_row("  Heavy", reg.CASCADE_HEAVY)
    except Exception:
        pass
    # Runtime
    try:
        from core.agent.runtime import get_runtime
        rt = get_runtime()
        rt_status = rt.get_status()
        table.add_row("Main task", "running" if rt_status["main_running"] else "idle")
        table.add_row("Interrupts", "running" if rt_status["interrupt_running"] else "idle")
    except Exception:
        pass
    console.print(table)


def _cmd_memory_prompt(loop) -> None:
    """Show the formatted memory section that gets injected into the system prompt."""
    if loop.mem is None:
        console.print(Text("  memory disabled", style="jarvis.error"))
        return
    try:
        prompt = loop.mem.format_for_prompt(str(loop.project.root_path))
        if not prompt:
            console.print(Text("  (empty memory prompt)", style="dim"))
        else:
            console.print(Text("  Memory prompt:", style="jarvis.accent"))
            for line in prompt.split("\n"):
                console.print(Text(f"  {line}", style="dim"))
    except Exception as e:
        console.print(Text(f"  error: {e}", style="jarvis.error"))


def _cmd_cancel(loop) -> None:
    """Cancel the current running task."""
    try:
        from core.agent.runtime import get_runtime
        rt = get_runtime()
        if rt.is_main_running:
            rt.cancel_main()
            console.print(Text("  task cancelled", style="jarvis.success"))
        else:
            console.print(Text("  no task running", style="dim"))
    except Exception:
        console.print(Text("  cancel not available", style="jarvis.error"))


def _cmd_memory_list(loop) -> None:
    """Show recent memories."""
    if loop.mem is None:
        console.print(Text("  memory disabled", style="jarvis.error"))
        return
    recent = loop.mem._kv.recent(limit=12) if hasattr(loop.mem, '_kv') and loop.mem._kv else []
    if not recent:
        console.print(Text("  no memories stored", style="jarvis.dim"))
        return
    console.print(Text("  Memory:", style="jarvis.accent"))
    for r in recent:
        cat = r.get('category', 'general')
        key = r.get('key', '?')
        val = str(r.get('value', ''))[:60]
        console.print(Text(f"    [{cat}] {key}: {val}", style="jarvis.dim"))


def _cmd_model(line: str, loop) -> None:
    """Switch models: /model [name|auto|status|list]."""
    from rich.table import Table

    from providers.model_registry import MODEL_CATALOG, ModelRegistry

    registry = ModelRegistry.instance()
    parts = line.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if arg == "list" or arg == "":
        # Show available models
        table = Table(title="Available Models")
        table.add_column("Model", style="bold")
        table.add_column("Size")
        table.add_column("Speed")
        table.add_column("Strengths")
        table.add_column("Description", max_width=40)
        active = registry.active_model or loop.router.get_ollama_model() or ""
        for m in MODEL_CATALOG:
            is_active = m.name == active
            marker = " ●" if is_active else ""
            style = "jarvis.accent" if is_active else None
            table.add_row(
                f"{m.name}{marker}",
                f"{m.size_gb:.1f} GB",
                m.speed,
                ", ".join(s.value for s in m.strengths),
                m.description,
                style=style,
            )
        console.print(table)
        mode_str = "auto" if registry.auto_mode else f"locked to {registry.active_model}"
        console.print(Text(f"  Mode: {mode_str}", style="jarvis.dim"))
        return

    if arg == "status":
        status = registry.get_status()
        console.print(Text(f"  Active: {status['active_model'] or 'auto'}", style="jarvis.accent"))
        console.print(Text(f"  Auto: {status['auto_mode']}", style="jarvis.dim"))
        console.print(Text(f"  Cascade: {status['cascade_mode']}", style="jarvis.dim"))
        if status["cascade_mode"]:
            console.print(Text(f"    Router: {status['cascade_router']} (ultra-fast, simple tasks)", style="jarvis.dim"))
            console.print(Text(f"    Worker: {status['cascade_worker']} (coding, tools, reasoning)", style="jarvis.dim"))
            console.print(Text(f"    Heavy:  {status['cascade_heavy']} (complex multi-step)", style="jarvis.dim"))
            console.print(Text(f"    Direct (1B handled): {status['direct_handle_count']}x", style="jarvis.dim"))
            console.print(Text(f"    Escalated (→3B/4B): {status['escalation_count']}x", style="jarvis.dim"))
            console.print(Text(f"    Draft-then-verify:  {status.get('draft_verify_count', 0)}x", style="jarvis.dim"))
            console.print(Text(f"    Deterministic (no LLM): {status.get('deterministic_count', 0)}x", style="jarvis.dim"))
        if status["model_usage"]:
            console.print(Text("  Usage:", style="jarvis.accent"))
            for model, count in status["model_usage"].items():
                console.print(Text(f"    {model}: {count}x", style="jarvis.dim"))
        return

    if arg == "cascade":
        result = registry.set_cascade(True)
        console.print(Text(f"  {result}", style="jarvis.accent"))
        return

    if arg == "single":
        result = registry.set_cascade(False)
        console.print(Text(f"  {result}", style="jarvis.accent"))
        return

    # Switch to a specific model or auto
    result = registry.set_model(arg)
    console.print(Text(f"  {result}", style="jarvis.accent"))
    # Also swap the router's Ollama model if we locked to a specific one
    if registry.active_model:
        loop.router.swap_ollama_model(registry.active_model)
        # Remember preference in memory
        try:
            if loop.mem is not None:
                loop.mem.store("preferred_model", registry.active_model, category="preferences")
        except Exception:
            pass
    else:
        # Auto mode — remove preference
        try:
            if loop.mem is not None:
                loop.mem.store("preferred_model", "auto", category="preferences")
        except Exception:
            pass


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
