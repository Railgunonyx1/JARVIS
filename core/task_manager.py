"""Task Manager — tracks active, cancelled, and completed tasks.

Separate from Scheduler. Manages task lifecycle and progress reporting.
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger("jarvis.task_manager")


class TaskStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
    TIMEOUT = auto()


@dataclass
class Task:
    name: str
    id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    message: str = ""
    created_at: float = 0.0
    completed_at: float | None = None
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = f"task_{uuid.uuid4().hex[:8]}"
        if self.created_at == 0.0:
            self.created_at = time.time()


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._history: list[Task] = []
        self._max_history = 200

    def create(self, name: str, metadata: dict[str, Any] | None = None) -> Task:
        task = Task(name=name, metadata=metadata or {})
        self._tasks[task.id] = task
        return task

    def update(self, task_id: str, status: TaskStatus | None = None,
               progress: float | None = None, message: str | None = None,
               result: Any = None, error: str | None = None) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        if status:
            task.status = status
        if progress is not None:
            task.progress = min(1.0, max(0.0, progress))
        if message:
            task.message = message
        if result is not None:
            task.result = result
        if error:
            task.error = error
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED,
                      TaskStatus.CANCELLED, TaskStatus.TIMEOUT):
            task.completed_at = time.time()
            self._archive(task)
        return True

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED,
                                       TaskStatus.FAILED):
            return False
        task.status = TaskStatus.CANCELLED
        task.completed_at = time.time()
        self._archive(task)
        return True

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def get_active(self) -> list[Task]:
        return [t for t in self._tasks.values()
                if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)]

    def get_by_status(self, status: TaskStatus) -> list[Task]:
        return [t for t in self._tasks.values() if t.status == status]

    def get_history(self, limit: int = 50) -> list[Task]:
        return sorted(self._history, key=lambda t: t.created_at, reverse=True)[:limit]

    def _archive(self, task: Task):
        self._tasks.pop(task.id, None)
        self._history.append(task)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_stats(self) -> dict[str, int]:
        return {
            "active": len(self.get_active()),
            "pending": len(self.get_by_status(TaskStatus.PENDING)),
            "running": len(self.get_by_status(TaskStatus.RUNNING)),
            "completed": len(self.get_by_status(TaskStatus.COMPLETED)),
            "failed": len(self.get_by_status(TaskStatus.FAILED)),
            "cancelled": len(self.get_by_status(TaskStatus.CANCELLED)),
            "history": len(self._history),
        }
