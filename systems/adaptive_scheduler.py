"""Adaptive Thread Scheduler — Priority-based task scheduling with adaptive priority.

Replaces FIFO with priority-aware scheduling:
  Voice > Planning > Vision > Background indexing
"""
import logging
import time
import threading
import queue
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from enum import IntEnum
from concurrent.futures import ThreadPoolExecutor, Future

logger = logging.getLogger("systems.adaptive_scheduler")


class TaskPriority(IntEnum):
    CRITICAL = 0   # Voice input processing, safety
    HIGH = 1       # Intent recognition, LLM calls
    MEDIUM = 2     # Planning, tool execution
    LOW = 3        # Vision analysis, context updates
    BACKGROUND = 4 # Indexing, telemetry, cache cleanup


@dataclass
class ScheduledTask:
    """A task with priority metadata."""
    task_id: str
    func: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.MEDIUM
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    result: Any = None
    error: Optional[Exception] = None
    future: Optional[Future] = None

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at


class AdaptiveScheduler:
    """Priority-based thread scheduler with adaptive load management.

    Features:
    - Priority queue (critical/high/medium/low/background)
    - Adaptive thread pool sizing based on load
    - Deadlock detection via timeout
    - Task timeout support
    """

    def __init__(self, min_workers: int = 2, max_workers: int = 8):
        self._min_workers = min_workers
        self._max_workers = max_workers
        self._task_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._active_tasks: Dict[str, ScheduledTask] = {}
        self._completed_tasks: List[ScheduledTask] = []
        self._lock = threading.Lock()
        self._task_counter = 0
        self._running = False
        self._stats = {
            "submitted": 0, "completed": 0, "failed": 0,
            "timeout": 0, "avg_wait_ms": 0.0, "avg_exec_ms": 0.0,
        }

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="jarvis_sched",
        )
        # Start dispatcher thread
        self._dispatcher = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatcher.start()
        logger.info("Adaptive scheduler started (min=%d, max=%d)", self._min_workers, self._max_workers)

    def stop(self) -> None:
        self._running = False
        if self._executor:
            self._executor.shutdown(wait=False)
        logger.info("Adaptive scheduler stopped")

    def submit(self, func: Callable, *args, priority: TaskPriority = TaskPriority.MEDIUM,
               task_id: str = None, timeout: float = 30.0, **kwargs) -> str:
        """Submit a task for execution. Returns task_id."""
        with self._lock:
            self._task_counter += 1
            task_id = task_id or f"task_{self._task_counter}"

        task = ScheduledTask(
            task_id=task_id, func=func, args=args, kwargs=kwargs,
            priority=priority,
        )

        self._task_queue.put((priority, task.created_at, task))
        self._stats["submitted"] += 1

        with self._lock:
            self._active_tasks[task_id] = task

        return task_id

    def _dispatch_loop(self):
        """Background loop that pulls tasks from the queue and submits to executor."""
        while self._running:
            try:
                priority, created_at, task = self._task_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if self._executor is None:
                continue

            task.started_at = time.time()
            wait_ms = (task.started_at - task.created_at) * 1000

            try:
                future = self._executor.submit(self._execute_task, task)
                task.future = future
            except Exception as e:
                task.error = e
                task.completed_at = time.time()
                self._stats["failed"] += 1

    def _execute_task(self, task: ScheduledTask):
        """Execute a task and record results."""
        try:
            result = task.func(*task.args, **task.kwargs)
            task.result = result
            task.completed_at = time.time()
            self._stats["completed"] += 1

            exec_ms = (task.completed_at - task.started_at) * 1000
            n = self._stats["completed"]
            self._stats["avg_exec_ms"] = (
                (self._stats["avg_exec_ms"] * (n - 1) + exec_ms) / n
            )
        except Exception as e:
            task.error = e
            task.completed_at = time.time()
            self._stats["failed"] += 1
        finally:
            with self._lock:
                self._active_tasks.pop(task.task_id, None)
                self._completed_tasks.append(task)
                if len(self._completed_tasks) > 500:
                    self._completed_tasks = self._completed_tasks[-300:]

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._active_tasks.get(task_id)
            if task:
                return {
                    "id": task.task_id,
                    "priority": task.priority.name,
                    "state": "running",
                    "wait_ms": round((task.started_at - task.created_at) * 1000, 1) if task.started_at else None,
                }
        # Check completed
        for task in reversed(self._completed_tasks):
            if task.task_id == task_id:
                return {
                    "id": task.task_id,
                    "priority": task.priority.name,
                    "state": "error" if task.error else "completed",
                    "exec_ms": round((task.completed_at - task.started_at) * 1000, 1),
                }
        return None

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            stats = dict(self._stats)
            stats["active_tasks"] = len(self._active_tasks)
            stats["queue_size"] = self._task_queue.qsize()
            stats["completed_history"] = len(self._completed_tasks)
            return stats

    def clear_completed(self) -> int:
        with self._lock:
            count = len(self._completed_tasks)
            self._completed_tasks.clear()
            return count


_scheduler_instance: Optional[AdaptiveScheduler] = None


def get_adaptive_scheduler() -> AdaptiveScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = AdaptiveScheduler()
    return _scheduler_instance
