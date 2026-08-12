"""Durable Task Executor — persistent async tasks with retry, timeout, recovery.

Extends WorkflowEngine concepts for individual durable tasks.
Tasks survive restarts via SQLite-backed checkpoint.
"""

import asyncio
import json
import logging
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.core.durable_task")


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DurableTask:
    id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str = ""
    retries: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    timeout: float = 30.0
    checkpoint_data: dict = field(default_factory=dict)


class DurableExecutor:
    """Executes async tasks with durability — survives crashes via SQLite.

    Usage:
        executor = DurableExecutor()
        task_id = await executor.submit("process_file", my_coro, max_retries=5)
        result = await executor.wait(task_id)
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or Path.home() / ".jarvis" / "durable_tasks.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                error TEXT,
                retries INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                timeout REAL DEFAULT 30.0,
                checkpoint_data TEXT DEFAULT '{}'
            )
        """)
        self._conn.commit()
        self._lock = threading.Lock()
        self._pending: dict[str, asyncio.Future] = {}

    async def submit(self, name: str, coro_factory: Callable,
                     max_retries: int = 3, timeout: float = 30.0) -> str:
        """Submit a durable task. coro_factory is called to create the coroutine."""
        task_id = str(uuid.uuid4())[:16]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO tasks (id, name, status, created_at, updated_at, max_retries, timeout) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task_id, name, TaskStatus.PENDING.value, now, now, max_retries, timeout),
            )
            self._conn.commit()
            future = asyncio.get_running_loop().create_future()
            self._pending[task_id] = future

        asyncio.create_task(self._execute(task_id, coro_factory))
        logger.info("Durable task submitted: %s (%s)", task_id, name)
        return task_id

    async def _execute(self, task_id: str, coro_factory: Callable):
        task = await self._load(task_id)
        if not task:
            return

        retries = 0
        while retries <= task.max_retries:
            task.status = TaskStatus.RUNNING
            task.retries = retries
            task.updated_at = time.time()
            await self._save(task)

            try:
                maybe_awaitable = coro_factory()
                if asyncio.iscoroutine(maybe_awaitable) or asyncio.isfuture(maybe_awaitable) or hasattr(maybe_awaitable, '__await__'):
                    result = await asyncio.wait_for(maybe_awaitable, timeout=task.timeout)
                else:
                    result = maybe_awaitable
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.updated_at = time.time()
                await self._save(task)
                future = self._pending.pop(task_id, None)
                if future and not future.done():
                    future.set_result(result)
                logger.info("Durable task %s completed", task_id)
                return
            except TimeoutError:
                retries += 1
                logger.warning("Task %s timeout (retry %d/%d)", task_id, retries, task.max_retries)
            except Exception as e:
                retries += 1
                logger.warning("Task %s failed: %s (retry %d/%d)", task_id, e, retries, task.max_retries)
                task.error = str(e)

            if retries > task.max_retries:
                task.status = TaskStatus.FAILED
                task.updated_at = time.time()
                await self._save(task)
                future = self._pending.pop(task_id, None)
                if future and not future.done():
                    future.set_exception(RuntimeError(f"Task {task_id} failed: {task.error}"))
                logger.error("Task %s failed after %d retries", task_id, retries)
                return

            await asyncio.sleep(2 ** retries)

    async def wait(self, task_id: str, timeout: float = None) -> Any:
        future = self._pending.get(task_id)
        if not future:
            task = await self._load(task_id)
            if task:
                if task.status == TaskStatus.COMPLETED:
                    return task.result
                elif task.status == TaskStatus.FAILED:
                    raise RuntimeError(f"Task failed: {task.error}")
            raise KeyError(f"Unknown task: {task_id}")
        return await asyncio.wait_for(future, timeout=timeout)

    def get_status(self, task_id: str) -> dict | None:
        task = self._load_sync(task_id)
        if not task:
            return None
        return {
            "id": task.id,
            "name": task.name,
            "status": task.status.value,
            "retries": task.retries,
            "max_retries": task.max_retries,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "error": task.error,
        }

    def get_all(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, status, retries, max_retries, created_at, updated_at, error "
            "FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    async def _load(self, task_id: str) -> DurableTask | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return None
        return DurableTask(
            id=row["id"],
            name=row["name"],
            status=TaskStatus(row["status"]),
            result=row["result"],
            error=row["error"] or "",
            retries=row["retries"],
            max_retries=row["max_retries"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            timeout=row["timeout"],
            checkpoint_data=json.loads(row["checkpoint_data"] or "{}"),
        )

    def _load_sync(self, task_id: str) -> DurableTask | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return None
        return DurableTask(
            id=row["id"],
            name=row["name"],
            status=TaskStatus(row["status"]),
            result=row["result"],
            error=row["error"] or "",
            retries=row["retries"],
            max_retries=row["max_retries"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            timeout=row["timeout"],
            checkpoint_data=json.loads(row["checkpoint_data"] or "{}"),
        )

    async def _save(self, task: DurableTask):
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET status=?, result=?, error=?, retries=?, "
                "updated_at=?, checkpoint_data=? WHERE id=?",
                (task.status.value,
                 json.dumps(task.result) if task.result is not None else None,
                 task.error,
                 task.retries,
                 task.updated_at,
                 json.dumps(task.checkpoint_data),
                 task.id),
            )
            self._conn.commit()

    def recover_pending(self) -> list[dict]:
        """On startup, find tasks that were running and mark them for recovery."""
        rows = self._conn.execute(
            "SELECT id, name, status FROM tasks WHERE status IN ('pending', 'running')"
        ).fetchall()
        for r in rows:
            self._conn.execute(
                "UPDATE tasks SET status=?, error=? WHERE id=?",
                (TaskStatus.FAILED.value, "crashed before completion", r["id"]),
            )
        self._conn.commit()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()
