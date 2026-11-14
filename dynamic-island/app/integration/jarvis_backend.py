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
    request_id: int | None = None


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
    chunk_ready = Signal(int, str)               # (request_id, streaming text chunk)
    response_ready = Signal(object)              # AgentResponse
    status_changed = Signal(str)                 # status string
    state_changed = Signal(object)               # BackendState
    shutdown_complete = Signal()                 # emitted only after the worker has exited

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
        self._runtime = None
        self._max_queue_size = 50
        self._input_queue: queue.Queue[tuple[int | None, str]] = queue.Queue(maxsize=self._max_queue_size)
        self._request_id_counter = 0
        self._current_request_id: int | None = None
        self._current_task: asyncio.Task | None = None
        self._tasks_by_id: dict[int, asyncio.Task] = {}
        self._startup_error: Exception | None = None
        self._started_event = threading.Event()
        self._shutdown_event = threading.Event()
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
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Previous agent worker is still shutting down")
            self._state = BackendState.STARTING
            self._startup_error = None
            self._started_event.clear()
            self._shutdown_event.clear()
            self._input_queue = queue.Queue(maxsize=self._max_queue_size)
            self._tasks_by_id.clear()
            self._current_task = None
            self._current_request_id = None
            self._agent_loop = None
            self._runtime = None
            self._loop = None
            self._thread = threading.Thread(
                target=self._run_loop,
                name="jarvis-agent",
                daemon=True,
            )
            worker = self._thread
            try:
                # Start while holding the state lock so stop() cannot observe
                # an unstarted Thread and then race with worker.start().
                worker.start()
            except Exception as exc:
                self._set_state(BackendState.ERROR, error=exc)
                self._started_event.set()
                raise

        if wait:
            self._wait_until_ready(timeout)


    def cancel_request(self, request_id: int) -> bool:
        """Request cancellation of a specific in-flight agent run.

        This operation is request-scoped: the cancellation token is wired to
        the task created for that request ID, not to the agent loop as a
        whole. Cancelling one request leaves other in-flight or queued requests
        alone.

        Returns True only when the backend found an active, not-yet-done task
        for that exact request ID and scheduled cancellation on the worker loop.
        When the backend has no task for that ID it returns False and reports
        the outcome honestly, rather than falling back to the current request
        and pretending the named request was cancelled.
        """
        with self._state_lock:
            task = self._tasks_by_id.get(request_id)
            loop = self._loop
            if task is None or task.done() or loop is None:
                return False
        try:
            loop.call_soon_threadsafe(task.cancel)
            return True
        except RuntimeError:
            # asyncio Tasks must only be cancelled on their owning loop.
            # If scheduling is no longer possible, report failure rather than
            # mutating the Task from the caller's thread.
            logger.warning("Could not schedule cancellation for request %s", request_id)
            return False


    def send_message(self, text: str, *, request_id: int | None = None) -> int | None:
        """Queue a message for the agent (non-blocking).

        Assigns a request ID to the message and delivers it to the worker loop.
        If the queue is full, the message is rejected but the backend keeps any
        existing per-request state intact; rejecting one message never mutates
        the shared request counter, the current request ID, or other request IDs.

        Returns the request ID that was queued, or None when the backend is not
        in a state that accepts input or the input queue is full.
        """
        with self._state_lock:
            if self._state not in (BackendState.READY, BackendState.RUNNING):
                return None
            assigned_id = request_id
            if assigned_id is None:
                assigned_id = self._request_id_counter + 1

            try:
                # Queue insertion is non-blocking; keeping it under the state
                # lock makes ID allocation and acceptance one atomic operation.
                self._input_queue.put_nowait((assigned_id, text))
            except queue.Full:
                logger.debug(
                    "Input queue full, rejecting message "
                    f"(queue size: {self._input_queue.qsize()}, request_id: {assigned_id})"
                )
                return None

            if isinstance(assigned_id, int):
                self._request_id_counter = max(self._request_id_counter, assigned_id)

        return assigned_id


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
        worker_error: Exception | None = None
        loop: asyncio.AbstractEventLoop | None = None
        try:
            loop = asyncio.new_event_loop()
            with self._state_lock:
                self._loop = loop
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._main())
        except Exception as exc:
            worker_error = exc
            logger.exception("Backend worker failed")
        finally:
            if loop is not None:
                try:
                    loop.close()
                except Exception:
                    logger.exception("Could not close backend event loop")
                with self._state_lock:
                    if self._loop is loop:
                        self._loop = None
                asyncio.set_event_loop(None)

            if worker_error is not None and not self._shutdown_event.is_set():
                try:
                    self._set_state(BackendState.ERROR, error=worker_error)
                except Exception:
                    logger.exception("Backend failed to report worker error")
            elif self.state != BackendState.STOPPED:
                try:
                    self._set_state(BackendState.STOPPED)
                except Exception:
                    logger.exception("Backend failed to report stopped state")

    def stop(self, wait: bool = True, timeout: float = 10.0) -> bool:
        """Stop the worker thread gracefully and report confirmed termination.

        The shutdown sequence is deliberately bounded:

        1. Reject new input from this point forward.
        2. Wake the worker loop if it is blocked waiting on the input queue.
        3. Let the worker finish its current iteration and release asyncio
           resources on its own thread.
        4. Wait for the worker thread to terminate, with an explicit timeout.
        5. Emit shutdown_complete only when the thread actually terminated.
           A timeout leaves the state STOPPING and returns False.

        The method never calls loop.stop() from another thread as normal
        control flow. If the worker still has work in flight when the timeout
        expires, that is reported rather than forcibly cut off.
        """
        with self._state_lock:
            worker = self._thread
            if self._state == BackendState.STOPPED and (
                worker is None or not worker.is_alive()
            ):
                already_stopped = True
                task = None
                loop = None
            else:
                already_stopped = False
                self._state = BackendState.STOPPING
                # Cancel the current request on the worker's own loop.
                task = self._current_task
                loop = self._loop
        if already_stopped:
            self.shutdown_complete.emit()
            return True
        self._shutdown_event.set()
        if task is not None and loop is not None and not task.done():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except Exception:
                # Do not call Task.cancel() directly from this thread. The
                # shutdown event and queue wake-up still let the worker exit
                # once its current operation returns.
                logger.warning("Could not schedule cancellation during backend shutdown")

        # Wake the worker loop out of a blocking input-queue get(), if any.
        try:
            self._input_queue.put_nowait((None, ""))
        except Exception:
            pass

        if worker is threading.current_thread():
            logger.warning("Backend stop was requested from its own worker thread")
            return False
        if (
            worker is not None
            and wait
            and (getattr(worker, "ident", None) is not None or not hasattr(worker, "ident"))
        ):
            worker.join(timeout=timeout)

        with self._state_lock:
            if worker is not None and worker.is_alive():
                logger.warning(
                    "Backend thread did not stop gracefully within timeout; "
                    "remaining work was not forcibly cancelled."
                )
                self._state = BackendState.STOPPING
                return False
            self._state = BackendState.STOPPED
            self._agent_loop = None
            self._loop = None
            self._current_request_id = None
            self._tasks_by_id.clear()
            self._input_queue = queue.Queue(maxsize=self._max_queue_size)
            self.shutdown_complete.emit()
            return True

    async def _main(self) -> None:
        """Build and run the agent through the canonical composition root."""
        if self._shutdown_event.is_set():
            return
        from runtime.kernel import build_kernel, close_kernel

        try:
            # Re-check after importing the composition root; shutdown may have
            # been requested while the module was being imported.
            if self._shutdown_event.is_set():
                return
            runtime = build_kernel(
                mode=self._mode,
                max_iterations=self._max_iterations,
                confirmation_handler=self._confirmation_handler,
            )
            with self._state_lock:
                self._runtime = runtime
                self._agent_loop = runtime.agent_loop

            # A stop can arrive while build_kernel() is running. The finally
            # block below still closes the newly created runtime.
            if self._shutdown_event.is_set():
                return

            self._set_state(BackendState.READY)
            self.status_changed.emit("ready")
            self._started_event.set()

            while (
                not self._shutdown_event.is_set()
                and self.state in (BackendState.READY, BackendState.RUNNING)
            ):
                # Never block the asyncio event loop on the thread-safe
                # producer queue. This keeps cancellation and model-change
                # callbacks responsive while the backend is idle.
                item = await asyncio.to_thread(self._input_queue.get)
                request_id, text = item
                if not text or not str(text).strip():
                    continue
                with self._state_lock:
                    # Re-check after queue.get(): stop() may have changed the
                    # state while this worker was waiting for an item.
                    if (
                        self._shutdown_event.is_set()
                        or self._state not in (BackendState.READY, BackendState.RUNNING)
                    ):
                        break
                    task = self._loop.create_task(
                        self._run_agent_with_id(text, request_id)
                    )
                    self._current_task = task
                    self._current_request_id = request_id
                    if isinstance(request_id, int):
                        self._tasks_by_id[request_id] = task
                    self._set_state(BackendState.RUNNING)
                try:
                    await task
                finally:
                    with self._state_lock:
                        self._current_task = None
                        self._current_request_id = None
                        if isinstance(request_id, int):
                            self._tasks_by_id.pop(request_id, None)
                        if (
                            not self._shutdown_event.is_set()
                            and self._state != BackendState.STOPPING
                        ):
                            self._set_state(BackendState.READY)
        finally:
            with self._state_lock:
                runtime = self._runtime
            try:
                if runtime is not None:
                    close_kernel(runtime)
            finally:
                with self._state_lock:
                    self._runtime = None
                    self._agent_loop = None

    async def _run_agent_with_id(self, text: str, request_id: int) -> None:
        """Execute one agent run with a request ID and support cancellation."""
        start = time.time()
        try:
            def on_chunk(chunk: str) -> None:
                self.chunk_ready.emit(request_id, chunk)

            result = await self._agent_loop.run(text, session_id=self._session_id, on_chunk=on_chunk)
            duration_ms = (time.time() - start) * 1000
            response = AgentResponse(
                success=result.success,
                text=result.response or "",
                trace_id=result.trace_id or "",
                error=result.error or "",
                duration_ms=duration_ms,
                tool_calls=[tc.get("name", "") for tc in result.state.tool_calls] if result.state else [],
                request_id=request_id,
            )
            self.response_ready.emit(response)
        except asyncio.CancelledError:
            # Re-emit as an error response rather than propagating the cancel
            self.response_ready.emit(AgentResponse(
                success=False, text="",
                error=f"Request {request_id} was cancelled",
                duration_ms=(time.time() - start) * 1000,
                request_id=request_id,
            ))
        except Exception as exc:
            logger.exception("Agent run failed")
            self.response_ready.emit(AgentResponse(
                success=False, text="", error=str(exc)[:500],
                duration_ms=(time.time() - start) * 1000,
                request_id=request_id,
            ))

    def set_model(self, model: str, timeout: float = 2.0) -> bool:
        """Apply a model change on the agent loop and wait for completion.

        Callers outside the agent thread retain synchronous semantics. Calls
        already running on the agent loop execute directly to avoid deadlock.
        """
        with self._state_lock:
            loop = self._loop
            agent_loop = self._agent_loop
            if (
                loop is None
                or agent_loop is None
                or self._state not in (BackendState.READY, BackendState.RUNNING)
            ):
                return False

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        setter = agent_loop.router.set_default_model
        if current_loop is loop:
            try:
                setter(model)
                return True
            except Exception:
                logger.exception("Could not apply model change on agent loop")
                return False

        completed = threading.Event()
        errors: list[Exception] = []

        def apply_model() -> None:
            try:
                setter(model)
            except Exception as exc:
                errors.append(exc)
            finally:
                completed.set()

        try:
            loop.call_soon_threadsafe(apply_model)
        except Exception:
            logger.exception("Could not schedule model change; backend loop is stopping")
            return False

        if not completed.wait(timeout=max(0.0, timeout)):
            logger.warning("Timed out waiting for model change to complete")
            return False
        if errors:
            logger.error("Model change failed: %s", errors[0])
            return False
        return True

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
