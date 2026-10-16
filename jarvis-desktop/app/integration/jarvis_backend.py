"""Bridge between the Qt UI and the existing JARVIS agent core.

Runs AgentLoop in a dedicated worker thread with its own asyncio event loop.
The Qt main thread never blocks on agent I/O — communication is via
thread-safe queues and Qt signals.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

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


class JarvisBackend:
    """Thread-safe wrapper around AgentLoop for desktop use.

    Usage:
        backend = JarvisBackend()
        backend.start()
        backend.send_message("Hello JARVIS")
        # connect to backend.chunk_ready / backend.response_ready signals
        backend.stop()
    """

    def __init__(self, *, mode: str = "agent", max_iterations: int = 10,
                 on_chunk: Callable[[str], None] | None = None,
                 on_response: Callable[[AgentResponse], None] | None = None,
                 on_status: Callable[[str], None] | None = None,
                 confirmation_handler: Callable[[str, dict], str] | None = None):
        self._mode = mode
        self._max_iterations = max_iterations
        self._on_chunk = on_chunk
        self._on_response = on_response
        self._on_status = on_status
        self._confirmation_handler = confirmation_handler

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._agent_loop = None
        self._input_queue: queue.Queue[str] = queue.Queue()
        self._status_queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._session_id = f"desktop-{int(time.time())}"

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the worker thread and asyncio event loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="jarvis-agent", daemon=True)
        self._thread.start()
        self._wait_until_ready()

    def stop(self) -> None:
        """Stop the worker thread gracefully."""
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5.0)
        self._agent_loop = None
        self._loop = None

    def send_message(self, text: str) -> None:
        """Queue a message for the agent (non-blocking)."""
        self._input_queue.put(text)

    def _wait_until_ready(self, timeout: float = 10.0) -> None:
        start = time.time()
        while time.time() - start < timeout:
            if self._agent_loop is not None:
                return
            time.sleep(0.05)
        raise RuntimeError("Agent backend failed to start")

    def _run_loop(self) -> None:
        """Worker thread entry: own asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception:
            logger.exception("Agent loop crashed")
        finally:
            self._loop.close()

    async def _main(self) -> None:
        """Build the agent and process queued messages."""
        from core.config import Config
        from core.project import ProjectContext
        from providers.router import ProviderRouter
        from tools import build_default_registry
        from core.agent.loop import AgentLoop
        from core.agent.permissions import PermissionEngine
        from core.agent.tool_service import ToolExecutionService
        from core.agent.tools import AgentToolExecutor
        from core.decision_logger import get_decision_logger
        from runtime.event_bus import get_event_bus
        from memory.mem import get_mem

        config = Config()
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

        self._emit_status("ready")

        while self._running:
            try:
                text = self._input_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if not text.strip():
                continue
            await self._run_agent(text)

    async def _run_agent(self, text: str) -> None:
        """Execute one agent run and deliver results."""
        start = time.time()
        try:
            def on_chunk(chunk: str) -> None:
                if self._on_chunk:
                    try:
                        self._on_chunk(chunk)
                    except Exception:
                        pass

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
            if self._on_response:
                self._on_response(response)
        except Exception as exc:
            logger.exception("Agent run failed")
            if self._on_response:
                self._on_response(AgentResponse(
                    success=False, text="", error=str(exc)[:500],
                    duration_ms=(time.time() - start) * 1000,
                ))

    def _emit_status(self, status: str) -> None:
        if self._on_status:
            try:
                self._on_status(status)
            except Exception:
                pass

    def _load_models_config(self) -> dict:
        try:
            from core.config import Config
            c = Config()
            return c.get_section("models") or {}
        except Exception:
            return {}
