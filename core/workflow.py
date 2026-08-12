"""WorkflowEngine — DAG-based scheduler with checkpoint/resume, error recovery, and resource awareness.

Borrows from: BehaviorTree (sequence/fallback/parallel nodes), Temporal (durable execution),
Prefect (task graphs), ROS2 (recovery behaviors).
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.core.workflow")


class NodeType(Enum):
    SEQUENCE = auto()   # Run all children in order
    FALLBACK = auto()   # Run children until one succeeds
    PARALLEL = auto()   # Run children concurrently
    ACTION = auto()     # Execute a single tool call
    CONDITION = auto()  # Check a condition before proceeding


class StepStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()
    TIMEOUT = auto()


@dataclass
class WorkflowStep:
    id: str = ""
    tool: str = ""
    params: dict = field(default_factory=dict)
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    node_type: NodeType = NodeType.ACTION
    children: list['WorkflowStep'] = field(default_factory=list)
    max_retries: int = 2
    timeout: float = 30.0
    critical: bool = False
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: float = 0.0
    completed_at: float = 0.0
    retry_count: int = 0

    def __post_init__(self):
        if not self.id and self.tool:
            self.id = f"step_{uuid.uuid4().hex[:6]}"
        elif not self.id:
            self.id = f"node_{uuid.uuid4().hex[:6]}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d['node_type'] = self.node_type.name
        d['status'] = self.status.name
        return d


@dataclass
class Workflow:
    id: str = ""
    goal: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    status: str = "pending"
    created_at: float = 0.0
    updated_at: float = 0.0
    checkpoint_path: Path | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = f"wf_{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = time.time()
            self.updated_at = self.created_at


# ── Scheduler ─────────────────────────────────

class Scheduler:
    """Executes workflow steps respecting dependencies, parallelism, and resource pressure."""

    def __init__(self, tool_executor: Callable | None = None,
                 resource_manager=None, task_manager=None):
        self._tool_executor = tool_executor
        self._resource_manager = resource_manager
        self._task_manager = task_manager

    def _topological_sort(self, steps: list[WorkflowStep]) -> list[WorkflowStep]:
        step_map = {s.id: s for s in steps}
        visited: set[str] = set()
        result: list[WorkflowStep] = []

        def _visit(sid: str):
            if sid in visited:
                return
            visited.add(sid)
            step = step_map.get(sid)
            if step:
                for dep_id in step.depends_on:
                    _visit(dep_id)
                result.append(step)

        for s in steps:
            _visit(s.id)
        return result

    def _get_ready_steps(self, steps: list[WorkflowStep]) -> list[WorkflowStep]:
        status_map = {s.id: s.status for s in steps}
        ready = []
        for s in steps:
            if s.status != StepStatus.PENDING:
                continue
            deps_met = all(
                status_map.get(dep) == StepStatus.COMPLETED
                for dep in s.depends_on
            )
            if deps_met:
                ready.append(s)
        return ready

    async def execute_workflow(self, workflow: Workflow,
                                execute_fn: Callable) -> dict:
        logger.info("Executing workflow %s: %s", workflow.id, workflow.goal[:60])
        sorted_steps = self._topological_sort(workflow.steps)

        if self._task_manager:
            task = self._task_manager.create(
                name=f"workflow.{workflow.id}",
                metadata={"goal": workflow.goal, "step_count": len(sorted_steps)},
            )

        overall_result = {
            "workflow_id": workflow.id,
            "goal": workflow.goal,
            "status": "completed",
            "steps": [],
            "error": None,
        }

        while True:
            ready = self._get_ready_steps(sorted_steps)
            if not ready:
                break

            # Check resource pressure before executing
            if self._resource_manager and self._resource_manager.should_throttle:
                logger.info("Resource pressure high, delaying workflow %s", workflow.id)
                await asyncio.sleep(2.0)
                continue

            # Execute ready steps (parallel if independent)
            tasks = []
            for step in ready:
                tasks.append(self._execute_step(step, execute_fn))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, result in zip(ready, results):
                if isinstance(result, Exception):
                    step.status = StepStatus.FAILED
                    step.error = str(result)
                    logger.error("Step %s failed: %s", step.id, result)

                    if step.critical:
                        overall_result["status"] = "failed"
                        overall_result["error"] = f"Critical step {step.id} failed: {step.error}"
                        if self._task_manager:
                            self._task_manager.update(
                                task.id, error=overall_result["error"]
                            )
                        return overall_result
                else:
                    step.status = StepStatus.COMPLETED
                    step.result = result
                    step.completed_at = time.time()

            overall_result["steps"] = [
                {"id": s.id, "tool": s.tool, "status": s.status.name, "error": s.error}
                for s in sorted_steps
            ]

            # Checkpoint after each batch
            self._checkpoint(workflow)

        if self._task_manager:
            self._task_manager.update(task.id, status=task.status.COMPLETED)

        workflow.status = "completed"
        logger.info("Workflow %s completed", workflow.id)
        return overall_result

    async def _execute_step(self, step: WorkflowStep, execute_fn: Callable) -> Any:
        step.status = StepStatus.RUNNING
        step.started_at = time.time()
        logger.info("Step %s: %s (%s)", step.id, step.tool, step.description[:50])

        if self._tool_executor:
            try:
                result = await asyncio.wait_for(
                    self._tool_executor(step.tool, step.params),
                    timeout=step.timeout,
                )
                return result
            except TimeoutError:
                step.error = "Timeout"
                step.retry_count += 1
                if step.retry_count <= step.max_retries:
                    wait = min(10, 2 ** step.retry_count)
                    logger.warning("Step %s timeout, retry %d/%d in %ds",
                                   step.id, step.retry_count, step.max_retries, wait)
                    await asyncio.sleep(wait)
                    return await self._execute_step(step, execute_fn)
                raise
            except Exception as e:
                step.retry_count += 1
                if step.retry_count <= step.max_retries:
                    wait = min(10, 2 ** step.retry_count)
                    logger.warning("Step %s failed, retry %d/%d in %ds: %s",
                                   step.id, step.retry_count, step.max_retries, wait, e)
                    await asyncio.sleep(wait)
                    return await self._execute_step(step, execute_fn)
                raise
        else:
            if callable(execute_fn):
                return await execute_fn(step.tool, step.params)
            return None

    def _checkpoint(self, workflow: Workflow):
        if not workflow.checkpoint_path:
            return
        try:
            data = {
                "id": workflow.id,
                "goal": workflow.goal,
                "status": workflow.status,
                "steps": [s.to_dict() for s in workflow.steps],
                "updated_at": time.time(),
            }
            workflow.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            workflow.checkpoint_path.write_text(
                json.dumps(data, indent=2, default=str), encoding='utf-8'
            )
        except Exception as e:
            logger.warning("Checkpoint failed for %s: %s", workflow.id, e)


# ── WorkflowEngine ────────────────────────────

class WorkflowEngine:
    """Creates and manages workflows with durable execution, checkpoint/resume, and error recovery."""

    def __init__(self, tool_executor: Callable | None = None,
                 scheduler: Scheduler | None = None,
                 resource_manager=None, task_manager=None,
                 checkpoint_dir: Path | None = None):
        self._scheduler = scheduler or Scheduler(
            tool_executor=tool_executor,
            resource_manager=resource_manager,
            task_manager=task_manager,
        )
        self._resource_manager = resource_manager
        self._task_manager = task_manager
        self._checkpoint_dir = checkpoint_dir or Path.home() / ".jarvis" / "workflows"
        self._workflows: dict[str, Workflow] = {}
        self._lock = threading.Lock()

    def create_workflow(self, goal: str,
                         steps: list[dict] | None = None) -> Workflow:
        wf = Workflow(
            goal=goal,
            checkpoint_path=self._checkpoint_dir / f"{uuid.uuid4().hex[:8]}.json",
        )
        if steps:
            for s in steps:
                step = WorkflowStep(
                    tool=s.get("tool", ""),
                    params=s.get("params", {}),
                    description=s.get("description", ""),
                    depends_on=s.get("depends_on", []),
                    critical=s.get("critical", False),
                    max_retries=s.get("max_retries", 2),
                    timeout=s.get("timeout", 30.0),
                )
                wf.steps.append(step)

        with self._lock:
            self._workflows[wf.id] = wf
        logger.info("Created workflow %s: %s", wf.id, goal[:60])
        self._checkpoint(wf)
        return wf

    async def execute(self, workflow_id: str,
                       execute_fn: Callable | None = None) -> dict:
        wf = self._workflows.get(workflow_id)
        if not wf:
            raise KeyError(f"Workflow {workflow_id} not found")
        wf.status = "running"
        result = await self._scheduler.execute_workflow(wf, execute_fn or self._default_executor)
        wf.status = result["status"]
        return result

    async def _default_executor(self, tool: str, params: dict) -> str:
        logger.info("Executing tool %s with params: %s", tool, params)
        return f"Executed {tool}"

    def resume(self, workflow_id: str) -> Workflow | None:
        """Resume a workflow from its checkpoint."""
        wf = self._workflows.get(workflow_id)
        if wf:
            return wf
        # Try loading from checkpoint
        for cp in self._checkpoint_dir.glob("*.json"):
            try:
                data = json.loads(cp.read_text(encoding='utf-8'))
                if data.get("id") == workflow_id:
                    wf = self._from_checkpoint(data)
                    wf.checkpoint_path = cp
                    with self._lock:
                        self._workflows[wf.id] = wf
                    return wf
            except Exception:
                continue
        return None

    def _from_checkpoint(self, data: dict) -> Workflow:
        steps = []
        for s in data.get("steps", []):
            step = WorkflowStep(
                id=s.get("id", ""),
                tool=s.get("tool", ""),
                params=s.get("params", {}),
                description=s.get("description", ""),
                depends_on=s.get("depends_on", []),
                critical=s.get("critical", False),
                max_retries=s.get("max_retries", 2),
                timeout=s.get("timeout", 30.0),
                status=StepStatus[s.get("status", "PENDING")],
                error=s.get("error"),
                result=s.get("result"),
                retry_count=s.get("retry_count", 0),
            )
            steps.append(step)
        return Workflow(
            id=data.get("id", ""),
            goal=data.get("goal", ""),
            steps=steps,
            status=data.get("status", "pending"),
            created_at=data.get("updated_at", 0),
        )

    def cancel(self, workflow_id: str) -> bool:
        wf = self._workflows.get(workflow_id)
        if not wf:
            return False
        wf.status = "cancelled"
        logger.info("Cancelled workflow %s", workflow_id)
        return True

    def get_status(self, workflow_id: str) -> dict | None:
        wf = self._workflows.get(workflow_id)
        if not wf:
            return None
        return {
            "id": wf.id,
            "goal": wf.goal[:80],
            "status": wf.status,
            "steps": [
                {"id": s.id, "tool": s.tool, "status": s.status.name, "error": s.error}
                for s in wf.steps
            ],
            "created_at": wf.created_at,
            "step_count": len(wf.steps),
            "completed_steps": sum(1 for s in wf.steps if s.status == StepStatus.COMPLETED),
            "failed_steps": sum(1 for s in wf.steps if s.status == StepStatus.FAILED),
        }

    def _checkpoint(self, workflow: Workflow):
        self._scheduler._checkpoint(workflow)

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "total": len(self._workflows),
                "running": sum(1 for w in self._workflows.values() if w.status == "running"),
                "completed": sum(1 for w in self._workflows.values() if w.status == "completed"),
                "failed": sum(1 for w in self._workflows.values() if w.status == "failed"),
                "cancelled": sum(1 for w in self._workflows.values() if w.status == "cancelled"),
            }
