"""Persistent Runtime — async event loop that keeps the CLI responsive.

Replaces the blocking asyncio.run() pattern with a persistent loop where:
- Main agent task runs as an asyncio.Task
- Input reader runs in a thread (via run_in_executor)
- Interrupt executor runs as a separate Task (never blocks main)
- UI updates reactively from events

Architecture:
    Main Thread                    Event Loop Thread
    ───────────                    ─────────────────
    input() [blocking]  ──────►   main_task (3B/4B)
                                  interrupt_task (1.5B)
                                  event rendering
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger("jarvis.runtime")


class PersistentRuntime:
    """Manages a persistent asyncio event loop for the CLI.

    The event loop runs in the main thread. Blocking I/O (stdin reads)
    runs in a thread pool executor. Agent tasks and interrupts run as
    concurrent asyncio Tasks on the shared loop.
    """

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="jarvis-io")
        self._main_task: asyncio.Task | None = None
        self._interrupt_task: asyncio.Task | None = None
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._shutdown = threading.Event()
        self._task_counter = 0

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    @property
    def is_main_running(self) -> bool:
        return self._main_task is not None and not self._main_task.done()

    @property
    def is_interrupt_running(self) -> bool:
        return self._interrupt_task is not None and not self._interrupt_task.done()

    def _next_task_id(self) -> str:
        self._task_counter += 1
        return f"task_{self._task_counter}"

    async def read_input(self, prompt: str) -> str:
        """Read a line from stdin without blocking the event loop.

        Runs the blocking input() in a thread pool executor so the event
        loop continues processing other tasks (main agent, interrupts).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, lambda: input(prompt))

    async def run_main_task(
        self,
        coro_factory: Callable[[], Awaitable[Any]],
        task_id: str | None = None,
    ) -> Any:
        """Run the main agent task with cancellation support.

        Only one main task can run at a time. If a main task is already
        running, this raises RuntimeError.
        """
        if self.is_main_running:
            raise RuntimeError("A main task is already running")

        task_id = task_id or self._next_task_id()
        self._main_task = asyncio.create_task(
            coro_factory(), name=f"main-{task_id}"
        )
        self._active_tasks[task_id] = self._main_task

        try:
            result = await self._main_task
            return result
        except asyncio.CancelledError:
            logger.info("Main task %s cancelled", task_id)
            raise
        finally:
            self._active_tasks.pop(task_id, None)
            if self._main_task is self._main_task:
                self._main_task = None

    async def run_interrupt(
        self,
        coro_factory: Callable[[], Awaitable[Any]],
        timeout: float = 10.0,
    ) -> Any:
        """Run an interrupt task concurrently with the main task.

        The interrupt runs on 1B with a hard timeout. If the main task
        is running, the interrupt executes alongside it without blocking.
        """
        if self.is_interrupt_running:
            logger.warning("Interrupt already running, skipping")
            return None

        task_id = f"interrupt_{self._next_task_id()}"
        self._interrupt_task = asyncio.create_task(
            coro_factory(), name=task_id
        )
        self._active_tasks[task_id] = self._interrupt_task

        try:
            result = await asyncio.wait_for(self._interrupt_task, timeout=timeout)
            return result
        except TimeoutError:
            logger.warning("Interrupt %s timed out after %.0fs", task_id, timeout)
            self._interrupt_task.cancel()
            try:
                await self._interrupt_task
            except asyncio.CancelledError:
                pass
            return None
        except asyncio.CancelledError:
            return None
        finally:
            self._active_tasks.pop(task_id, None)
            self._interrupt_task = None

    def cancel_main(self) -> bool:
        """Cancel the current main task. Returns True if cancelled."""
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
            return True
        return False

    def cancel_all(self) -> None:
        """Cancel all running tasks."""
        for task_id, task in list(self._active_tasks.items()):
            if not task.done():
                task.cancel()
                logger.info("Cancelled task %s", task_id)
        self._active_tasks.clear()
        self._main_task = None
        self._interrupt_task = None

    def shutdown(self) -> None:
        """Clean shutdown of the runtime."""
        self._shutdown.set()
        self.cancel_all()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._executor.shutdown(wait=False)

    def run_coroutine_sync(self, coro) -> Any:
        """Run a coroutine on the event loop from a synchronous context.

        If the loop is running (in another thread), uses run_coroutine_threadsafe.
        If not running, uses run_until_complete.
        """
        if self._loop is None or self._loop.is_closed():
            # No loop yet — create one and run directly
            return asyncio.run(coro)

        if self._loop.is_running():
            # Loop is running in another thread — submit and wait
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result(timeout=60)
        else:
            # Loop exists but not running — run it
            return self._loop.run_until_complete(coro)

    def get_status(self) -> dict[str, Any]:
        """Return runtime status for diagnostics."""
        return {
            "loop_running": self._loop.is_running() if self._loop else False,
            "main_running": self.is_main_running,
            "interrupt_running": self.is_interrupt_running,
            "active_tasks": len(self._active_tasks),
            "task_ids": list(self._active_tasks.keys()),
        }


# ── Global runtime singleton ────────────────────────────────────────────

_runtime: PersistentRuntime | None = None


def get_runtime() -> PersistentRuntime:
    """Get the process-wide persistent runtime."""
    global _runtime
    if _runtime is None:
        _runtime = PersistentRuntime()
    return _runtime
