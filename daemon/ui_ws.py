"""WebSocket bridge for the JARVIS command-center UI.

Serves the UI's ``ServerEvent``/``ClientCommand`` wire protocol (the mirror of
``web/src/lib/ipc/protocol.ts``) on ``ws://127.0.0.1:8787/ws``. It translates
real kernel activity — agent runs, tool calls, permissions, memory — into the
same envelopes the in-browser simulator emits, so the console cannot tell the
live daemon and the simulator apart; the only signal is the UI's connection
state flipping to ``online`` instead of ``sim``.

This bridge is deliberately separate from the envelope IPC server
(``daemon.server``): that endpoint speaks ``runtime.transport.protocol`` with
a token handshake for the terminal clients, while this one speaks the browser
protocol with no auth (localhost-only).

Run::

    python -m daemon.server start --project-dir C:/path/to/project --ui-port 8787
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from runtime.transport.protocol import MAX_FRAME_SIZE

try:  # pragma: no cover - guarded import
    import psutil

    _HAS_PSUTIL = True
except Exception:  # pragma: no cover - psutil missing
    _HAS_PSUTIL = False

logger = logging.getLogger("jarvis.daemon.ui_ws")

DEFAULT_UI_PORT = 8787
UI_PROTOCOL_VERSION = 1
_MODES = ("plan", "controlled", "smart", "agent")

_CAPABILITIES = ["chat", "agent", "tools", "memory", "tasks", "telemetry", "fs"]
_DAEMON_NAME = "jarvisd"
_DAEMON_VERSION = "2.4.1"

_TASK_STATUS_MAP = {
    "running": "running",
    "completed": "done",
    "failed": "failed",
    "cancelled": "failed",
}


def _now() -> int:
    return int(time.time() * 1000)


class UiBridge:
    """One WebSocket server translating kernel activity into UI frames."""

    def __init__(
        self,
        kernel: Any,
        project_dir: str | None = None,
        host: str = "127.0.0.1",
        port: int = DEFAULT_UI_PORT,
    ) -> None:
        self.kernel = kernel
        self.host = host
        self.port = port
        self.project_dir = str(Path(project_dir).resolve()) if project_dir else str(Path.cwd().resolve())

        self._server = None
        self._clients: set = set()
        self._seq = 0
        self._telemetry_task: asyncio.Task | None = None
        self._run_lock = asyncio.Lock()

        # Per-run bookkeeping (runs are serialized through _run_lock).
        self._current: dict[str, Any] = {}
        self._previous_on_event: Any = None
        self._call_ids: dict[int, str] = {}

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def start(self):
        """Bind the WebSocket server. Returns the websockets Server object."""
        from websockets.asyncio.server import serve

        self._server = await serve(
            self._on_connection,
            self.host,
            self.port,
            max_size=MAX_FRAME_SIZE,
            ping_interval=20.0,
            ping_timeout=20.0,
        )
        bound = self._server.sockets[0].getsockname()
        self.port = bound[1]
        self._telemetry_task = asyncio.create_task(self._telemetry_loop())
        logger.info("ui bridge listening on ws://%s:%s/ws", self.host, self.port)
        return self._server

    async def close(self) -> None:
        if self._telemetry_task is not None:
            self._telemetry_task.cancel()
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    # ── connection handling ────────────────────────────────────────────────

    async def _on_connection(self, ws) -> None:
        try:
            request = getattr(ws, "request", None)
            path = getattr(ws, "path", "") or getattr(request, "path", "")
            if path != "/ws":
                await ws.close(code=1008, reason="expected /ws")
                return
            self._clients.add(ws)
            await self._safe_send(ws, self._frame("hello", self._hello_payload()))
            await self._safe_send(ws, self._frame("provider.status", {"providers": self._providers()}))
            tree = self._build_tree({"path": "."})
            if tree is not None:
                await self._safe_send(ws, self._frame("fs.tree", {"root": tree}))
            while True:
                raw = await ws.recv()
                if raw is None:
                    return
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode("utf-8")
                try:
                    cmd = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(cmd, dict):
                    continue
                await self._dispatch(cmd, ws)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("ui connection dropped: %r", exc)
        finally:
            self._clients.discard(ws)

    async def _dispatch(self, cmd: dict[str, Any], ws) -> None:
        type_ = cmd.get("type", "")
        payload = cmd.get("payload", {}) or {}
        try:
            if type_ == "ping":
                await self._safe_send(ws, self._frame("pong", {"t": payload.get("t")}))
            elif type_ == "hello":
                await self._safe_send(ws, self._frame("hello", self._hello_payload()))
            elif type_ == "chat.send":
                await self._run_agent(str(payload.get("sessionId", "")), str(payload.get("text", "")), ws)
            elif type_ == "task.create":
                title = str(payload.get("title", "")).strip()
                if title:
                    await self._run_agent("", title, ws)
            elif type_ in ("chat.cancel", "task.cancel"):
                await self._cancel_run()
            elif type_ == "provider.select":
                await self._select_provider(ws, payload)
            elif type_ == "mode.set":
                await self._set_mode(ws, payload)
            elif type_ == "fs.read":
                tree = self._build_tree(payload)
                if tree is not None:
                    await self._broadcast(self._frame("fs.tree", {"root": tree}))
            elif type_ == "subscribe":
                pass
            else:
                logger.debug("ui bridge: unknown command '%s'", type_)
        except Exception as exc:
            logger.warning("ui command %s failed: %s", type_, exc)
            await self._safe_send(ws, self._frame("error", {"code": "handler_error", "message": str(exc)[:500]}))

    # ── chat / agent runs ──────────────────────────────────────────────────

    async def _run_agent(self, session_id: str, goal: str, ws) -> None:
        goal = goal.strip()
        if not goal:
            return
        async with self._run_lock:
            await self._run_agent_locked(session_id, goal)

    async def _run_agent_locked(self, session_id: str, goal: str) -> None:
        run_id = uuid.uuid4().hex[:8]
        message_id = uuid.uuid4().hex[:10]
        task_id = uuid.uuid4().hex[:8]
        self._current = {
            "run_id": run_id,
            "message_id": message_id,
            "task_id": task_id,
            "session_id": session_id,
            "goal": goal,
        }
        self._call_ids = {}
        task = self._mk_task(task_id, goal, "running", 0.0, run_id)
        await self._broadcast(self._frame("task.update", {"task": task}))
        await self._agent(run_id, "start", "run started", f"session {session_id[:6] or '—'}")
        await self._log("info", "agent", f"run {run_id} started: {goal[:80]}")

        kernel = self.kernel
        observer = getattr(kernel, "observer", None)
        self._previous_on_event = getattr(observer, "on_event", None) if observer is not None else None
        if observer is not None:
            observer.on_event = self._forward

        # The run lives in its own task so cancelling it (chat.cancel /
        # task.cancel) never kills the connection handler that awaits it.
        async def _on_chunk(delta: str) -> None:
            try:
                await self._broadcast(self._frame("chat.delta", {
                    "messageId": message_id,
                    "sessionId": session_id,
                    "delta": delta,
                }))
            except Exception:
                pass

        run_task = asyncio.create_task(kernel.run(goal, session_id, on_chunk=_on_chunk))
        self._current["task"] = run_task
        try:
            result = await asyncio.shield(run_task)
        except asyncio.CancelledError:
            if not run_task.done():
                run_task.cancel()
            self._restore_observer(observer)
            await self._agent(run_id, "error", "run cancelled by operator")
            cancelled = self._mk_task(task_id, goal, "failed", 1.0, run_id, detail="cancelled by user")
            await self._broadcast(self._frame("task.update", {"task": cancelled}))
            self._current = {}
            return
        except Exception as exc:
            self._restore_observer(observer)
            await self._agent(run_id, "error", "run failed", str(exc)[:200])
            await self._log("error", "agent", f"run {run_id} failed: {exc}")
            await self._broadcast(self._frame("error", {"code": "run_failed", "message": str(exc)[:500]}))
            failed = self._mk_task(task_id, goal, "failed", 1.0, run_id, detail=str(exc)[:200])
            await self._broadcast(self._frame("task.update", {"task": failed}))
            self._current = {}
            return

        self._restore_observer(observer)

        success = bool(getattr(result, "success", False))
        response = str(getattr(result, "response", "") or "")
        state = getattr(result, "state", None)
        model = getattr(state, "model", "") if state is not None else ""
        provider = getattr(state, "provider", "") if state is not None else ""
        usage = {
            "input": getattr(state, "tokens_prompt", 0) if state is not None else 0,
            "output": getattr(state, "tokens_completion", 0) if state is not None else 0,
        }

        if success and response:
            await self._broadcast(self._frame("chat.message", {
                "message": {
                    "id": message_id,
                    "sessionId": session_id,
                    "role": "assistant",
                    "content": response,
                    "ts": _now(),
                    "model": model or None,
                    "streaming": False,
                    "runId": run_id,
                    "usage": usage,
                },
            }))
            await self._broadcast(self._frame("chat.done", {"messageId": message_id, "usage": usage}))
            await self._agent(run_id, "done", "run complete", provider or model or None)
            done = self._mk_task(task_id, goal, "done", 1.0, run_id, detail=f"{provider} · {model}" if provider else None)
            await self._broadcast(self._frame("task.update", {"task": done}))
            await self._log("info", "agent", f"run {run_id} complete ({provider or '?'} · {model or '?'})")
        else:
            error = str(getattr(result, "error", "") or "no response")[:500]
            await self._agent(run_id, "error", "run failed", error)
            await self._broadcast(self._frame("error", {"code": "run_failed", "message": error}))
            failed = self._mk_task(task_id, goal, "failed", 1.0, run_id, detail=error[:200])
            await self._broadcast(self._frame("task.update", {"task": failed}))
            await self._log("error", "agent", f"run {run_id} failed: {error}")

        self._current = {}

    def _restore_observer(self, observer) -> None:
        if observer is not None:
            observer.on_event = self._previous_on_event
            self._previous_on_event = None

    def _forward(self, name: str, data: dict[str, Any]) -> None:
        """Adapter for ``TaskObserver.on_event`` (sync) -> async broadcasts."""
        try:
            run_id = self._current.get("run_id", "")
            task_id = self._current.get("task_id", "")
            if name == "task.started":
                self._spawn(self._agent(run_id, "start", "task started", str(data.get("goal", ""))[:80]))
            elif name == "step.started":
                index = int(data.get("step", 0))
                tool = str(data.get("tool", ""))
                call_id = f"{run_id}:{index}"
                self._call_ids[index] = call_id
                self._spawn(self._broadcast(self._frame("tool.call", {
                    "id": call_id,
                    "runId": run_id,
                    "tool": tool,
                    "status": "running",
                    "ts": _now(),
                })))
                self._spawn(self._agent(run_id, "act", f"calling {tool}", f"step {index + 1}"))
            elif name == "step.completed":
                index = int(data.get("step", 0))
                tool = str(data.get("tool", ""))
                status = str(data.get("status", "ok"))
                error = str(data.get("error", "") or "")
                call_id = self._call_ids.get(index, f"{run_id}:{index}")
                self._spawn(self._broadcast(self._frame("tool.result", {
                    "id": call_id,
                    "runId": run_id,
                    "tool": tool,
                    "status": "ok" if status == "ok" else "error",
                    "error": error or None,
                    "durationMs": float(data.get("duration_ms", 0.0) or 0.0),
                    "ts": _now(),
                })))
                if status == "ok":
                    self._spawn(self._agent(run_id, "observe", f"{tool} ok"))
                else:
                    self._spawn(self._agent(run_id, "observe", f"{tool} → {error}", error))
            elif name == "permission.observed":
                allowed = bool(data.get("allowed"))
                reason = str(data.get("reason", "") or "")
                tool = str(data.get("tool", ""))
                level = "debug" if allowed else "warn"
                self._spawn(self._log(level, "security",
                                      f"{tool} allowed" if allowed else f"{tool} denied: {reason}"))
            elif name == "task.cancelled":
                self._spawn(self._broadcast(self._frame("task.update", {
                    "task": self._mk_task(task_id, self._current.get("goal", ""),
                                          "failed", 1.0, run_id, detail="cancelled"),
                })))
        except Exception:
            pass

    def _spawn(self, coro) -> None:
        try:
            asyncio.get_running_loop().create_task(coro)
        except Exception:
            pass

    async def _cancel_run(self) -> None:
        run_id = self._current.get("run_id")
        task = self._current.get("task")
        if run_id is None or task is None:
            await self._log("warn", "agent", "no running task to cancel")
            return
        await self._log("warn", "agent", f"cancelling run {run_id} (operator)")
        task.cancel()

    # ── provider / mode / fs ───────────────────────────────────────────────

    async def _select_provider(self, ws, payload: dict[str, Any]) -> None:
        provider = str(payload.get("provider", "") or "")
        model = str(payload.get("model", "") or "")
        router = getattr(self.kernel, "router", None)
        if router is None:
            return
        if provider:
            router.preferred_provider = provider
            router.preferred_model = model or None
            await self._log("info", "router", f"provider set → {provider}/{model or 'auto'}")
            await self._broadcast(self._frame("provider.status", {"providers": self._providers()}))
        else:
            await self._safe_send(ws, self._frame("error", {"code": "bad_request", "message": "provider required"}))

    async def _set_mode(self, ws, payload: dict[str, Any]) -> None:
        mode = str(payload.get("mode", "") or "").lower()
        permissions = getattr(self.kernel, "permissions", None)
        if permissions is None:
            return
        if mode not in _MODES:
            await self._safe_send(ws, self._frame("error", {"code": "bad_request", "message": f"unknown mode '{mode}'"}))
            return
        permissions.set_mode(mode)
        await self._log("info", "daemon", f"mode set → {mode}")

    def _build_tree(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        requested = str(payload.get("path", "") or ".").strip()
        base = Path(self.project_dir)
        target = (base / requested).resolve()
        try:
            target.relative_to(base.resolve())
        except ValueError:
            return None
        if not target.exists():
            return None
        return self._node(target, base, depth=2)

    def _node(self, path: Path, base: Path, depth: int) -> dict[str, Any]:
        rel = str(path.relative_to(base)).replace("\\", "/") or "."
        name = path.name or str(path)
        if path.is_file():
            return {
                "name": name,
                "path": rel,
                "type": "file",
                "size": path.stat().st_size if path.exists() else 0,
                "ext": path.suffix.lstrip(".") or None,
            }
        children = []
        if depth > 0:
            try:
                for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                    if child.name.startswith((".", "__pycache__", "node_modules", "dist", ".venv", ".git")):
                        continue
                    children.append(self._node(child, base, depth - 1))
            except OSError:
                pass
        return {"name": name, "path": rel, "type": "dir", "children": children}

    # ── state helpers ──────────────────────────────────────────────────────

    def _hello_payload(self) -> dict[str, Any]:
        providers = self._providers()
        active = ""
        active_model = ""
        router = getattr(self.kernel, "router", None)
        if router is not None:
            active = getattr(router, "preferred_provider", None) or getattr(router, "_last_provider", None) or ""
            if not active and providers:
                active = providers[0]["id"]
            active_model = getattr(router, "preferred_model", None) or getattr(router, "_last_model", None) or ""
            if not active_model and active:
                for p in providers:
                    if p["id"] == active and p["models"]:
                        active_model = p["models"][0]["id"]
        return {
            "daemon": _DAEMON_NAME,
            "version": _DAEMON_VERSION,
            "capabilities": _CAPABILITIES,
            "providers": providers,
            "activeProvider": active,
            "activeModel": active_model,
        }

    def _providers(self) -> list[dict[str, Any]]:
        router = getattr(self.kernel, "router", None)
        status = dict(getattr(router, "status", {}) or {}) if router is not None else {}
        out: list[dict[str, Any]] = []
        for name, info in status.items():
            model = str(info.get("model") or name)
            available = bool(info.get("available"))
            out.append({
                "id": name,
                "label": name.replace("_", " ").title(),
                "status": "online" if available else "offline",
                "models": [{"id": model, "label": model, "context": 0, "input": 0, "output": 0}],
            })
        return out

    @staticmethod
    def _mk_task(task_id: str, goal: str, status: str, progress: float,
                 run_id: str, detail: str | None = None) -> dict[str, Any]:
        return {
            "id": task_id,
            "title": goal[:80],
            "status": status,
            "progress": round(progress, 2),
            "createdAt": _now(),
            "updatedAt": _now(),
            "runId": run_id,
            "detail": detail,
        }

    # ── framing / transport ────────────────────────────────────────────────

    def _frame(self, type_: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        return {"seq": self._seq, "ts": _now(), "type": type_, "payload": payload}

    async def _agent(self, run_id: str, phase: str, label: str, detail: str | None = None) -> None:
        await self._broadcast(self._frame("agent.event", {
            "id": uuid.uuid4().hex[:8],
            "runId": run_id,
            "phase": phase,
            "label": label,
            "detail": detail,
            "ts": _now(),
        }))

    async def _log(self, level: str, source: str, message: str) -> None:
        await self._broadcast(self._frame("log", {
            "id": uuid.uuid4().hex[:8],
            "level": level,
            "source": source,
            "message": message,
            "ts": _now(),
        }))

    async def _broadcast(self, frame: dict[str, Any]) -> None:
        for ws in list(self._clients):
            await self._safe_send(ws, frame)

    @staticmethod
    async def _safe_send(ws, frame: dict[str, Any]) -> None:
        try:
            await ws.send(json.dumps(frame, default=str))
        except Exception:
            pass

    # ── ambient telemetry ──────────────────────────────────────────────────

    async def _telemetry_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                return
            if not self._clients:
                continue
            cpu = mem = 0.0
            if _HAS_PSUTIL:
                try:
                    cpu = psutil.cpu_percent(interval=None)
                    mem = psutil.virtual_memory().percent
                except Exception:
                    cpu = mem = 0.0
            await self._broadcast(self._frame("telemetry", {
                "ts": _now(),
                "cpu": round(cpu, 1),
                "mem": round(mem, 1),
                "gpu": 0,
                "netIn": 0,
                "netOut": 0,
                "tokensPerSec": 0,
                "latencyMs": 0,
                "activeRuns": 1 if self._current else 0,
            }))
