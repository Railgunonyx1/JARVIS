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

_IMPORT_START = time.perf_counter()  # noqa: E402 — must be before heavy imports

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
# Additional silence for library progress bars and telemetry before any provider is imported.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", category=FutureWarning,
                        message=r"(?s).*google\.generativeai")

logger = logging.getLogger("jarvis.cli")

import typer  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.text import Text  # noqa: E402

from cli.theme import build_rich_theme  # noqa: E402

app = typer.Typer(add_completion=False)
console = Console(theme=build_rich_theme())

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


def _build_loop(mode: str, max_iterations: int, max_tokens: int | None,
                project_dir: str | None, confirmation_handler=None):
    from cli.startup_profile import get_profiler

    profiler = get_profiler()
    profiler.begin_trace()
    try:
        from runtime.kernel import build_kernel
        with profiler.phase("kernel.build"):
            runtime = build_kernel(
                mode=mode,
                max_iterations=max_iterations,
                max_tokens=max_tokens,
                project_dir=project_dir,
                confirmation_handler=confirmation_handler,
            )
        return runtime.agent_loop
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
    """Print result after agent finishes.

    Uses plain sys.stdout.write() to bypass ALL Rich state (Console, Live,
    Panel, etc). Rich's internal cursor tracking can swallow prints even
    after Live.stop(). Writing directly to the file descriptor is the only
    reliable way to guarantee output appears.
    """
    try:
        if result and result.success and result.response:
            text = result.response
            # Strip any ANSI codes that Rich might have injected
            import re as _re
            text = _re.sub(r'\x1b\[[0-9;]*m', '', text)
            sys.stdout.write('\n' + text + '\n\n')
            sys.stdout.flush()
        elif result and not result.success:
            err = getattr(result, 'error', 'unknown error')
            sys.stdout.write(f'\n  error: {err[:200]}\n\n')
            sys.stdout.flush()
        else:
            sys.stdout.write('\n  (no response)\n\n')
            sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(f'\n  (output error: {e})\n\n')
        sys.stdout.flush()


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
    loop._last_task_id = f"task_{int(time.time())}"
    _cancel_event = asyncio.Event()  # Set to cancel the current task gracefully
    notifications = notifications if notifications is not None else []
    renderer = getattr(bridge, "renderer", None) if bridge is not None else None
    # Live display is enabled for one-shot (--json disabled, --collapsed disabled).
    # In interactive (collapsed) mode: we skip the Live display entirely to
    # avoid duplicate output — _print_collapsed handles the final result.
    use_live = not json_output and not collapsed
    display = LiveTaskDisplay(
        console=console,
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
        # Clear previous conversation so each run starts fresh.
        # The Live display renders bridge.state.messages — accumulating
        # across runs causes the growing repetition bug.
        bridge.state.messages.clear()
        bridge.state.plan = None
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
    # Model selection is delegated to the wired ModelGateway (the single
    # model-selection authority). The registry's cascade/auto routing below is
    # kept only for deterministic-command detection and informational logging —
    # it must NOT mutate loop._preferred_model, which the loop owns.
    try:
        from core.agent.loop import AgentResult
        from providers.model_registry import ModelRegistry
        _registry = ModelRegistry.instance()
        if _registry.cascade_mode:
            _cascade = _registry.resolve_cascade(goal)
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
            logger.info("Cascade: %s (conf=%.2f) → gateway-selected model for: %s",
                        _cascade["task_type"], _cascade["confidence"], goal[:60])
        else:
            _resolved = _registry.resolve_model(goal)
            logger.info("Auto-routed to %s for: %s", _resolved, goal[:60])
    except Exception:
        pass  # Auto-routing is best-effort
    try:
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
        if use_live:
            display.stop()
            if renderer is not None:
                renderer.detach_live()
            # After Live stops: print the final result so the user sees it.
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
        # transient=False keeps the Live display. Print the final result.
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

    # Conditional startup phases based on mode to reduce first-response time
    # Plan mode: skip heavy memory loading
    # Controlled/smart mode: reduced initialization
    # Agent mode: full initialization with interrupt executor
    if mode in ("plan", "controlled"):
        # Skip interrupt executor and heavy memory features
        _interrupt_executor = None
        _interrupt_classifier = None
    elif mode == "smart":
        # Smart mode: reduced features, no interrupt executor
        _interrupt_executor = None
        _interrupt_classifier = None

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

    _BOOT_PHASES = ["config", "tools", "project", "providers", "memory", "loop"]
    _boot_phase_idx = [0]

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

    # Show startup progress while kernel boots
    bridge.renderer.state.connection = "BOOTING"
    bridge.renderer.refresh()
    boot_start = time.time()
    notifications: list = []
    _configure_noise(verbose=False)
    loop = None

    history = HistoryStore()
    reader = InputReader()
    reader.set_history(history.to_list())

    # ── Input thread + asyncio REPL (P0-1: concurrent interrupt support) ──
    # Input reading runs in a daemon thread feeding a queue.
    # The main asyncio event loop consumes commands and checks for
    # interrupts while an agent task is running concurrently.
    import queue as _queue
    input_q: _queue.Queue[str | None] = _queue.Queue()
    pending_main: _queue.Queue[str] = _queue.Queue()  # deferred main requests (separate from input)
    _stop_event = threading.Event()
    _agent_task: asyncio.Task | None = None
    _agent_event_loop: asyncio.AbstractEventLoop | None = None
    _input_ready = threading.Event()  # Set when REPL is waiting for input

    def _input_thread() -> None:
        """Read input in a background thread.

        ALWAYS reads when REPL is ready. The REPL sets _input_ready before
        blocking on input_q.get(), and clears it after consuming a line.
        This allows the input thread to read interrupts while the main
        task is running.
        """
        while not _stop_event.is_set():
            _input_ready.wait(timeout=0.5)
            if _stop_event.is_set():
                break
            if not _input_ready.is_set():
                continue
            try:
                mode_str = str(loop.mode).lower() if loop else "agent"
                prompt = f"JARVIS [{mode_str}] > "
                line = reader.read_line(prompt)
                _input_ready.clear()  # Consumed — REPL will set again
                input_q.put(line)
            except (EOFError, KeyboardInterrupt):
                input_q.put(None)
                break
            except PaletteRequest:
                try:
                    commands.dispatch("/palette")
                except SystemExit:
                    input_q.put(None)
                    break

    # ── Synchronous command dispatcher (non-agent commands) ──
    def _dispatch_sync(line: str) -> bool:
        """Dispatch non-agent commands. Returns False if agent task should run."""
        if not line:
            last = getattr(loop, "_last_result", None)
            if last is not None:
                console.print(render_expanded(last))
            return True
        if line in ("/exit", "/quit"):
            _stop_event.set()
            return True
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
        elif line == "/plugins":
            _cmd_plugins(loop)
        elif line == "/tools":
            _cmd_tools(loop)
        elif line == "/skills":
            _cmd_skills()
        elif line == "/memory prompt":
            _cmd_memory_prompt(loop)
        elif line == "/cancel":
            _cmd_cancel(loop)
        elif line == "/resume":
            goal = getattr(loop, "_last_goal", None)
            if not goal:
                console.print(Text("  no previous goal", style="jarvis.error"))
                return True
            line = goal  # Fall through to agent runner below
            return False
        elif line.startswith("/"):
            commands.dispatch(line)
        else:
            return False  # Agent command
        return True

    # ── Async agent task runner (runs on background event loop) ──
    async def _run_agent_async(goal: str) -> None:
        """Run the agent task on the background event loop.

        Registers with TaskRegistry as the authoritative task-state source.
        """
        from core.agent.lanes import ExecutionLane, TaskHandle
        _task_id = f"main_{int(time.time())}"
        _handle = TaskHandle(
            task_id=_task_id, goal=goal, lane=ExecutionLane.MAIN,
            model=loop._preferred_model or 'unknown',
        )
        # Use interrupt executor's registry if available, else local
        _registry = (
            _interrupt_executor.task_registry if _interrupt_executor
            else None
        )
        if _registry:
            _registry.register(_handle)
        try:
            await _run_once(
                goal, loop, collapsed=True,
                notifications=notifications, bridge=bridge, screen=False,
            )
        finally:
            if _registry:
                _registry.unregister(_task_id)

    # ── Async interrupt handler (runs on background event loop) ──
    async def _handle_interrupt(text: str) -> None:
        """Classify and execute an interrupt on the 1B model."""
        if _interrupt_classifier is None or _interrupt_executor is None:
            return
        classification = _interrupt_classifier.classify(
            text,
            active_task_id=getattr(loop, '_last_task_id', None),
            active_task_status="executing",
        )
        if classification.lane.value == "interrupt":
            try:
                _result = await _interrupt_executor.execute(text, classification)
                if _result["success"]:
                    console.print(Text(f"  {_result['response']}", style="cyan"))
                    console.print(Text(f"  (interrupt · {_result['latency_ms']:.0f}ms · 1B)", style="dim"))
                else:
                    err = _result.get("error", "no response")
                    console.print(Text(f"  interrupt error: {err}", style="jarvis.error"))
            except Exception as exc:
                console.print(Text(f"  interrupt error: {exc}", style="jarvis.error"))

    # ── Async REPL main loop (runs on main thread via asyncio.run) ──
    async def _repl_loop() -> None:
        nonlocal loop, _agent_task, _agent_event_loop
        _agent_event_loop = asyncio.get_running_loop()
        t = threading.Thread(target=_input_thread, daemon=True, name="jarvis-input")
        t.start()

        while not _stop_event.is_set():
            # ── Read one input line ──
            # _input_ready controls the input thread: set = thread reads from stdin,
            # clear = thread waits. We set it here, read one line, then immediately
            # clear to prevent the thread from reading ahead while we process.
            _input_ready.set()
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, input_q.get)
            except Exception:
                break
            _input_ready.clear()  # Consumed — prevent input thread from reading ahead

            # ── First iteration: boot + loop setup ──
            if loop is None:
                if line is None:
                    break
                line = line.strip()
                history.add(line)
                history.save()
                if not ready.is_set():
                    try:
                        await asyncio.get_event_loop().run_in_executor(None, ready.wait)
                    except (KeyboardInterrupt, Exception):
                        break
                loop = holder.get("loop")
                if loop is None:
                    console.print(Text(f"  startup failed: {holder.get('error', 'unknown')}", style="jarvis.error"))
                    break
                bridge.attach_loop(loop)
                bridge.pull_status()
                boot_ms = (time.time() - boot_start) * 1000
                ollama_ok = False
                try:
                    for _pname, _pinfo in loop.router.status.items():
                        if _pname == 'ollama' and _pinfo.get('available'):
                            ollama_ok = True
                            break
                except Exception:
                    pass
                if ollama_ok:
                    bridge.renderer.state.connection = "ONLINE"
                elif getattr(loop.router, '_last_provider', None) and \
                     loop.router._last_provider != 'ollama':
                    bridge.renderer.state.connection = "CLOUD"
                else:
                    bridge.renderer.state.connection = "OFFLINE"
                bridge.renderer.state.status_message = f"ready in {boot_ms/1000:.1f}s"
                bridge.renderer.refresh()
                def _forward_provider_event(name, payload):
                    if hasattr(loop.observer, 'on_event'):
                        loop.observer.on_event(name, payload)
                loop.router.on_provider_event = _forward_provider_event
                def _deferred_project_import():
                    try:
                        loop.mem.import_project_docs(
                            str(loop.project.root_path), loop.project.root_path,
                        )
                    except Exception:
                        pass
                threading.Thread(target=_deferred_project_import, daemon=True).start()
                loop.router.warm()
                global _interrupt_executor, _interrupt_classifier
                try:
                    from core.agent.lanes import InterruptExecutor, RequestClassifier
                    _interrupt_classifier = RequestClassifier()
                    _tool_svc = getattr(loop, '_tool_service', None)
                    _interrupt_executor = InterruptExecutor(
                        router=loop.router, registry=loop.registry,
                        mem=loop.mem, project=loop.project,
                        tool_service=_tool_svc,
                    )
                except Exception as exc:
                    logger.warning("InterruptExecutor init failed: %s", exc)
                    _interrupt_classifier = None
                    _interrupt_executor = None
                if profile_startup:
                    _print_startup_report()
                # Fall through to dispatch this first input
            else:
                # ── Subsequent iterations: process input ──
                if line is None:
                    _stop_event.set()
                    break
                line = line.strip()
                if not line:
                    last = getattr(loop, '_last_result', None)
                    if last is not None:
                        console.print(render_expanded(last))
                    _input_ready.set()
                    continue
                history.add(line)
                history.save()


            # ── Dispatch or queue agent command ──
            if _dispatch_sync(line):
                _input_ready.set()  # Ready for next input
                continue  # Non-agent command handled, get next input

            # Check if a main task is already running (via TaskRegistry)
            _main_active = (
                _interrupt_executor is not None
                and _interrupt_executor.task_registry.has_active_main
            )

            if _main_active:
                # Main task running — classify this input
                if _interrupt_classifier is not None:
                    classification = _interrupt_classifier.classify(
                        line,
                        active_task_id=(
                            _interrupt_executor.task_registry.main_task.task_id
                            if _interrupt_executor.task_registry.main_task
                            else None
                        ),
                        active_task_status="executing",
                    )
                    if classification.lane.value == "interrupt":
                        # Run interrupt concurrently — main task continues
                        asyncio.run_coroutine_threadsafe(
                            _handle_interrupt(line), _agent_event_loop,
                        )
                        _input_ready.set()  # Ready for next input immediately
                        continue
                # Not an interrupt — queue for after current task finishes
                console.print(Text("  (task still running — queuing...)", style="dim"))
                pending_main.put(line)
                _input_ready.set()  # Ready for next input
                await asyncio.sleep(0.1)
                continue

            # No main task running — launch one
            _agent_task = asyncio.ensure_future(_run_agent_async(line))
            # Allow input thread to read — interrupts can arrive while the
            # main task is running.  We poll the queue below.
            _input_ready.set()

            # Poll for interrupts while main task runs (non-blocking)
            import queue as _qmod
            while not _agent_task.done():
                try:
                    incoming = await asyncio.to_thread(input_q.get, timeout=0.15)
                except (_qmod.Empty, TimeoutError):
                    await asyncio.sleep(0.01)
                    continue
                if incoming is None:
                    _stop_event.set()
                    _agent_task.cancel()
                    break
                incoming = incoming.strip()
                history.add(incoming)
                # Classify as interrupt or queued main task
                if _interrupt_classifier is not None:
                    _main_id = (
                        _interrupt_executor.task_registry.main_task.task_id
                        if (
                            _interrupt_executor
                            and _interrupt_executor.task_registry.main_task
                        )
                        else None
                    )
                    cls = _interrupt_classifier.classify(
                        incoming, active_task_id=_main_id,
                        active_task_status="executing",
                    )
                    if cls.lane.value == "interrupt" and _agent_event_loop:
                        asyncio.run_coroutine_threadsafe(
                            _handle_interrupt(incoming), _agent_event_loop,
                        )
                        continue
                # Not interrupt — queue for after main task (SEPARATE queue)
                console.print(Text("  (task running — queued)", style="dim"))
                pending_main.put(incoming)

            # Main task finished — result already printed by _run_once.
            # Clear bridge state to prevent message accumulation.
            try:
                await _agent_task
            except asyncio.CancelledError:
                pass
            except Exception as _task_err:
                console.print(Text(f"  error: {str(_task_err)[:200]}", style="jarvis.error"))
            if bridge is not None:
                bridge.state.messages.clear()
                bridge.state.plan = None
            # Drain pending main requests from the separate queue
            while not pending_main.empty():
                try:
                    pending_line = pending_main.get_nowait()
                except _qmod.Empty:
                    break
                if pending_line and pending_line.strip():
                    console.print(Text(f"  (running queued: {pending_line.strip()[:50]})", style="dim"))
                    _agent_task = asyncio.ensure_future(_run_agent_async(pending_line.strip()))
                    # Do NOT set _input_ready here — let the agent finish first
                    try:
                        await _agent_task
                    except Exception as _q_err:
                        console.print(Text(f"  error: {str(_q_err)[:200]}", style="jarvis.error"))
            await asyncio.sleep(0.1)
            _input_ready.set()
            continue

    # Run the async REPL
    try:
        asyncio.run(_repl_loop())
    except KeyboardInterrupt:
        pass

    _stop_event.set()
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
        console.print(Text(f"  {loop.mem.remember(key.strip() or 'note', value.strip(), category='notes')}", style="dim"))  # noqa: E501
    else:
        console.print(Text("  usage: /memory [search <q> | add <k>=<v>]", style="jarvis.error"))


def _cmd_audit(line: str, limit_default: int = 12) -> None:
    from security.audit import get_audit_log
    parts = line.split(maxsplit=1)
    args = parts[1].strip() if len(parts) == 2 else ""
    log = get_audit_log()
    stats = log.get_stats()
    console.print(Text(f"  {stats['total_actions']} actions | {stats['denied']} denied | {stats['failed']} failed", style="dim"))  # noqa: E501
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
            console.print(Text(f"  {ts} {e['tool'] or e['action']:<28} {ok}{flag} {e['duration_ms']:.0f}ms", style="dim"))  # noqa: E501
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


def _cmd_skills() -> None:
    """Show all available skills and their tool coverage."""
    from rich.table import Table

    from skills import build_default_skill_registry
    from tools import build_default_registry

    skill_reg = build_default_skill_registry()
    tool_reg = build_default_registry()
    tool_names = {t.name for t in tool_reg.list()}

    table = Table(title="JARVIS Skills")
    table.add_column("Skill", style="bold")
    table.add_column("Tools", justify="right")
    table.add_column("Risk")
    table.add_column("Description", max_width=50)

    for s in sorted(skill_reg.values(), key=lambda x: x.name):
        tags_str = ", ".join(s.tags[:3]) if s.tags else ""
        risk_raw = getattr(s, 'risk', '') or ''
        risk_str = (
            "high" if "high" in str(risk_raw)
            else "medium" if "medium" in str(risk_raw)
            else "low"
        )
        table.add_row(
            s.name,
            tags_str,
            risk_str,
            s.description[:50],
        )
    console.print(table)
    console.print(
        Text(f"  {len(skill_reg)} skills, {len(tool_names)} tools",
             style="dim")
    )



def _cmd_plugins(loop) -> None:
    """Show all discovered plugins."""
    from core.plugin_loader import PluginLoader, list_plugins

    pl = PluginLoader()
    loaded = pl.discover_and_load()

    from rich.table import Table
    table = Table(title="JARVIS Plugins")
    table.add_column("Plugin", style="bold")
    table.add_column("Description")

    for name, reg in sorted(list_plugins().items()):
        table.add_row(name, reg.description or "")

    console.print(table)
    console.print(Text(f"  {len(loaded)} plugins loaded", style="dim"))


def _cmd_tools(loop) -> None:
    """Show all registered tools from the default registry."""
    from rich.table import Table

    from tools import build_default_registry

    tool_reg = build_default_registry()

    table = Table(title="JARVIS Tools")
    table.add_column("Tool", style="bold")
    table.add_column("Category")
    table.add_column("Permission")

    for tool in tool_reg.list():
        table.add_row(
            tool.name,
            tool.category if tool.category else "",
            tool.permission if tool.permission else "",
        )

    console.print(table)
    console.print(
        Text(f"  {len(tool_reg)} tools registered", style="dim"))



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
            console.print(Text(f"    Router: {status['cascade_router']} (ultra-fast, simple tasks)", style="jarvis.dim"))  # noqa: E501
            console.print(Text(f"    Worker: {status['cascade_worker']} (coding, tools, reasoning)", style="jarvis.dim"))  # noqa: E501
            console.print(Text(f"    Heavy:  {status['cascade_heavy']} (complex multi-step)", style="jarvis.dim"))
            console.print(Text(f"    Direct (1B handled): {status['direct_handle_count']}x", style="jarvis.dim"))
            console.print(Text(f"    Escalated (→3B/4B): {status['escalation_count']}x", style="jarvis.dim"))
            console.print(Text(f"    Draft-then-verify:  {status.get('draft_verify_count', 0)}x", style="jarvis.dim"))
            console.print(Text(f"    Deterministic (no LLM): {status.get('deterministic_count', 0)}x", style="jarvis.dim"))  # noqa: E501
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
    # Store preference in memory (request-scoped, NOT global mutation)
    # Model selection is resolved per-request via ModelRegistry.resolve_model()
    # and passed as preferred_model to ProviderRouter.complete(), so we do NOT
    # call swap_ollama_model() which mutates shared state unsafely.
    try:
        if loop.mem is not None:
            model_val = registry.active_model or "auto"
            loop.mem.store("preferred_model", model_val, category="preferences")
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
