"""Pipeline Optimizer — topological sort, critical-path analysis, and stage timing."""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("jarvis.orchestration_engine.pipeline_optimizer")


class PipelineOptimizer:
    """Analyzes pipeline stages, reorders for maximum parallelism, and records timings."""

    def __init__(self) -> None:
        self._stage_stats: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize_pipeline(self, stages: list[dict]) -> list[dict]:
        """Reorder *stages* for maximum parallelism.

        Each stage dict must contain:
            name          – str
            dependencies  – list[str] of stage names that must finish first
            estimated_ms  – float estimate of wall-clock time
            can_parallel  – bool whether it may run alongside siblings

        Returns a new list of stage dicts augmented with ``"parallel_group": int``
        so callers can execute each group concurrently.
        """
        if not stages:
            return []

        stage_map: dict[str, dict] = {s["name"]: s for s in stages}
        in_degree: dict[str, int] = {s["name"]: 0 for s in stages}
        dependents: dict[str, list[str]] = {s["name"]: [] for s in stages}

        for s in stages:
            for dep in s.get("dependencies", []):
                if dep in stage_map:
                    in_degree[s["name"]] += 1
                    dependents[dep].append(s["name"])

        queue: deque = deque()
        for name, deg in in_degree.items():
            if deg == 0:
                queue.append(name)

        ordered: list[str] = []
        while queue:
            current = queue.popleft()
            ordered.append(current)
            for dep_name in dependents[current]:
                in_degree[dep_name] -= 1
                if in_degree[dep_name] == 0:
                    queue.append(dep_name)

        if len(ordered) != len(stages):
            remaining = [s["name"] for s in stages if s["name"] not in ordered]
            logger.warning("Cycle detected; appending remaining stages: %s", remaining)
            ordered.extend(remaining)

        group_assignment: dict[str, int] = {}
        level: dict[str, int] = {}
        for name in ordered:
            deps = [d for d in stage_map[name].get("dependencies", []) if d in level]
            level[name] = (max(level[d] for d in deps) + 1) if deps else 0

        for name in ordered:
            stage = stage_map[name]
            lvl = level[name]
            if not stage.get("can_parallel", False):
                group_assignment[name] = max(group_assignment.values(), default=-1) + 1
            else:
                same_level = [n for n in ordered if level[n] == lvl and n != name]
                sibling_groups = [group_assignment[n] for n in same_level if n in group_assignment]
                if sibling_groups:
                    group_assignment[name] = min(sibling_groups)
                else:
                    group_assignment[name] = max(group_assignment.values(), default=-1) + 1

        result: list[dict] = []
        for name in ordered:
            enriched = dict(stage_map[name])
            enriched["parallel_group"] = group_assignment[name]
            result.append(enriched)

        logger.debug("Optimized %d stages into %d groups",
                      len(stages), len(set(group_assignment.values())))
        return result

    def measure_stage(self, name: str, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute *fn*, record wall-clock timing, and return its result."""
        start = time.perf_counter()
        error = False
        try:
            result = fn(*args, **kwargs)
            return result
        except Exception:
            error = True
            raise
        finally:
            ms = (time.perf_counter() - start) * 1000
            self._record(name, ms, error)

    def get_stage_stats(self) -> dict[str, dict]:
        """Return per-stage ``avg_ms``, ``call_count``, ``p95_ms``."""
        with self._lock:
            stats: dict[str, dict] = {}
            for name, data in self._stage_stats.items():
                timings = data["timings"]
                count = len(timings)
                avg = sum(timings) / count if count else 0.0
                sorted_t = sorted(timings)
                p95_idx = min(int(0.95 * count), count - 1) if count else 0
                p95 = sorted_t[p95_idx] if count else 0.0
                stats[name] = {
                    "avg_ms": round(avg, 3),
                    "call_count": count,
                    "p95_ms": round(p95, 3),
                }
            return stats

    def identify_critical_path(self, stages: list[dict]) -> list[str]:
        """Return the longest dependency chain (by estimated_ms) through *stages*."""
        if not stages:
            return []

        stage_map: dict[str, dict] = {s["name"]: s for s in stages}
        dist: dict[str, float] = {s["name"]: 0.0 for s in stages}
        predecessor: dict[str, str | None] = {s["name"]: None for s in stages}

        in_degree: dict[str, int] = {s["name"]: 0 for s in stages}
        dependents: dict[str, list[str]] = {s["name"]: [] for s in stages}
        for s in stages:
            for dep in s.get("dependencies", []):
                if dep in stage_map:
                    in_degree[s["name"]] += 1
                    dependents[dep].append(s["name"])

        queue: deque = deque()
        for name, deg in in_degree.items():
            if deg == 0:
                queue.append(name)

        topo_order: list[str] = []
        while queue:
            current = queue.popleft()
            topo_order.append(current)
            for dep_name in dependents[current]:
                in_degree[dep_name] -= 1
                if in_degree[dep_name] == 0:
                    queue.append(dep_name)

        for name in topo_order:
            stage = stage_map[name]
            est = stage.get("estimated_ms", 0.0)
            for dep in stage.get("dependencies", []):
                if dep in stage_map:
                    candidate = dist[dep] + est
                    if candidate > dist[name]:
                        dist[name] = candidate
                        predecessor[name] = dep

        end_node = max(dist, key=dist.get) if dist else None
        if end_node is None or dist[end_node] == 0:
            return []

        path: list[str] = []
        node: str | None = end_node
        while node is not None:
            path.append(node)
            node = predecessor[node]
        path.reverse()
        return path

    def suggest_optimizations(self) -> list[dict]:
        """Analyse recorded stage stats and return concrete suggestions."""
        suggestions: list[dict] = []
        stats = self.get_stage_stats()

        slow_stages = [n for n, s in stats.items() if s["avg_ms"] > 500]
        if len(slow_stages) >= 2:
            suggestions.append({
                "name": "parallelize_slow_stages",
                "description": f"Parallelize '{slow_stages[0]}' and '{slow_stages[1]}' "
                               f"(combined avg {stats[slow_stages[0]]['avg_ms'] + stats[slow_stages[1]]['avg_ms']:.0f}ms)",
                "impact": "high",
                "effort": "medium",
                "auto_apply": False,
            })

        high_variance = []
        for name, s in stats.items():
            if s["call_count"] > 5 and s["p95_ms"] > s["avg_ms"] * 2:
                high_variance.append(name)
        for name in high_variance:
            suggestions.append({
                "name": f"stabilize_{name}",
                "description": f"Stage '{name}' has high variance (p95 {stats[name]['p95_ms']:.0f}ms "
                               f"vs avg {stats[name]['avg_ms']:.0f}ms). Consider caching or pre-allocation.",
                "impact": "medium",
                "effort": "low",
                "auto_apply": False,
            })

        for name, s in stats.items():
            if s["avg_ms"] > 1000 and s["call_count"] > 10:
                suggestions.append({
                    "name": f"cache_{name}",
                    "description": f"Stage '{name}' averages {s['avg_ms']:.0f}ms over {s['call_count']} calls. "
                                   f"Consider adding memoization or async processing.",
                    "impact": "high",
                    "effort": "medium",
                    "auto_apply": False,
                })

        if not suggestions:
            suggestions.append({
                "name": "no_optimizations_needed",
                "description": "All stage timings are within acceptable thresholds.",
                "impact": "none",
                "effort": "none",
                "auto_apply": False,
            })

        return suggestions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record(self, name: str, ms: float, error: bool = False) -> None:
        with self._lock:
            if name not in self._stage_stats:
                self._stage_stats[name] = {"timings": [], "errors": 0}
            self._stage_stats[name]["timings"].append(ms)
            if error:
                self._stage_stats[name]["errors"] += 1

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all recorded stage statistics."""
        with self._lock:
            self._stage_stats.clear()


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: PipelineOptimizer | None = None
_lock = threading.Lock()


def get_pipeline_optimizer() -> PipelineOptimizer:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = PipelineOptimizer()
    return _instance
