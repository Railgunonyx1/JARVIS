"""Hierarchical Planning — Decompose large tasks into executable trees.

Build Application
├── UI
├── Backend
├── Database
├── Testing
└── Deployment

Workers execute branches independently.
"""
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger("reasoning_system.hierarchical_planner")


class TaskState(Enum):
    PENDING = auto()
    PLANNING = auto()
    READY = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    BLOCKED = auto()
    SKIPPED = auto()


@dataclass
class PlanNode:
    """A node in the hierarchical plan tree."""
    id: str
    description: str
    state: TaskState = TaskState.PENDING
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    depth: int = 0
    priority: int = 5
    estimated_ms: float = 0.0
    actual_ms: float = 0.0
    result: Any = None
    error: str | None = None
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "state": self.state.name,
            "depth": self.depth,
            "children": len(self.children_ids),
            "priority": self.priority,
            "estimated_ms": self.estimated_ms,
            "actual_ms": self.actual_ms,
        }


class HierarchicalPlanner:
    """Decompose complex goals into hierarchical task trees.

    Supports:
    - Automatic decomposition based on goal description
    - Parallel execution of independent branches
    - Dependency tracking between tasks
    - Progress reporting
    """

    def __init__(self):
        self._nodes: dict[str, PlanNode] = {}
        self._root_id: str | None = None
        self._lock = threading.Lock()
        self._execution_log: list[dict[str, Any]] = []
        self._plan_counter = 0

    def create_plan(self, goal: str, subtasks: list[str] = None) -> str:
        """Create a new hierarchical plan from a goal."""
        self._plan_counter += 1
        root_id = f"plan_{self._plan_counter}_root"

        root = PlanNode(
            id=root_id,
            description=goal,
            state=TaskState.READY,
            depth=0,
        )
        self._nodes[root_id] = root
        self._root_id = root_id

        if subtasks:
            for i, task_desc in enumerate(subtasks):
                child_id = f"{root_id}_c{i}"
                child = PlanNode(
                    id=child_id,
                    description=task_desc,
                    parent_id=root_id,
                    depth=1,
                    priority=i + 1,
                )
                self._nodes[child_id] = child
                root.children_ids.append(child_id)

        return root_id

    def decompose(self, node_id: str, subtasks: list[str]) -> None:
        """Add subtasks to a node (decompose further)."""
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return

            node.state = TaskState.PLANNING
            for i, task_desc in enumerate(subtasks):
                child_id = f"{node_id}_d{i}"
                child = PlanNode(
                    id=child_id,
                    description=task_desc,
                    parent_id=node_id,
                    depth=node.depth + 1,
                )
                self._nodes[child_id] = child
                node.children_ids.append(child_id)

            node.state = TaskState.READY

    def get_ready_tasks(self) -> list[PlanNode]:
        """Get all tasks that are ready to execute (dependencies met)."""
        with self._lock:
            ready = []
            for node in self._nodes.values():
                if node.state == TaskState.READY:
                    deps_met = all(
                        self._nodes.get(dep, PlanNode(id="", description="")).state == TaskState.COMPLETED
                        for dep in node.dependencies
                    )
                    if deps_met:
                        ready.append(node)
            return sorted(ready, key=lambda n: n.priority)

    def mark_running(self, node_id: str) -> None:
        with self._lock:
            node = self._nodes.get(node_id)
            if node:
                node.state = TaskState.RUNNING

    def mark_completed(self, node_id: str, result: Any = None) -> None:
        with self._lock:
            node = self._nodes.get(node_id)
            if node:
                node.state = TaskState.COMPLETED
                node.result = result
                self._check_parent_completion(node)

    def mark_failed(self, node_id: str, error: str = "") -> None:
        with self._lock:
            node = self._nodes.get(node_id)
            if node:
                node.state = TaskState.FAILED
                node.error = error

    def _check_parent_completion(self, node: PlanNode) -> None:
        """Check if all children of a parent are completed."""
        if not node.parent_id:
            return
        parent = self._nodes.get(node.parent_id)
        if parent is None:
            return
        all_done = all(
            self._nodes.get(cid, PlanNode(id="", description="")).state in (TaskState.COMPLETED, TaskState.SKIPPED)
            for cid in parent.children_ids
        )
        if all_done:
            parent.state = TaskState.COMPLETED

    def get_progress(self) -> dict[str, Any]:
        """Get overall plan progress."""
        with self._lock:
            total = len(self._nodes)
            completed = sum(1 for n in self._nodes.values() if n.state == TaskState.COMPLETED)
            failed = sum(1 for n in self._nodes.values() if n.state == TaskState.FAILED)
            running = sum(1 for n in self._nodes.values() if n.state == TaskState.RUNNING)

            return {
                "total_tasks": total,
                "completed": completed,
                "failed": failed,
                "running": running,
                "progress_pct": round(completed / max(total, 1) * 100, 1),
                "is_complete": completed == total,
            }

    def get_tree(self, node_id: str = None) -> dict[str, Any]:
        """Get plan as a tree structure."""
        node_id = node_id or self._root_id
        node = self._nodes.get(node_id)
        if node is None:
            return {}
        return {
            **node.to_dict(),
            "children": [self.get_tree(cid) for cid in node.children_ids],
        }

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_plans": self._plan_counter,
                "total_nodes": len(self._nodes),
                "plan_progress": self.get_progress() if self._nodes else {},
            }


_planner_instance: HierarchicalPlanner | None = None


def get_hierarchical_planner() -> HierarchicalPlanner:
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = HierarchicalPlanner()
    return _planner_instance
