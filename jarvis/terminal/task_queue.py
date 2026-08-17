"""Sprint 12 -- Background task queue with cancellation support.

Runs agent tasks in a background thread pool while the terminal stays
responsive.  Each task gets a cancellation token that can interrupt it.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.terminal.task_queue")


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


class TaskQueue:
    """Background task queue with cooperative cancellation.

    Usage:
        queue = TaskQueue()
        queue.start()

        token, task = queue.submit(my_coroutine, arg1, arg2)
        # ... later ...
        queue.cancel(task.id)
        queue.stop()
    """

    def __init__(self, max_workers: int = 2):
        self._max_workers = max_workers
        self._tasks: dict[str, QueuedTask] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                         name="jarvis-task-queue")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def submit(self, coro_factory: Callable[[CancellationToken], Awaitable[Any]],
               description: str = "") -> tuple[CancellationToken, QueuedTask]:
        """Submit an async task.  The factory receives a CancellationToken.

        Returns (token, task) so the caller can cancel or inspect status.
        """
        task = QueuedTask(description=description)
        self._tasks[task.id] = task
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._run_task(task, coro_factory), self._loop,
            )
        return task.token, task

    def cancel(self, task_id: str, reason: str = "user cancelled") -> bool:
        task = self._tasks.get(task_id)
        if task and task.state == TaskState.RUNNING:
            task.token.cancel(reason)
            return True
        return False

    def cancel_all(self, reason: str = "bulk cancel") -> int:
        count = 0
        for task in self._tasks.values():
            if task.state == TaskState.RUNNING:
                task.token.cancel(reason)
                count += 1
        return count

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

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _run_task(self, task: QueuedTask,
                        coro_factory: Callable[[CancellationToken], Awaitable[Any]]) -> None:
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
