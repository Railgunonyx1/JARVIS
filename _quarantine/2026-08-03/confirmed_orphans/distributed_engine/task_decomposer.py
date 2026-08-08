"""Task Decomposer — breaks high-level tasks into dependency-ordered subtasks."""

import re
import uuid
import time
import threading
import logging
from typing import Any, Dict, List, Optional
from collections import defaultdict, deque

logger = logging.getLogger("jarvis.distributed_engine.task_decomposer")


def _make_id() -> str:
    return f"task_{uuid.uuid4().hex[:8]}"


def _default_patterns() -> Dict[str, dict]:
    """Return regex → decomposition template mapping."""
    return {
        re.compile(
            r"research\s+(.+?)\s+and\s+summarize\s+(.+)",
            re.IGNORECASE,
        ): {
            "template": [
                {"id": None, "description": "Research {0}", "dependencies": [], "estimated_ms": 5000},
                {"id": None, "description": "Research {1}", "dependencies": [], "estimated_ms": 5000},
                {"id": None, "description": "Summarize findings on {0} and {1}",
                 "dependencies": ["t0", "t1"], "estimated_ms": 3000},
            ],
            "fields": ["topic_a", "topic_b"],
        },
        re.compile(
            r"compare\s+(.+?)\s+and\s+(.+)",
            re.IGNORECASE,
        ): {
            "template": [
                {"id": None, "description": "Analyze {0}", "dependencies": [], "estimated_ms": 4000},
                {"id": None, "description": "Analyze {1}", "dependencies": [], "estimated_ms": 4000},
                {"id": None, "description": "Compare {0} vs {1}",
                 "dependencies": ["t0", "t1"], "estimated_ms": 2000},
            ],
            "fields": ["subject_a", "subject_b"],
        },
        re.compile(
            r"(?:do|execute|run)\s+(.+?)\s+then\s+(.+)",
            re.IGNORECASE,
        ): {
            "template": [
                {"id": None, "description": "{0}", "dependencies": [], "estimated_ms": 3000},
                {"id": None, "description": "{1}", "dependencies": ["t0"], "estimated_ms": 3000},
            ],
            "fields": ["step_a", "step_b"],
        },
        re.compile(
            r"(?:do|execute|run)\s+(.+?)\s+(?:and|,)\s+(.+?)(?:\s+then\s+(.+))?$",
            re.IGNORECASE,
        ): {
            "template": "auto",
            "fields": ["step_a", "step_b", "step_c"],
        },
    }


class TaskDecomposer:
    """Decomposes high-level task strings into dependency-ordered subtask lists."""

    def __init__(self) -> None:
        self._patterns: Dict[re.Pattern, dict] = _default_patterns()
        self._lock = threading.Lock()

    def decompose(self, task: str, max_depth: int = 3) -> List[Dict[str, Any]]:
        """Break *task* into subtasks, up to *max_depth* recursion levels."""
        if not task or not task.strip():
            return []

        task = task.strip()
        with self._lock:
            for pattern, spec in self._patterns.items():
                match = pattern.search(task)
                if match:
                    return self._apply_pattern(match, spec)

        return self._generic_decompose(task, max_depth)

    def _apply_pattern(self, match: re.Match, spec: dict) -> List[Dict[str, Any]]:
        """Instantiate a matched pattern template with captured groups."""
        groups = [match.group(i + 1).strip() for i in range(len(match.groups()))]
        template = spec["template"]

        if template == "auto":
            template = self._auto_template(groups)

        result: List[Dict[str, Any]] = []
        id_map: Dict[str, str] = {}

        for idx, entry in enumerate(template):
            new_id = _make_id()
            placeholder = f"t{idx}"
            id_map[placeholder] = new_id

            desc = entry["description"]
            for i, group in enumerate(groups):
                desc = desc.replace(f"{{{i}}}", group)

            deps = [id_map.get(d, d) for d in entry["dependencies"]]
            result.append({
                "id": new_id,
                "description": desc,
                "dependencies": deps,
                "estimated_ms": entry["estimated_ms"],
            })

        return result

    def _auto_template(self, groups: List[str]) -> List[dict]:
        """Build a template from an auto-captured group list."""
        non_none = [g for g in groups if g is not None]
        if len(non_none) == 2:
            return [
                {"id": None, "description": "{0}", "dependencies": [], "estimated_ms": 3000},
                {"id": None, "description": "{1}", "dependencies": ["t0"], "estimated_ms": 3000},
            ]
        if len(non_none) == 3:
            return [
                {"id": None, "description": "{0}", "dependencies": [], "estimated_ms": 3000},
                {"id": None, "description": "{1}", "dependencies": [], "estimated_ms": 3000},
                {"id": None, "description": "{2}", "dependencies": ["t0", "t1"], "estimated_ms": 3000},
            ]
        return [
            {"id": None, "description": "{0}", "dependencies": [], "estimated_ms": 3000},
        ]

    def _generic_decompose(self, task: str, max_depth: int) -> List[Dict[str, Any]]:
        """Fallback: return the task as a single subtask."""
        return [{
            "id": _make_id(),
            "description": task,
            "dependencies": [],
            "estimated_ms": 5000,
        }]

    def get_dependency_graph(self, tasks: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Return an adjacency list mapping each task id to its dependency ids."""
        graph: Dict[str, List[str]] = {}
        for t in tasks:
            graph[t["id"]] = list(t.get("dependencies", []))
        return graph

    def topological_sort(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return tasks in a valid topological order (dependencies before dependents)."""
        id_to_task = {t["id"]: t for t in tasks}
        in_degree: Dict[str, int] = {t["id"]: 0 for t in tasks}
        dependents: Dict[str, List[str]] = defaultdict(list)

        for t in tasks:
            for dep in t.get("dependencies", []):
                if dep in id_to_task:
                    in_degree[t["id"]] += 1
                    dependents[dep].append(t["id"])

        queue: deque = deque()
        for tid, deg in in_degree.items():
            if deg == 0:
                queue.append(tid)

        order: List[Dict[str, Any]] = []
        while queue:
            tid = queue.popleft()
            order.append(id_to_task[tid])
            for dep_tid in dependents.get(tid, []):
                in_degree[dep_tid] -= 1
                if in_degree[dep_tid] == 0:
                    queue.append(dep_tid)

        if len(order) != len(tasks):
            logger.warning(
                "Cycle detected: got %d/%d tasks in topological order",
                len(order), len(tasks),
            )
            for t in tasks:
                if t not in order:
                    order.append(t)

        return order

    def add_pattern(self, pattern: str, template: List[dict], fields: List[str]) -> None:
        """Register a custom decomposition pattern."""
        with self._lock:
            compiled = re.compile(pattern, re.IGNORECASE)
            self._patterns[compiled] = {"template": template, "fields": fields}

    def clear_patterns(self) -> None:
        """Remove all custom patterns and restore defaults."""
        with self._lock:
            self._patterns = _default_patterns()


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: Optional[TaskDecomposer] = None
_instance_lock = threading.Lock()


def get_task_decomposer() -> TaskDecomposer:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = TaskDecomposer()
    return _instance
