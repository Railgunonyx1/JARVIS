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

from workflows.goal_decomposer import GoalDecomposer, GoalType

logger = logging.getLogger("jarvis.workflows.engine")


class WorkflowStatus(Enum):
    PENDING    = "pending"
    RUNNING    = "running"
    PAUSED     = "paused"
    COMPLETED  = "completed"
    FAILED     = "failed"
    CANCELLED  = "cancelled"


@dataclass
class Goal:
    id:          str           = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str           = ""
    priority:    int           = 2
    status:      WorkflowStatus = WorkflowStatus.PENDING
    sub_goals:   list          = field(default_factory=list)
    deadline:    float         = 0.0
    created_at:  float         = field(default_factory=time.time)
    updated_at:  float         = field(default_factory=time.time)
    metadata:    dict          = field(default_factory=dict)


@dataclass
class WorkflowStep:
    id:           str          = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:         str          = ""
    action:       str          = ""
    params:       dict         = field(default_factory=dict)
    status:       WorkflowStatus = WorkflowStatus.PENDING
    dependencies: list         = field(default_factory=list)
    timeout:      float        = 60.0
    result:       Any          = None
    error:        str          = ""
    attempts:     int          = 0
    max_attempts: int          = 3
    created_at:   float        = field(default_factory=time.time)


DEFAULT_DB = str(Path.home() / ".jarvis" / "workflows.db")


class WorkflowEngine:

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or DEFAULT_DB
        self._lock = threading.Lock()
        self._active_workflows: dict[str, dict] = {}
        self._pause_events: dict[str, threading.Event] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._step_callbacks: dict[str, Callable] = {}
        self._decomposer = GoalDecomposer(db_path)
        self._init_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id          TEXT PRIMARY KEY,
                    goal_id     TEXT,
                    goal_text   TEXT NOT NULL,
                    status      TEXT DEFAULT 'pending',
                    priority    INTEGER DEFAULT 2,
                    context     TEXT DEFAULT '{}',
                    results     TEXT DEFAULT '{}',
                    created_at  REAL NOT NULL,
                    updated_at  REAL NOT NULL,
                    completed_at REAL DEFAULT 0,
                    deadline    REAL DEFAULT 0,
                    metadata    TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_steps (
                    id            TEXT PRIMARY KEY,
                    workflow_id   TEXT NOT NULL,
                    name          TEXT NOT NULL,
                    action        TEXT NOT NULL,
                    params        TEXT DEFAULT '{}',
                    status        TEXT DEFAULT 'pending',
                    dependencies  TEXT DEFAULT '[]',
                    timeout       REAL DEFAULT 60,
                    result        TEXT DEFAULT '',
                    error         TEXT DEFAULT '',
                    attempts      INTEGER DEFAULT 0,
                    max_attempts  INTEGER DEFAULT 3,
                    created_at    REAL NOT NULL,
                    completed_at  REAL DEFAULT 0,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_wf_status ON workflows(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_wf_steps ON workflow_steps(workflow_id)
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to init workflow DB: %s", e)

    def decompose_goal(self, goal_text: str) -> Goal:
        goal_type, sub_goals = self._decomposer.decompose(goal_text)

        goal = Goal(
            description=goal_text,
            priority=1 if goal_type in (GoalType.MULTISTEP, GoalType.UNKNOWN) else 2,
            sub_goals=[sg.__dict__ for sg in sub_goals],
            metadata={"goal_type": goal_type.value},
        )

        with self._lock:
            self._persist_goal(goal)

        logger.info("Decomposed goal '%s' -> %d sub-goals [%s]",
                     goal_text[:60], len(sub_goals), goal_type.value)
        return goal

    def create_workflow(self, goal: Goal) -> list[WorkflowStep]:
        steps: list[WorkflowStep] = []

        for sg in goal.sub_goals:
            if isinstance(sg, dict):
                step = WorkflowStep(
                    name=sg.get("name", "step"),
                    action=sg.get("action", "generated_code"),
                    params=sg.get("params", {}),
                    dependencies=sg.get("depends_on", []),
                    priority=sg.get("priority", 2),
                    timeout=sg.get("timeout", 60.0),
                )
            else:
                step = WorkflowStep(
                    name=getattr(sg, "name", "step"),
                    action=getattr(sg, "action", "generated_code"),
                    params=getattr(sg, "params", {}),
                    dependencies=getattr(sg, "depends_on", []),
                    priority=getattr(sg, "priority", 2),
                    timeout=getattr(sg, "timeout", 60.0),
                )
            steps.append(step)

        steps = self._resolve_dependency_order(steps)

        wf_id = goal.id
        with self._lock:
            self._persist_workflow(wf_id, goal, steps)

        return steps

    def execute_workflow(self, workflow: list[WorkflowStep], context: dict | None = None,
                         goal_id: str | None = None, callback: Callable | None = None) -> dict:
        wf_id = goal_id or str(uuid.uuid4())[:8]
        context = context or {}

        with self._lock:
            self._active_workflows[wf_id] = {
                "steps": workflow,
                "context": context,
                "start_time": time.time(),
                "status": WorkflowStatus.RUNNING,
            }
            self._pause_events[wf_id] = threading.Event()
            self._pause_events[wf_id].set()
            self._cancel_events[wf_id] = threading.Event()
            if callback:
                self._step_callbacks[wf_id] = callback

        results: dict[str, Any] = {}
        completed_ids: set[str] = set()
        failed = False
        failed_step: WorkflowStep | None = None

        try:
            for step in workflow:
                if self._cancel_events.get(wf_id, threading.Event()).is_set():
                    self._update_workflow_status(wf_id, WorkflowStatus.CANCELLED)
                    return {"status": "cancelled", "results": results}

                pause_event = self._pause_events.get(wf_id)
                if pause_event:
                    pause_event.wait()

                deps_met = all(d in completed_ids for d in step.dependencies)
                if not deps_met:
                    missing = [d for d in step.dependencies if d not in completed_ids]
                    step.status = WorkflowStatus.FAILED
                    step.error = f"Dependencies not met: {missing}"
                    results[step.id] = {"error": step.error}
                    failed = True
                    failed_step = step
                    break

                step.status = WorkflowStatus.RUNNING
                self._update_step_status(step.id, WorkflowStatus.RUNNING)

                cb = self._step_callbacks.get(wf_id)
                if cb:
                    try:
                        cb("step_start", step.id, step.name)
                    except Exception:
                        pass

                ok = self.monitor_step(step, step.timeout, context, results)

                if ok:
                    step.status = WorkflowStatus.COMPLETED
                    completed_ids.add(step.id)
                    results[step.id] = step.result
                    self._update_step_status(step.id, WorkflowStatus.COMPLETED, result=step.result)
                else:
                    recovery = self.recover_from_failure(step, step.error)
                    if recovery and recovery.action != step.action:
                        step = recovery
                        ok = self.monitor_step(step, step.timeout, context, results)
                        if ok:
                            step.status = WorkflowStatus.COMPLETED
                            completed_ids.add(step.id)
                            results[step.id] = step.result
                            self._update_step_status(step.id, WorkflowStatus.COMPLETED, result=step.result)
                        else:
                            failed = True
                            failed_step = step
                            break
                    else:
                        failed = True
                        failed_step = step
                        break

                if cb:
                    try:
                        cb("step_complete", step.id, step.name)
                    except Exception:
                        pass

            status = WorkflowStatus.COMPLETED if not failed else WorkflowStatus.FAILED
            self._update_workflow_status(wf_id, status, results=results)

            return {
                "status": status.value,
                "workflow_id": wf_id,
                "results": results,
                "total_steps": len(workflow),
                "completed": len(completed_ids),
                "failed_step": failed_step.id if failed_step else None,
                "elapsed": time.time() - self._active_workflows.get(wf_id, {}).get("start_time", time.time()),
            }

        except Exception as e:
            logger.error("Workflow execution error: %s", e)
            self._update_workflow_status(wf_id, WorkflowStatus.FAILED)
            return {"status": "failed", "error": str(e), "results": results}
        finally:
            with self._lock:
                self._active_workflows.pop(wf_id, None)
                self._pause_events.pop(wf_id, None)
                self._cancel_events.pop(wf_id, None)
                self._step_callbacks.pop(wf_id, None)

    def monitor_step(self, step: WorkflowStep, timeout: float,
                     context: dict | None = None, results: dict | None = None) -> bool:
        start = time.time()
        step.attempts += 1

        try:
            action_fn = self._resolve_action(step.action)
            if not action_fn:
                step.error = f"Unknown action: {step.action}"
                return False

            merged_params = {**(context or {}), **step.params}
            merged_params["_step_id"] = step.id
            merged_params["_results"] = results or {}

            result = action_fn(step.action, merged_params)

            if time.time() - start > timeout:
                step.error = f"Step timed out after {timeout}s"
                return False

            step.result = result
            return True

        except Exception as e:
            step.error = str(e)[:500]
            logger.warning("Step '%s' failed: %s", step.name, e)
            return False

    def recover_from_failure(self, step: WorkflowStep, error: str) -> WorkflowStep | None:
        if step.attempts >= step.max_attempts:
            logger.warning("Max attempts reached for step '%s', no recovery", step.name)
            return None

        if "timeout" in error.lower():
            return WorkflowStep(
                id=step.id,
                name=step.name + "_retry",
                action=step.action,
                params={**step.params, "_retry": True},
                dependencies=step.dependencies,
                timeout=step.timeout * 1.5,
                max_attempts=step.max_attempts,
            )

        if "not found" in error.lower() or "missing" in error.lower():
            return WorkflowStep(
                id=step.id,
                name=step.name + "_fallback",
                action="generated_code",
                params={"description": f"Retry with fallback approach for: {step.name}. Original error: {error[:200]}"},
                dependencies=step.dependencies,
                timeout=step.timeout,
                max_attempts=step.max_attempts,
            )

        if "permission" in error.lower() or "denied" in error.lower():
            logger.warning("Permission error on step '%s', cannot auto-recover", step.name)
            return None

        if step.attempts < step.max_attempts:
            return WorkflowStep(
                id=step.id,
                name=step.name + "_retry",
                action=step.action,
                params={**step.params},
                dependencies=step.dependencies,
                timeout=step.timeout,
                max_attempts=step.max_attempts,
            )

        return None

    def pause_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            wf = self._active_workflows.get(workflow_id)
            if not wf or wf["status"] != WorkflowStatus.RUNNING:
                return False
            wf["status"] = WorkflowStatus.PAUSED
            pause_evt = self._pause_events.get(workflow_id)
            if pause_evt:
                pause_evt.clear()
            self._update_workflow_status(workflow_id, WorkflowStatus.PAUSED)
            logger.info("Workflow paused: %s", workflow_id)
            return True

    def resume_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            wf = self._active_workflows.get(workflow_id)
            if not wf or wf["status"] != WorkflowStatus.PAUSED:
                return False
            wf["status"] = WorkflowStatus.RUNNING
            pause_evt = self._pause_events.get(workflow_id)
            if pause_evt:
                pause_evt.set()
            self._update_workflow_status(workflow_id, WorkflowStatus.RUNNING)
            logger.info("Workflow resumed: %s", workflow_id)
            return True

    def cancel_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            wf = self._active_workflows.get(workflow_id)
            if not wf:
                return False
            cancel_evt = self._cancel_events.get(workflow_id)
            if cancel_evt:
                cancel_evt.set()
            pause_evt = self._pause_events.get(workflow_id)
            if pause_evt:
                pause_evt.set()
            wf["status"] = WorkflowStatus.CANCELLED
            self._update_workflow_status(workflow_id, WorkflowStatus.CANCELLED)
            logger.info("Workflow cancelled: %s", workflow_id)
            return True

    def get_workflow_status(self, workflow_id: str) -> dict:
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
            if not row:
                conn.close()
                return {"error": "Workflow not found"}

            wf = dict(row)
            wf["context"] = json.loads(wf.get("context", "{}"))
            wf["results"] = json.loads(wf.get("results", "{}"))
            wf["metadata"] = json.loads(wf.get("metadata", "{}"))

            steps = conn.execute(
                "SELECT * FROM workflow_steps WHERE workflow_id = ? ORDER BY created_at",
                (workflow_id,)
            ).fetchall()
            wf["steps"] = [dict(s) for s in steps]

            active = self._active_workflows.get(workflow_id)
            if active:
                wf["is_running"] = True
                wf["elapsed"] = time.time() - active.get("start_time", time.time())
            else:
                wf["is_running"] = False

            conn.close()
            return wf

        except Exception as e:
            logger.error("Failed to get workflow status: %s", e)
            return {"error": str(e)}

    def list_workflows(self, status: str | None = None, limit: int = 50) -> list[dict]:
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            conn.row_factory = sqlite3.Row

            if status:
                rows = conn.execute(
                    "SELECT * FROM workflows WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflows ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()

            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error("Failed to list workflows: %s", e)
            return []

    def _resolve_dependency_order(self, steps: list[WorkflowStep]) -> list[WorkflowStep]:
        if not steps:
            return []

        step_map = {s.id: s for s in steps}
        in_degree = {s.id: 0 for s in steps}

        for s in steps:
            for dep in s.dependencies:
                if dep in in_degree:
                    in_degree[s.id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        result: list[WorkflowStep] = []

        while queue:
            queue.sort(key=lambda sid: step_map[sid].priority if hasattr(step_map[sid], "priority") else 2)
            node = queue.pop(0)
            result.append(step_map[node])

            for s in steps:
                if node in s.dependencies:
                    in_degree[s.id] -= 1
                    if in_degree[s.id] == 0:
                        queue.append(s.id)

        if len(result) != len(steps):
            seen = {s.id for s in result}
            for s in steps:
                if s.id not in seen:
                    result.append(s)

        return result

    def _resolve_action(self, action: str) -> Callable | None:
        action_map = {
            "web_search":     self._action_web_search,
            "file_controller": self._action_file_controller,
            "generated_code":  self._action_generated_code,
            "open_app":        self._action_open_app,
            "browser":         self._action_browser,
            "system":          self._action_system,
            "process_manager": self._action_process_manager,
            "shell":           self._action_shell,
            "screen_analyzer": self._action_screen_analyzer,
            "computer_control": self._action_computer_control,
        }
        return action_map.get(action)

    def _action_web_search(self, action: str, params: dict) -> str:
        from actions.web_search import web_search
        return web_search(parameters=params, player=None) or "Done."

    def _action_file_controller(self, action: str, params: dict) -> str:
        from actions.file_manager import file_action
        return file_action(params.get("action", "list"), params) or "Done."

    def _action_generated_code(self, action: str, params: dict) -> str:
        from core.executor import _run_generated_code
        return _run_generated_code(params.get("description", ""))

    def _action_open_app(self, action: str, params: dict) -> str:
        from actions.open_app import open_app
        return open_app(parameters=params, player=None) or "Done."

    def _action_browser(self, action: str, params: dict) -> str:
        from actions.browser_control import browser_action
        return browser_action(params) or "Done."

    def _action_system(self, action: str, params: dict) -> str:
        action_type = params.get("action", "info")
        if action_type == "info":
            from actions.disk_manager import disk_action
            return disk_action("info", params) or "Done."
        from actions.process_manager import process_action
        return process_action("list", params) or "Done."

    def _action_process_manager(self, action: str, params: dict) -> str:
        from actions.process_manager import process_action
        return process_action(params.get("action", "list"), params) or "Done."

    def _action_shell(self, action: str, params: dict) -> str:
        from actions.shell_exec import shell_action
        return shell_action(params.get("action", "run"), params) or "Done."

    def _action_screen_analyzer(self, action: str, params: dict) -> str:
        from actions.screen_analyzer import screen_analyze
        return screen_analyze(params) or "Done."

    def _action_computer_control(self, action: str, params: dict) -> str:
        from actions.input_control import input_action
        return input_action(params.get("action", ""), params) or "Done."

    def _persist_goal(self, goal: Goal) -> None:
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                INSERT OR REPLACE INTO goals
                (id, description, goal_type, priority, status, deadline, created_at, updated_at, raw_text, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                goal.id, goal.description, goal.metadata.get("goal_type", "unknown"),
                goal.priority, goal.status.value, goal.deadline,
                goal.created_at, goal.updated_at, goal.description,
                json.dumps(goal.metadata),
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to persist goal: %s", e)

    def _persist_workflow(self, wf_id: str, goal: Goal, steps: list[WorkflowStep]) -> None:
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            now = time.time()
            conn.execute("""
                INSERT OR REPLACE INTO workflows
                (id, goal_id, goal_text, status, priority, context, results, created_at, updated_at, deadline, metadata)
                VALUES (?, ?, ?, ?, ?, '{}', '{}', ?, ?, ?, '{}')
            """, (wf_id, goal.id, goal.description, WorkflowStatus.PENDING.value,
                  goal.priority, now, now, goal.deadline))

            for step in steps:
                conn.execute("""
                    INSERT OR REPLACE INTO workflow_steps
                    (id, workflow_id, name, action, params, status,
                     dependencies, timeout, result, error, attempts,
                     max_attempts, created_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', 0, ?, ?, 0)
                """, (
                    step.id, wf_id, step.name, step.action, json.dumps(step.params),
                    step.status.value, json.dumps(step.dependencies), step.timeout,
                    step.max_attempts, now,
                ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to persist workflow: %s", e)

    def _update_workflow_status(self, wf_id: str, status: WorkflowStatus,
                                results: dict | None = None) -> None:
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            now = time.time()
            if results:
                conn.execute(
                    "UPDATE workflows SET status = ?, updated_at = ?, completed_at = ?, results = ? WHERE id = ?",
                    (status.value, now, now if status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED) else 0,
                     json.dumps(results), wf_id)
                )
            else:
                conn.execute(
                    "UPDATE workflows SET status = ?, updated_at = ? WHERE id = ?",
                    (status.value, now, wf_id)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to update workflow status: %s", e)

    def _update_step_status(self, step_id: str, status: WorkflowStatus,
                            result: Any = None, error: str = "") -> None:
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            now = time.time()
            conn.execute(
                "UPDATE workflow_steps SET status = ?, result = ?, error = ?, completed_at = ? WHERE id = ?",
                (status.value, str(result) if result else "", error,
                 now if status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED) else 0, step_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to update step status: %s", e)
