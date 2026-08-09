"""Persistent JARVIS daemon kernel.

Binds a long-lived kernel (config + tools + project + router + memory) to a
localhost TCP loopback socket. The terminal client connects, authenticates
with the registry token, and drives the kernel over a persistent connection
with envelope-framed requests. ``run`` requests stream TaskObserver events
back to the client in real time, then a terminal ``stream.result`` frame.

The daemon is one-per-project: memory, tools, and the workspace context are
project-specific, so the registry key is a project fingerprint.

Run (as the detached daemon process)::

    python -m daemon.server start --project-dir C:/path/to/project
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from daemon.project import project_id
from daemon.state import (
    DAEMONS_DIR,
    LOG_PATH,
    PROTOCOL_VERSION,
    STATE_DIR,
    acquire_instance_lock,
    generate_token,
    load_entry,
    pick_port,
    release_instance_lock,
    remove_entry,
    save_entry,
)
from runtime.transport.protocol import (
    MSG_AUTH,
    MSG_ERROR,
    MSG_EVENT,
    MSG_HISTORY,
    MSG_MEMORY_ADD,
    MSG_MEMORY_SEARCH,
    MSG_MODELS,
    MSG_OK,
    MSG_PING,
    MSG_PONG,
    MSG_RESULT,
    MSG_RUN,
    MSG_RUN_RESULT,
    MSG_SET_MODE,
    MSG_SHUTDOWN,
    MSG_STATUS,
)
from runtime.transport.tcp import start_server

logger = logging.getLogger("jarvis.daemon")

_MODES = ("plan", "controlled", "smart", "agent")
KernelFactory = Callable[[str | None], Any]


class DaemonAlreadyRunning(RuntimeError):
    """A healthy daemon already owns this project; refusing to start a second."""


def _env(type_: str, payload: dict[str, Any] | None = None,
         id_: str = "") -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "id": id_,
        "type": type_,
        "timestamp": time.time(),
        "payload": payload or {},
    }


async def _send(transport, type_: str, payload: dict[str, Any] | None,
                id_: str) -> None:
    await transport.send(_env(type_, payload, id_))


async def _safe_send(transport, type_: str, payload: dict[str, Any] | None,
                     id_: str) -> None:
    """Send a frame; a dead client must never take the daemon down."""
    try:
        await transport.send(_env(type_, payload, id_))
    except (OSError, ConnectionError, RuntimeError):
        pass


def _mode_value(permissions) -> str:
    mode = getattr(permissions, "mode", "")
    return getattr(mode, "value", str(mode))


class DaemonServer:
    """Hosts one project kernel behind an authenticated TCP loopback server."""

    def __init__(
        self,
        kernel_factory: KernelFactory | None = None,
        project_dir: str | None = None,
        port: int | None = None,
        host: str = "127.0.0.1",
        token: str | None = None,
        registry_dir: Path | None = None,
        state_dir: Path | None = None,
    ) -> None:
        self.kernel_factory = kernel_factory
        self.project_dir = str(Path(project_dir).resolve()) if project_dir else str(Path.cwd().resolve())
        self.project_id = project_id(Path(self.project_dir))
        self.host = host
        self.port = port or pick_port()
        self.token = token or generate_token()
        self.registry_dir = Path(registry_dir) if registry_dir else DAEMONS_DIR
        self.state_dir = Path(state_dir) if state_dir else STATE_DIR

        self.kernel: Any = None
        self._server = None
        self._pipe_server = None
        self._connections = set()
        self._tasks: dict[int, set] = {}
        self._run_lock = asyncio.Lock()
        self._shutdown = asyncio.Event()
        self.started_at = time.time()
        self._last_state = None
        self._closing = False
        self._active_runs: set = set()
        self._detached_runs: set = set()
        self._senders: set = set()

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        lock = acquire_instance_lock(self.project_id, self.registry_dir)
        try:
            self._ensure_single_instance()
            factory = self.kernel_factory or self._default_kernel_factory()
            self.kernel = factory(project_dir=self.project_dir)

            thread = threading.Thread(target=self._safe_warm, daemon=True,
                                      name="daemon-router-warm")
            thread.start()

            for attempt in range(3):
                try:
                    self._server = await start_server(self._on_client, self.host, self.port)
                    break
                except OSError:
                    if attempt == 2:
                        raise
                    self.port = pick_port()
            bound = self._server.sockets[0].getsockname()
            self.port = bound[1]

            try:
                from runtime.transport.pipe import start_pipe_server
                pipe_name = rf"\\.\pipe\jarvis-{self.project_id}"
                self._pipe_server = await start_pipe_server(self._on_client, pipe_name)
                logger.info("daemon %s listening on pipe %s", self.project_id, pipe_name)
            except Exception as e:
                logger.warning("Failed to start named pipe server: %s", e)

            save_entry({
                "project_id": self.project_id,
                "project": self.project_dir,
                "port": self.port,
                "pid": os.getpid(),
                "token": self.token,
                "version": PROTOCOL_VERSION,
                "started_at": self.started_at,
                "last_active": time.time(),
                "mode": self._mode(),
            }, base_dir=self.registry_dir)
            self._write_snapshot()
            logger.info("daemon %s listening on %s:%s", self.project_id,
                        self.host, self.port)
        finally:
            release_instance_lock(lock)

    def _ensure_single_instance(self) -> None:
        """Refuse to start a second daemon while a healthy one owns this project.

        The CLI checks the registry before spawning; this second line closes
        the window where two ``start`` processes pass that check before either
        writes its entry (the instance lock serializes that window), and also
        covers direct ``DaemonServer`` construction. Without it the duplicate
        would quietly bind a fresh TCP port and fail its named-pipe bind —
        two daemons for one project.
        """
        from daemon.lifecycle import entry_healthy

        existing = load_entry(self.project_id, base_dir=self.registry_dir)
        if existing is not None and entry_healthy(existing):
            raise DaemonAlreadyRunning(
                f"a healthy daemon already runs for project {self.project_id} "
                f"(pid={existing['pid']}, port={existing['port']})"
            )

    def _default_kernel_factory(self) -> KernelFactory:
        from runtime.kernel import build_kernel

        return build_kernel

    def _safe_warm(self) -> None:
        """Warm provider SDKs in the background, retrying until it succeeds."""
        delay = 1.0
        for _ in range(5):
            try:
                self.kernel.router.warm()
                return
            except Exception as exc:  # pragma: no cover - provider edge cases
                logger.warning("router warm failed (%s); retrying in %.1fs", exc, delay)
                time.sleep(delay)
                delay = min(delay * 2, 30.0)

    def _mode(self) -> str:
        if self.kernel is None:
            return "agent"
        return _mode_value(self.kernel.permissions)

    async def serve(self) -> None:
        await self._shutdown.wait()

    async def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._shutdown.set()
        logger.info("daemon %s shutting down", self.project_id)
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self._pipe_server is not None:
            self._pipe_server.close()
            await self._pipe_server.wait_closed()
        for sender in list(self._senders):
            sender.cancel()
        for run in list(self._detached_runs):
            run.cancel()
        for task in self._all_tasks():
            task.cancel()
        await asyncio.gather(*list(self._senders), return_exceptions=True)
        for transport in list(self._connections):
            await transport.close()
        self._write_snapshot()
        try:
            from runtime.kernel import close_kernel

            close_kernel(self.kernel)
        except Exception:
            pass
        remove_entry(self.project_id, base_dir=self.registry_dir)
        try:
            from runtime.observability.exporters import disable_perf

            disable_perf()
        except Exception:
            pass

    def _all_tasks(self):
        for group in self._tasks.values():
            yield from group

    # ── connection handling ────────────────────────────────────────────────

    async def _on_client(self, transport) -> None:
        self._connections.add(transport)
        self._tasks[id(transport)] = set()
        try:
            first = await transport.receive()
            if first is None:
                return
            if (first.get("type") != MSG_AUTH
                    or first.get("payload", {}).get("token") != self.token):
                await _safe_send(transport, MSG_ERROR,
                                 {"message": "unauthorized"}, first.get("id", ""))
                return
            await _safe_send(transport, MSG_OK, {}, first.get("id", ""))
            while not self._shutdown.is_set():
                message = await transport.receive()
                if message is None:
                    return
                task = asyncio.create_task(self._dispatch(message, transport))
                self._tasks[id(transport)].add(task)
                task.add_done_callback(self._tasks[id(transport)].discard)
        except asyncio.CancelledError:
            raise
        except BaseException:
            # A single hostile/broken client must not kill the daemon.
            logger.exception("client connection failed")
        finally:
            self._connections.discard(transport)
            pending = self._tasks.pop(id(transport), set())
            for task in pending:
                if task in self._active_runs:
                    # A run may be inside an LLM call: cancel it and the kernel
                    # work dies mid-flight. Leave the run to finish in the
                    # background (shielding keeps the call alive); the client
                    # is gone so its frames just go nowhere.
                    continue
                task.cancel()
            await transport.close()

    # ── request dispatch ───────────────────────────────────────────────────

    async def _dispatch(self, message: dict[str, Any], transport) -> None:
        type_ = message.get("type", "")
        rid = message.get("id", "")
        payload = message.get("payload", {}) or {}
        handler = {
            MSG_PING: self._handle_ping,
            MSG_STATUS: self._handle_status,
            MSG_MODELS: self._handle_models,
            MSG_SET_MODE: self._handle_set_mode,
            MSG_MEMORY_SEARCH: self._handle_memory_search,
            MSG_MEMORY_ADD: self._handle_memory_add,
            MSG_HISTORY: self._handle_history,
            MSG_RUN: self._handle_run,
            MSG_SHUTDOWN: self._handle_shutdown,
        }.get(type_)
        if handler is None:
            await _send(transport, MSG_ERROR,
                        {"message": f"unknown message type '{type_}'"}, rid)
            return
        from runtime.observability.tracer import get_tracer

        tracer = get_tracer()
        try:
            with tracer.span(f"ipc.{type_}", {"id": rid}):
                await handler(payload, rid, transport)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            try:
                await _safe_send(transport, MSG_ERROR,
                                 {"message": str(exc)[:500]}, rid)
            except Exception:
                pass

    async def _handle_ping(self, payload, rid, transport) -> None:
        await _send(transport, MSG_PONG, {
            "pid": os.getpid(),
            "project": self.project_dir,
            "project_id": self.project_id,
            "mode": self._mode(),
            "started_at": self.started_at,
            "uptime": time.time() - self.started_at,
        }, rid)

    async def _handle_status(self, payload, rid, transport) -> None:
        await _send(transport, MSG_RESULT, {
            "pid": os.getpid(),
            "project": self.project_dir,
            "project_id": self.project_id,
            "started_at": self.started_at,
            "uptime": time.time() - self.started_at,
            "mode": self._mode(),
            "provider": getattr(self.kernel.router, "_last_provider", None),
            "model": getattr(self.kernel.router, "_last_model", None),
            "tools": len(self.kernel.registry.list()),
            "mem_stats": self.kernel.mem.get_stats()
                if getattr(self.kernel, "mem", None) else {},
            "last_goal": getattr(self.kernel, "_last_goal", ""),
            "busy": self._run_lock.locked(),
        }, rid)

    async def _handle_models(self, payload, rid, transport) -> None:
        await _send(transport, MSG_RESULT,
                    {"data": dict(getattr(self.kernel.router, "status", {}))}, rid)

    async def _handle_set_mode(self, payload, rid, transport) -> None:
        mode = str(payload.get("mode", "")).strip()
        if mode not in _MODES:
            await _send(transport, MSG_ERROR,
                        {"message": f"unknown mode '{mode}'"}, rid)
            return
        self.kernel.permissions.set_mode(mode)
        await _send(transport, MSG_OK, {"mode": mode}, rid)

    async def _handle_memory_search(self, payload, rid, transport) -> None:
        mem = getattr(self.kernel, "mem", None)
        if mem is None:
            await _send(transport, MSG_ERROR, {"message": "memory disabled"}, rid)
            return
        query = str(payload.get("query", "")).strip()
        if not query:
            await _send(transport, MSG_ERROR, {"message": "empty query"}, rid)
            return
        project = payload.get("project") or self.project_dir
        top_k = int(payload.get("top_k", 5))
        hits = mem.retrieve(query, project=project, top_k=top_k)
        await _send(transport, MSG_RESULT, {"hits": hits}, rid)

    async def _handle_memory_add(self, payload, rid, transport) -> None:
        mem = getattr(self.kernel, "mem", None)
        if mem is None:
            await _send(transport, MSG_ERROR, {"message": "memory disabled"}, rid)
            return
        key = str(payload.get("key", "")).strip() or "note"
        value = str(payload.get("value", "")).strip()
        if not value:
            await _send(transport, MSG_ERROR, {"message": "empty value"}, rid)
            return
        message = mem.remember(key, value, category=str(payload.get("category", "notes")))
        await _send(transport, MSG_OK, {"message": message}, rid)

    async def _handle_history(self, payload, rid, transport) -> None:
        from core.event_store import get_event_store

        store = get_event_store()
        task_id = str(payload.get("task_id", "")).strip()
        if task_id:
            events = store.query(trace_id=task_id, limit=200)
            await _send(transport, MSG_RESULT, {"events": [
                {
                    "timestamp": e.timestamp,
                    "name": e.name,
                    "data": e.data,
                    "source": e.source,
                    "trace_id": e.trace_id,
                }
                for e in events
            ]}, rid)
        else:
            traces = store.recent_traces(limit=int(payload.get("limit", 10)))
            await _send(transport, MSG_RESULT, {"traces": traces}, rid)

    async def _handle_run(self, payload, rid, transport) -> None:
        goal = str(payload.get("goal", "")).strip()
        if not goal:
            await _safe_send(transport, MSG_ERROR, {"message": "empty goal"}, rid)
            return
        mode = payload.get("mode")
        if mode and mode in _MODES:
            self.kernel.permissions.set_mode(mode)

        current = asyncio.current_task()
        if current is not None:
            self._active_runs.add(current)

        stream: asyncio.Queue = asyncio.Queue()
        sender = asyncio.create_task(self._drain_events(stream, transport, rid))
        self._senders.add(sender)
        sender.add_done_callback(self._senders.discard)

        def _forward(name: str, data: dict[str, Any]) -> None:
            stream.put_nowait({"name": name, "payload": data})

        previous = getattr(self.kernel.observer, "on_event", None)
        self.kernel.observer.on_event = _forward
        result = None
        try:
            result = await self._shielded_kernel_run(goal)
        finally:
            if current is not None:
                self._active_runs.discard(current)
            self.kernel.observer.on_event = previous
            stream.put_nowait(None)
            try:
                await asyncio.wait_for(asyncio.shield(sender), timeout=2.0)
            except (Exception, asyncio.CancelledError):
                pass

        self.kernel._last_goal = goal
        self.kernel._last_result = result
        self._touch()
        self._write_snapshot(result)
        await _safe_send(transport, MSG_RUN_RESULT,
                         {"result": result.to_dict()}, rid)

    async def _shielded_kernel_run(self, goal: str):
        """Run the kernel detached so cancellation cannot kill the work.

        If the dispatch task is cancelled (client disconnect mid-run), the
        kernel run keeps going in the background holding the run lock; a fresh
        client simply waits for it instead of corrupting a half-finished LLM
        call. The daemon never dies because a client vanished.
        """
        task = asyncio.ensure_future(self._run_locked(goal))
        self._detached_runs.add(task)
        task.add_done_callback(self._on_run_done)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            raise

    async def _run_locked(self, goal: str):
        async with self._run_lock:
            return await self.kernel.run(goal)

    def _on_run_done(self, task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("background kernel run failed")
        finally:
            self._detached_runs.discard(task)

    async def _drain_events(self, stream, transport, rid) -> None:
        while True:
            item = await stream.get()
            if item is None:
                return
            await _safe_send(transport, MSG_EVENT, item, rid)

    async def _handle_shutdown(self, payload, rid, transport) -> None:
        await _send(transport, MSG_OK, {"message": "shutting down"}, rid)
        asyncio.create_task(self.shutdown())

    # ── state snapshot ─────────────────────────────────────────────────────

    def _write_snapshot(self, result=None) -> None:
        try:
            from runtime.state import RuntimeState, save_snapshot

            state = RuntimeState(
                project_id=self.project_id,
                project=self.project_dir,
                mode=self._mode(),
                provider=getattr(self.kernel.router, "_last_provider", ""),
                model=getattr(self.kernel.router, "_last_model", ""),
                tools=len(self.kernel.registry.list()),
                mem_stats=self.kernel.mem.get_stats()
                    if getattr(self.kernel, "mem", None) else {},
                last_goal=getattr(self.kernel, "_last_goal", ""),
                last_result="completed" if (result and result.success)
                    else ("failed" if result is not None
                           else getattr(self._last_state, "last_result", None)),
                last_trace_id=getattr(result, "trace_id", ""),
                started_at=self.started_at,
                pid=os.getpid(),
            )
            save_snapshot(state, self.state_dir / f"{self.project_id}.json")
            self._last_state = state
        except Exception:
            pass

    def _touch(self) -> None:
        try:
            from daemon.state import touch_entry

            touch_entry(self.project_id, base_dir=self.registry_dir)
        except Exception:
            pass


def _install_exception_logging() -> None:
    """Log every asyncio task error to daemon.log instead of dropping it."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    def _on_loop_error(loop, context) -> None:
        message = context.get("message", "asyncio error")
        exc = context.get("exception")
        if exc is not None:
            logger.error("asyncio: %s", message, exc_info=exc)
        else:
            logger.error("asyncio: %s", message)

    loop.set_exception_handler(_on_loop_error)


def _start_daemon(args) -> None:
    project_dir = args.project_dir or str(Path.cwd().resolve())
    existing = load_entry(project_id(Path(project_dir)))
    if existing:
        from daemon.lifecycle import entry_healthy

        if entry_healthy(existing):
            print(f"daemon already running: pid={existing['pid']} "
                  f"port={existing['port']} project={existing['project']}")
            return

    logging.basicConfig(
        filename=args.log or str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        from runtime.observability.exporters import enable_perf

        enable_perf()
    except Exception:
        pass
    server = DaemonServer(project_dir=project_dir, port=args.port,
                          registry_dir=args.registry_dir,
                          state_dir=args.state_dir)

    async def _run() -> None:
        _install_exception_logging()
        try:
            await server.start()
        except DaemonAlreadyRunning as exc:
            # A concurrent start won the race — this is not an error, the
            # healthy daemon stays. Exit cleanly so callers see a success.
            print(str(exc))
            return
        except Exception as exc:
            print(f"daemon failed to start: {exc}")
            raise
        try:
            await server.serve()
        except BaseException:
            # Never exit silently: a full traceback must reach daemon.log so a
            # "died for no reason" daemon can actually be diagnosed.
            logger.exception("daemon service crashed")
            raise

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        asyncio.run(server.shutdown())
    except BaseException:
        logger.exception("daemon process crashed")
        raise


def _stop_daemon(args) -> None:
    from daemon.lifecycle import stop_daemon

    project_dir = args.project_dir or str(Path.cwd().resolve())
    ok = stop_daemon(project_dir)
    print("daemon stopped" if ok else "no daemon running / stop failed")
    sys.exit(0 if ok else 1)


def _status_daemon(args) -> None:
    from daemon.lifecycle import daemon_status

    project_dir = args.project_dir or str(Path.cwd().resolve())
    info = daemon_status(project_dir)
    if info is None:
        print("no daemon running for this project")
        sys.exit(1)
    for key, value in info.items():
        print(f"{key}: {value}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="daemon", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="start (and serve) the daemon")
    start.add_argument("--project-dir", default=None)
    start.add_argument("--port", type=int, default=None)
    start.add_argument("--log", default=None)
    start.add_argument("--registry-dir", default=None)
    start.add_argument("--state-dir", default=None)
    stop = sub.add_parser("stop", help="stop the daemon for this project")
    stop.add_argument("--project-dir", default=None)
    status = sub.add_parser("status", help="show daemon status for this project")
    status.add_argument("--project-dir", default=None)

    args = parser.parse_args(argv)
    if args.command == "start":
        _start_daemon(args)
    elif args.command == "stop":
        _stop_daemon(args)
    elif args.command == "status":
        _status_daemon(args)


if __name__ == "__main__":
    main()
