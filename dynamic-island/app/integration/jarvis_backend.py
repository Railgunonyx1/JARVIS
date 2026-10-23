"""Bridge between the Qt UI and the existing JARVIS agent core.

Runs AgentLoop in a dedicated worker thread with its own asyncio event loop.
The Qt main thread never blocks on agent I/O — communication is via
thread-safe queues and Qt signals.

All public signals are emitted from the worker thread but are safe to connect
to Qt slots on the main thread — Qt automatically delivers them via
queued connections when crossing threads.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("jarvis.desktop.backend")


@dataclass
class AgentResponse:
    """Result of an agent run, delivered to the UI."""
    success: bool
    text: str
    trace_id: str = ""
    error: str = ""
    duration_ms: float = 0.0
    tool_calls: list = field(default_factory=list)


class BackendState(StrEnum):
    """Backend lifecycle states."""
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class JarvisBackend(QObject):
    """Thread-safe wrapper around AgentLoop for desktop use.

    Usage:
        backend = JarvisBackend()
        backend.chunk_ready.connect(my_chunk_handler)
        backend.response_ready.connect(my_response_handler)
        backend.status_changed.connect(my_status_handler)
        backend.start()
        backend.send_message("Hello JARVIS")
        backend.stop()
    """

    # Signals — all emitted from the worker thread but safe to connect to
    # Qt slots on the main thread (Qt uses queued connections across threads).
    chunk_ready = Signal(str)                    # streaming text chunk
    response_ready = Signal(object)              # AgentResponse
    status_changed = Signal(str)                 # status string
    state_changed = Signal(object)               # BackendState

    def __init__(self, *, mode: str = "agent", max_iterations: int = 10,
                 confirmation_handler: Callable[[str, dict], str] | None = None):
        super().__init__()
        self._mode = mode
        self._max_iterations = max_iterations
        self._confirmation_handler = confirmation_handler

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._state = BackendState.STOPPED
        self._state_lock = threading.RLock()
        self._agent_loop = None
        self._input_queue: queue.Queue[str] = queue.Queue()
        self._startup_error: Exception | None = None
        self._started_event = threading.Event()
        self._session_id = f"desktop-{int(time.time())}"

    @property
    def state(self) -> BackendState:
        with self._state_lock:
            return self._state

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._state in (BackendState.STARTING, BackendState.READY, BackendState.RUNNING)

    @property
    def startup_error(self) -> Exception | None:
        return self._startup_error

    def start(self, wait: bool = True, timeout: float = 10.0) -> None:
        """Start the worker thread and asyncio event loop.

        Args:
            wait: If True, block until backend is ready or fails (up to timeout).
            If False, returns immediately after starting the thread.
            timeout: Maximum seconds to wait when wait=True.
        """
        with self._state_lock:
            if self._state in (BackendState.STARTING, BackendState.READY, BackendState.RUNNING):
                return
            self._state = BackendState.STARTING
            self._startup_error = None
            self._started_event.clear()

        self._thread = threading.Thread(target=self._run_loop, name="jarvis-agent", daemon=True)
        self._thread.start()

        if wait:
            self._wait_until_ready(timeout)

    def stop(self, wait: bool = True, timeout: float = 10.0) -> None:
        """Stop the worker thread gracefully.

        Args:
            wait: If True, wait for graceful shutdown (up to timeout).
            timeout: Maximum seconds to wait when wait=True.
        """
        with self._state_lock:
            if self._state == BackendState.STOPPED:
                return
            self._state = BackendState.STOPPING

        # Signal the worker thread to stop by putting a sentinel in the queue.
        # The _main() loop checks self.state each iteration and will exit
        # when it sees STOPPING. Putting None in the queue unblocks get()
        # if it's currently waiting.
        if self._input_queue:
            try:
                self._input_queue.put_nowait(None)
            except Exception:
                pass

        if self._thread and wait:
            self._thread.join(timeout=timeout)

        # If the thread is still alive after the timeout, force-stop the loop
        # as a last resort. This can interrupt active work, so only use it
        # when the graceful shutdown timed out.
        if self._thread and self._thread.is_alive():
            logger.warning("Backend thread did not stop gracefully, forcing stop")
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5.0)

        with self._state_lock:
            self._state = BackendState.STOPPED
            self._agent_loop = None
            self._loop = None

    def send_message(self, text: str) -> None:
        """Queue a message for the agent (non-blocking)."""
        self._input_queue.put(text)

    def _wait_until_ready(self, timeout: float = 10.0) -> None:
        start = time.time()
        while time.time() - start < timeout:
            state = self.state
            if state == BackendState.READY:
                return
            if state == BackendState.ERROR:
                raise RuntimeError(f"Agent backend failed to start: {self._startup_error}")
            if state == BackendState.STOPPED:
                raise RuntimeError("Agent backend was stopped during startup")
            time.sleep(0.05)
        raise RuntimeError(f"Agent backend failed to start within {timeout}s")

    def _run_loop(self) -> None:
        """Worker thread entry: own asyncio event loop."""
        startup_error: Exception | None = None
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            try:
                self._loop.run_until_complete(self._main())
            except Exception as e:
                startup_error = e
                logger.exception("Backend startup failed")
            finally:
                self._loop.close()
                self._loop = None
        if startup_error is not None:
            # Preserve the original startup error so it is not lost
            # when the lifecycle subsequently settles to STOPPED.
            self._set_state(BackendState.ERROR, error=startup_error)
        elif self.state != BackendState.STOPPED:
            self._set_state(BackendState.STOPPED)

    async def _main(self) -> None:
        """Build the agent and process queued messages."""
        from core.agent.loop import AgentLoop
        from core.agent.permissions import PermissionEngine
        from core.agent.tool_service import ToolExecutionService
        from core.agent.tools import AgentToolExecutor
        from core.decision_logger import get_decision_logger
        from core.project import ProjectContext
        from memory.mem import get_mem
        from providers.router import ProviderRouter
        from runtime.event_bus import get_event_bus
        from tools import build_default_registry

        models_config = self._load_models_config()
        from core.api_keys import router_api_keys
        router = ProviderRouter(models_config, router_api_keys())
        registry = build_default_registry()
        project = ProjectContext.discover()
        event_bus = get_event_bus()
        logger_ = get_decision_logger()
        permissions = PermissionEngine(logger_, mode=self._mode,
                                       confirmation_handler=self._confirmation_handler)
        executor = AgentToolExecutor(registry, logger_)
        tool_service = ToolExecutionService(
            registry=registry, permissions=permissions, executor=executor,
            decision_logger=logger_, bus=event_bus, mode=self._mode,
        )
        mem = get_mem()

        self._agent_loop = AgentLoop(
            router=router, registry=registry, project=project,
            decision_logger=logger_, mode=self._mode,
            max_iterations=self._max_iterations,
            confirmation_handler=self._confirmation_handler,
            mem=mem, event_bus=event_bus, tool_service=tool_service,
        )

        self._set_state(BackendState.READY)
        self.status_changed.emit("ready")
        self._started_event.set()

        while self.state in (BackendState.READY, BackendState.RUNNING):
            try:
                text = self._input_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if not text or not str(text).strip():
                continue
            await self._run_agent(text)

    async def _run_agent(self, text: str) -> None:
        """Execute one agent run and deliver results."""
        start = time.time()
        try:
            def on_chunk(chunk: str) -> None:
                self.chunk_ready.emit(chunk)

            result = await self._agent_loop.run(text, session_id=self._session_id, on_chunk=on_chunk)
            duration_ms = (time.time() - start) * 1000
            response = AgentResponse(
                success=result.success,
                text=result.response or "",
                trace_id=result.trace_id or "",
                error=result.error or "",
                duration_ms=duration_ms,
                tool_calls=[tc.get("name", "") for tc in result.state.tool_calls] if result.state else [],
            )
            self.response_ready.emit(response)
        except Exception as exc:
            logger.exception("Agent run failed")
            self.response_ready.emit(AgentResponse(
                success=False, text="", error=str(exc)[:500],
                duration_ms=(time.time() - start) * 1000,
            ))

    def set_model(self, model: str) -> None:
        """Set the active model for subsequent agent runs."""
        if self._agent_loop:
            self._agent_loop.router.set_default_model(model)

    def _set_state(self, state: BackendState, error: Exception | None = None) -> None:
        with self._state_lock:
            old_state = self._state
            self._state = state
            self._startup_error = error
        if old_state != state:
            self.state_changed.emit(state)
            if state == BackendState.READY:
                self._started_event.set()

    def _emit_status(self, status: str) -> None:
        self.status_changed.emit(status)

    def _load_models_config(self) -> dict:
        try:
            from core.config import Config
            c = Config()
            return c.get_section("models") or {}
        except Exception:
            return {}
