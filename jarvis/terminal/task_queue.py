"""Sprint 13B -- Production task queue with ThreadPoolExecutor.

Real concurrency via concurrent.futures.  Pending tasks queue up and
dispatch when a worker slot opens.  Graceful shutdown drains in-flight
work and waits for pending tasks or times out.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.terminal.task_queue")

_SHUTDOWN_SENTINEL = object()


class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CancellationToken:
    """Cooperative cancellation signal shared between queue and task."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._reason: str = ""

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def cancel(self, reason: str = "user cancelled") -> None:
        self._reason = reason
        self._cancelled.set()

    def check(self) -> None:
        """Raise if cancelled.  Call this in long-running loops."""
        if self._cancelled.is_set():
            raise CancelledError(self._reason)


class CancelledError(Exception):
    pass


@dataclass
class QueuedTask:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    state: TaskState = TaskState.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str = ""
    result: Any = None
    token: CancellationToken = field(default_factory=CancellationToken)
    _future: Future | None = field(default=None, repr=False)


class TaskQueue:
    """Production task queue backed by a single event-loop thread.

    All coroutines run on one dedicated asyncio event loop, preserving
    asyncio semantics.  ``max_workers`` is enforced by a semaphore
    inside the loop; tasks that arrive while all slots are busy are
    kept in a pending queue and dispatched as slots free up.

    Usage::

        queue = TaskQueue(max_workers=4)
        queue.start()

        token, task = queue.submit(my_coroutine)
        queue.cancel(task.id)
        queue.stop(shutdown_timeout=10)
    """

    def __init__(self, max_workers: int = 2):
        self._max_workers = max_workers
        self._tasks: dict[str, QueuedTask] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._running = False
        self._ready = threading.Event()
        self._pending: deque[tuple[QueuedTask, Any]] = deque()
        self._semaphore: asyncio.Semaphore | None = None

    # ── lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loop_thread = threading.Thread(
            target=self._run_loop, daemon=True, name="jarvis-task-queue",
        )
        self._loop_thread.start()
        self._ready.wait(timeout=5.0)

    def stop(self, shutdown_timeout: float = 5.0) -> None:
        """Graceful shutdown: cancel all running tasks, drain pending, stop loop."""
        if not self._running or self._loop is None:
            return
        self._running = False

        def _shutdown() -> None:
            if self._semaphore is not None:
                self._semaphore.release(self._max_workers)
            self._pending.clear()
            self._loop.call_soon_threadsafe(self._loop.stop)  # type: ignore[union-attr]

        self._loop.call_soon_threadsafe(_shutdown)  # type: ignore[union-attr]
        if self._loop_thread:
            self._loop_thread.join(timeout=shutdown_timeout)
            self._loop_thread = None

    # ── submission ────────────────────────────────────────────────────

    def submit(self, coro_factory, description: str = "") -> tuple[CancellationToken, QueuedTask]:
        """Submit an async task.  Returns (token, task)."""
        task = QueuedTask(description=description)
        self._tasks[task.id] = task
        if self._loop and self._loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(
                self._guarded_run(task, coro_factory), self._loop,
            )
            task._future = fut
        return task.token, task

    async def _guarded_run(self, task: QueuedTask, coro_factory) -> Any:
        """Acquire semaphore slot, run task, release slot, dispatch pending."""
        assert self._semaphore is not None
        await self._semaphore.acquire()
        try:
            await self._execute(task, coro_factory)
        finally:
            self._semaphore.release()
            self._dispatch_pending()

    def _dispatch_pending(self) -> None:
        """Start as many pending tasks as there are free slots."""
        while self._pending and self._running:
            task, coro_factory = self._pending.popleft()
            if task.state != TaskState.PENDING:
                continue
            fut = asyncio.run_coroutine_threadsafe(
                self._guarded_run(task, coro_factory), self._loop,  # type: ignore[arg-type]
            )
            task._future = fut

    async def _execute(self, task: QueuedTask, coro_factory) -> None:
        """Run a single task coroutine, update state."""
        task.state = TaskState.RUNNING
        task.started_at = time.time()
        try:
            result = await coro_factory(task.token)
            task.result = result
            task.state = TaskState.COMPLETED
        except CancelledError as e:
            task.state = TaskState.CANCELLED
            task.error = str(e)
        except Exception as e:
            task.state = TaskState.FAILED
            task.error = str(e)[:500]
            logger.error("Task %s failed: %s", task.id, e)
        finally:
            task.finished_at = time.time()

    # ── cancellation ──────────────────────────────────────────────────

    def cancel(self, task_id: str, reason: str = "user cancelled") -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        if task.state == TaskState.RUNNING:
            task.token.cancel(reason)
            if task._future is not None:
                task._future.cancel()
            return True
        if task.state == TaskState.PENDING:
            task.state = TaskState.CANCELLED
            task.error = reason
            task.finished_at = time.time()
            return True
        return False

    def cancel_all(self, reason: str = "bulk cancel") -> int:
        count = 0
        for task in self._tasks.values():
            if task.state in (TaskState.RUNNING, TaskState.PENDING):
                if self.cancel(task.id, reason):
                    count += 1
        return count

    # ── queries ───────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> QueuedTask | None:
        return self._tasks.get(task_id)

    @property
    def active_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.state == TaskState.RUNNING)

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.state == TaskState.PENDING)

    def recent(self, limit: int = 10) -> list[QueuedTask]:
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]

    # ── internal ──────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._semaphore = asyncio.Semaphore(self._max_workers)
        self._ready.set()
        self._loop.run_forever()
