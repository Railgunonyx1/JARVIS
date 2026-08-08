"""JARVIS MK-X Hyper-Optimization Engine — Scheduler Optimizer.

Intelligent task scheduling with priority queues, deadline awareness,
preemption support, and resource utilization tracking.
"""

import heapq
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("jarvis.hyper_opt.scheduler_optimizer")

_TASK_COUNTER = 0


class _Task:
    """Internal representation of a schedulable task."""

    __slots__ = (
        "task_id", "fn", "priority", "deadline_ms", "dependencies",
        "status", "submitted_at", "started_at", "completed_at",
        "result", "error", "future",
    )

    def __init__(
        self,
        task_id: str,
        fn: Callable,
        priority: int = 5,
        deadline_ms: Optional[float] = None,
        dependencies: Optional[List[str]] = None,
    ):
        self.task_id = task_id
        self.fn = fn
        self.priority = priority
        self.deadline_ms = deadline_ms
        self.dependencies = dependencies or []
        self.status = "queued"
        self.submitted_at = time.perf_counter()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.result: Any = None
        self.error: Optional[str] = None
        self.future: Optional[Future] = None

    def __lt__(self, other: "_Task") -> bool:
        """Comparison for heapq: lower priority number = higher priority = dequeued first."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.submitted_at < other.submitted_at

    @property
    def wait_time_ms(self) -> float:
        if self.started_at is not None:
            return (self.started_at - self.submitted_at) * 1000.0
        return (time.perf_counter() - self.submitted_at) * 1000.0

    @property
    def execution_time_ms(self) -> Optional[float]:
        if self.started_at is not None and self.completed_at is not None:
            return (self.completed_at - self.started_at) * 1000.0
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "priority": self.priority,
            "deadline_ms": self.deadline_ms,
            "status": self.status,
            "wait_time_ms": round(self.wait_time_ms, 3),
            "execution_time_ms": round(self.execution_time_ms, 3) if self.execution_time_ms is not None else None,
            "dependencies": list(self.dependencies),
        }


class SchedulerOptimizer:
    """Intelligent task scheduling with priority, deadlines, and resource awareness."""

    def __init__(self, thread_pool_size: int = 4, max_queue_size: int = 256):
        self._task_queue: List[_Task] = []
        self._running_tasks: Dict[str, _Task] = {}
        self._completed_tasks: List[_Task] = []
        self._failed_tasks: List[_Task] = []
        self._thread_pool_size = thread_pool_size
        self._max_queue_size = max_queue_size
        self._lock = threading.RLock()
        self._total_scheduled = 0
        self._total_preempted = 0
        self._pool = ThreadPoolExecutor(
            max_workers=thread_pool_size,
            thread_name_prefix="jarvis-scheduler",
        )
        logger.info("SchedulerOptimizer initialized (pool_size=%d)", thread_pool_size)

    def schedule(
        self,
        task_id: str,
        fn: Callable,
        priority: int = 5,
        deadline_ms: Optional[float] = None,
        dependencies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Schedule a task with priority (1=highest, 10=lowest)."""
        with self._lock:
            if len(self._task_queue) >= self._max_queue_size:
                return {
                    "error": f"Queue full ({self._max_queue_size} tasks). Consider increasing priority of critical tasks.",
                    "task_id": task_id,
                }

            existing = {t.task_id for t in self._task_queue}
            existing.update(self._running_tasks.keys())
            if task_id in existing:
                return {"error": f"Task '{task_id}' already exists", "task_id": task_id}

            clamped_priority = max(1, min(10, priority))
            task = _Task(task_id, fn, clamped_priority, deadline_ms, dependencies)
            heapq.heappush(self._task_queue, task)
            self._total_scheduled += 1

            logger.info(
                "Scheduled task '%s' (priority=%d, deadline=%s, deps=%s)",
                task_id, clamped_priority, deadline_ms, dependencies or [],
            )
            return task.to_dict()

    def schedule_batch(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Schedule multiple tasks. Each task: {id, fn, priority, deadline_ms}."""
        results = []
        for task_spec in tasks:
            result = self.schedule(
                task_id=task_spec["id"],
                fn=task_spec["fn"],
                priority=task_spec.get("priority", 5),
                deadline_ms=task_spec.get("deadline_ms"),
                dependencies=task_spec.get("dependencies"),
            )
            results.append(result)
        return results

    def get_queue_status(self) -> Dict[str, Any]:
        """Returns queue_length, running_count, completed_count, avg_wait_ms."""
        with self._lock:
            wait_times = [t.wait_time_ms for t in self._task_queue]
            avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0.0

            completed_waits = [
                t.wait_time_ms for t in self._completed_tasks
                if t.wait_time_ms > 0
            ]
            avg_completed_wait = (
                sum(completed_waits) / len(completed_waits) if completed_waits else 0.0
            )

            return {
                "queue_length": len(self._task_queue),
                "running_count": len(self._running_tasks),
                "completed_count": len(self._completed_tasks),
                "failed_count": len(self._failed_tasks),
                "avg_wait_ms": round(avg_wait, 3),
                "avg_completed_wait_ms": round(avg_completed_wait, 3),
                "thread_pool_size": self._thread_pool_size,
            }

    def preempt(self, task_id: str) -> bool:
        """Preempt a low-priority task to make room for high-priority."""
        with self._lock:
            # Find in queue
            for i, task in enumerate(self._task_queue):
                if task.task_id == task_id:
                    preempted_task = self._task_queue.pop(i)
                    heapq.heapify(self._task_queue)
                    preempted_task.status = "preempted"
                    self._total_preempted += 1
                    self._completed_tasks.append(preempted_task)
                    logger.info("Preempted task '%s' (priority=%d)", task_id, preempted_task.priority)
                    return True

            # Check if running (can't truly preempt running threads, but mark them)
            if task_id in self._running_tasks:
                logger.warning("Task '%s' is running, cannot preempt", task_id)
                return False

            logger.warning("Task '%s' not found for preemption", task_id)
            return False

    def preempt_lowest_priority(self) -> Optional[str]:
        """Preempt the lowest-priority (highest number) task in the queue."""
        with self._lock:
            if not self._task_queue:
                return None

            # Find the lowest-priority task (highest priority number)
            worst_idx = 0
            for i, task in enumerate(self._task_queue):
                if task.priority > self._task_queue[worst_idx].priority:
                    worst_idx = i
                elif task.priority == self._task_queue[worst_idx].priority:
                    if task.submitted_at > self._task_queue[worst_idx].submitted_at:
                        worst_idx = i

            preempted_task = self._task_queue.pop(worst_idx)
            heapq.heapify(self._task_queue)
            preempted_task.status = "preempted"
            self._total_preempted += 1
            self._completed_tasks.append(preempted_task)
            logger.info(
                "Auto-preempted task '%s' (priority=%d) to make room",
                preempted_task.task_id, preempted_task.priority,
            )
            return preempted_task.task_id

    def get_stats(self) -> Dict[str, Any]:
        """Returns total_scheduled, total_preempted, avg_completion_ms, queue_utilization."""
        with self._lock:
            completions = [
                t.execution_time_ms for t in self._completed_tasks
                if t.execution_time_ms is not None
            ]
            avg_completion = (
                sum(completions) / len(completions) if completions else 0.0
            )
            utilization = (
                (len(self._running_tasks) / self._thread_pool_size) * 100
                if self._thread_pool_size > 0 else 0.0
            )

            return {
                "total_scheduled": self._total_scheduled,
                "total_preempted": self._total_preempted,
                "total_completed": len(self._completed_tasks),
                "total_failed": len(self._failed_tasks),
                "avg_completion_ms": round(avg_completion, 3),
                "queue_utilization_pct": round(utilization, 1),
                "pool_size": self._thread_pool_size,
            }

    def optimize_priority(self, task_id: str, adjustment: int) -> bool:
        """Dynamically adjust task priority based on deadlines."""
        with self._lock:
            for task in self._task_queue:
                if task.task_id == task_id:
                    old_priority = task.priority
                    new_priority = max(1, min(10, task.priority + adjustment))
                    task.priority = new_priority
                    heapq.heapify(self._task_queue)
                    logger.info(
                        "Adjusted task '%s' priority: %d -> %d (adjustment=%+d)",
                        task_id, old_priority, new_priority, adjustment,
                    )
                    return True

            if task_id in self._running_tasks:
                task = self._running_tasks[task_id]
                old_priority = task.priority
                task.priority = max(1, min(10, task.priority + adjustment))
                logger.info(
                    "Adjusted running task '%s' priority: %d -> %d",
                    task_id, old_priority, task.priority,
                )
                return True

            logger.warning("Task '%s' not found for priority adjustment", task_id)
            return False

    def apply_deadline_pressure(self) -> List[str]:
        """Boost priority of tasks approaching their deadlines. Returns boosted IDs."""
        with self._lock:
            now = time.perf_counter()
            boosted: List[str] = []

            for task in self._task_queue:
                if task.deadline_ms is not None and task.status == "queued":
                    elapsed_ms = (now - task.submitted_at) * 1000.0
                    remaining = task.deadline_ms - elapsed_ms
                    if remaining < 0:
                        # Already past deadline — maximum priority
                        task.priority = 1
                        boosted.append(task.task_id)
                    elif remaining < task.deadline_ms * 0.2:
                        # Less than 20% of deadline remaining — boost by 3
                        old = task.priority
                        task.priority = max(1, task.priority - 3)
                        if task.priority != old:
                            boosted.append(task.task_id)
                    elif remaining < task.deadline_ms * 0.5:
                        # Less than 50% — boost by 1
                        old = task.priority
                        task.priority = max(1, task.priority - 1)
                        if task.priority != old:
                            boosted.append(task.task_id)

            if boosted:
                heapq.heapify(self._task_queue)
                logger.info("Deadline pressure boosted %d tasks", len(boosted))

            return boosted

    def get_overdue_tasks(self) -> List[Dict[str, Any]]:
        """Returns tasks that have exceeded their deadlines."""
        with self._lock:
            now = time.perf_counter()
            overdue = []
            for task in self._task_queue:
                if task.deadline_ms is not None and task.status == "queued":
                    elapsed_ms = (now - task.submitted_at) * 1000.0
                    if elapsed_ms > task.deadline_ms:
                        overdue.append({
                            "task_id": task.task_id,
                            "priority": task.priority,
                            "deadline_ms": task.deadline_ms,
                            "elapsed_ms": round(elapsed_ms, 3),
                            "overdue_ms": round(elapsed_ms - task.deadline_ms, 3),
                        })
            return overdue

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task."""
        with self._lock:
            for task in self._task_queue:
                if task.task_id == task_id:
                    return task.to_dict()
            if task_id in self._running_tasks:
                return self._running_tasks[task_id].to_dict()
            for task in reversed(self._completed_tasks):
                if task.task_id == task_id:
                    return task.to_dict()
            for task in reversed(self._failed_tasks):
                if task.task_id == task_id:
                    return task.to_dict()
            return None

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a queued task."""
        with self._lock:
            for i, task in enumerate(self._task_queue):
                if task.task_id == task_id:
                    self._task_queue.pop(i)
                    heapq.heapify(self._task_queue)
                    task.status = "cancelled"
                    self._completed_tasks.append(task)
                    logger.info("Cancelled task '%s'", task_id)
                    return True
            if task_id in self._running_tasks:
                logger.warning("Cannot cancel running task '%s'", task_id)
                return False
        return False

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler and thread pool."""
        with self._lock:
            for task in self._task_queue:
                task.status = "shutdown"
            self._task_queue.clear()
        self._pool.shutdown(wait=wait)
        logger.info("SchedulerOptimizer shut down (wait=%s)", wait)

    def reset(self) -> None:
        """Reset all tracking data (does not shut down thread pool)."""
        with self._lock:
            self._task_queue.clear()
            self._running_tasks.clear()
            self._completed_tasks.clear()
            self._failed_tasks.clear()
            self._total_scheduled = 0
            self._total_preempted = 0
            logger.info("SchedulerOptimizer reset")


_scheduler_instance: Optional[SchedulerOptimizer] = None
_scheduler_lock = threading.RLock()


def get_scheduler_optimizer() -> SchedulerOptimizer:
    """Singleton accessor for SchedulerOptimizer."""
    global _scheduler_instance
    with _scheduler_lock:
        if _scheduler_instance is None:
            _scheduler_instance = SchedulerOptimizer()
        return _scheduler_instance
