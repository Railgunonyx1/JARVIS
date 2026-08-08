"""JARVIS MK-X Hyper-Optimization Engine — Pipeline Fusion.

Merges sequential pipeline stages into overlapping or concurrent execution.
Tracks actual stage timings, computes optimal execution order via
dependency analysis, and fuses independent stages using a thread pool.
"""

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("jarvis.hyper_opt.pipeline_fusion")


class _Stage:
    """Represents a single pipeline stage with its metadata."""

    __slots__ = ("name", "fn", "dependencies", "estimated_ms", "actual_ms", "call_count")

    def __init__(
        self,
        name: str,
        fn: Callable,
        dependencies: Optional[List[str]] = None,
        estimated_ms: float = 0.0,
    ):
        self.name = name
        self.fn = fn
        self.dependencies = dependencies or []
        self.estimated_ms = estimated_ms
        self.actual_ms = estimated_ms
        self.call_count = 0


class PipelineFusion:
    """Merges sequential pipeline stages into overlapping execution."""

    def __init__(self, max_workers: int = 8):
        self._stages: Dict[str, _Stage] = {}
        self._stage_order: List[str] = []
        self._active_fusions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._fusion_count = 0
        self._total_saved_ms = 0.0
        self._max_workers = max_workers
        logger.info("PipelineFusion initialized (max_workers=%d)", max_workers)

    def register_stage(
        self,
        name: str,
        fn: Callable,
        dependencies: Optional[List[str]] = None,
        estimated_ms: float = 0,
    ) -> None:
        """Register a pipeline stage."""
        with self._lock:
            if name in self._stages:
                logger.warning("Overwriting existing stage '%s'", name)
            else:
                self._stage_order.append(name)
            self._stages[name] = _Stage(name, fn, dependencies, estimated_ms)
            logger.info(
                "Registered stage '%s' (deps=%s, est=%.1f ms)",
                name, dependencies or [], estimated_ms,
            )

    def unregister_stage(self, name: str) -> bool:
        """Remove a pipeline stage."""
        with self._lock:
            if name not in self._stages:
                return False
            del self._stages[name]
            self._stage_order = [s for s in self._stage_order if s != name]
            for stage in self._stages.values():
                if name in stage.dependencies:
                    stage.dependencies.remove(name)
            logger.info("Unregistered stage '%s'", name)
            return True

    def get_optimal_order(self) -> List[str]:
        """Returns stages reordered for maximum parallelism using topological sort."""
        with self._lock:
            in_degree: Dict[str, int] = {name: 0 for name in self._stages}
            dependents: Dict[str, List[str]] = {name: [] for name in self._stages}

            for name, stage in self._stages.items():
                for dep in stage.dependencies:
                    if dep in dependents:
                        dependents[dep].append(name)
                        in_degree[name] += 1

            # Kahn's algorithm for topological sort, prioritized by estimated_ms
            queue = [
                name for name, deg in in_degree.items() if deg == 0
            ]
            queue.sort(key=lambda n: self._stages[n].estimated_ms, reverse=True)

            result: List[str] = []
            while queue:
                current = queue.pop(0)
                result.append(current)
                for dependent in dependents[current]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
                        queue.sort(key=lambda n: self._stages[n].estimated_ms, reverse=True)

            if len(result) != len(self._stages):
                logger.error("Cycle detected in stage dependencies, returning original order")
                return list(self._stage_order)

            return result

    def fuse(self, stage_names: List[str]) -> Dict[str, Any]:
        """Mark stages as fusible (can overlap in time). Returns fusion metadata."""
        with self._lock:
            valid_names = [n for n in stage_names if n in self._stages]
            if len(valid_names) < 2:
                return {"error": "Need at least 2 valid stages to fuse", "stages": valid_names}

            # Check for dependency conflicts
            for name in valid_names:
                stage = self._stages[name]
                for dep in stage.dependencies:
                    if dep in valid_names:
                        return {
                            "error": f"Cannot fuse: '{name}' depends on '{dep}' which is also in the fusion set",
                            "stages": valid_names,
                        }

            fusion_id = f"fusion_{uuid.uuid4().hex[:12]}"
            estimated_total = sum(self._stages[n].estimated_ms for n in valid_names)
            max_sequential = estimated_total  # if run sequentially

            # With perfect parallelism, time = max(estimated_ms)
            max_single = max(self._stages[n].estimated_ms for n in valid_names)

            fusion_meta = {
                "fusion_id": fusion_id,
                "stages": valid_names,
                "estimated_total_ms": round(estimated_total, 3),
                "estimated_parallel_ms": round(max_single, 3),
                "estimated_savings_ms": round(estimated_total - max_single, 3),
                "status": "registered",
                "start_time": None,
                "end_time": None,
                "actual_ms": None,
                "results": {},
            }
            self._active_fusions[fusion_id] = fusion_meta
            self._fusion_count += 1

            logger.info(
                "Created fusion '%s' with %d stages (estimated savings: %.1f ms)",
                fusion_id, len(valid_names), estimated_total - max_single,
            )
            return fusion_meta

    def execute_fused(self, fusion_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute fused stages concurrently using ThreadPoolExecutor."""
        with self._lock:
            if fusion_id not in self._active_fusions:
                return {"error": f"Fusion '{fusion_id}' not found"}
            fusion = self._active_fusions[fusion_id]
            fusion["status"] = "running"
            fusion["start_time"] = time.perf_counter()

        ctx = context or {}
        results: Dict[str, Any] = {}
        errors: Dict[str, Any] = {}
        stage_names = fusion["stages"]

        def _run_stage(name: str) -> tuple:
            stage = self._stages[name]
            start = time.perf_counter()
            try:
                if callable(stage.fn):
                    result = stage.fn(ctx)
                else:
                    result = stage.fn
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                return (name, result, elapsed_ms, None)
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                return (name, None, elapsed_ms, exc)

        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(stage_names))) as pool:
            futures = {pool.submit(_run_stage, name): name for name in stage_names}
            for future in as_completed(futures):
                name, result, elapsed_ms, error = future.result()
                # Record actual timing
                self.measure_stage(name, lambda: None, _skip=True, _elapsed=elapsed_ms)
                if error:
                    errors[name] = str(error)
                    results[name] = None
                    logger.error("Stage '%s' failed in fusion '%s': %s", name, fusion_id, error)
                else:
                    results[name] = result

        with self._lock:
            end_time = time.perf_counter()
            fusion["end_time"] = end_time
            fusion["actual_ms"] = round((end_time - fusion["start_time"]) * 1000.0, 3)
            fusion["results"] = results
            fusion["status"] = "completed" if not errors else "completed_with_errors"
            if errors:
                fusion["errors"] = errors

            savings = max(0, fusion["estimated_total_ms"] - fusion["actual_ms"])
            self._total_saved_ms += savings
            fusion["actual_savings_ms"] = round(savings, 3)

        logger.info(
            "Fusion '%s' completed in %.1f ms (saved ~%.1f ms, %d errors)",
            fusion_id, fusion["actual_ms"], savings, len(errors),
        )
        return dict(fusion)

    def get_fusion_stats(self) -> Dict[str, Any]:
        """Returns fusion_count, avg_saved_ms, pipeline_efficiency."""
        with self._lock:
            completed = [
                f for f in self._active_fusions.values()
                if f["status"] in ("completed", "completed_with_errors")
            ]
            avg_saved = 0.0
            efficiency = 0.0
            if completed:
                total_estimated = sum(f.get("estimated_total_ms", 0) for f in completed)
                total_actual = sum(f.get("actual_ms", 0) for f in completed)
                total_savings = sum(f.get("actual_savings_ms", 0) for f in completed)
                avg_saved = total_savings / len(completed) if completed else 0
                efficiency = (total_actual / total_estimated * 100) if total_estimated > 0 else 0

            return {
                "fusion_count": self._fusion_count,
                "completed_fusions": len(completed),
                "avg_saved_ms": round(avg_saved, 3),
                "total_saved_ms": round(self._total_saved_ms, 3),
                "pipeline_efficiency_pct": round(efficiency, 1),
                "registered_stages": len(self._stages),
            }

    def measure_stage(self, name: str, fn: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Measure and record a stage's actual execution time."""
        skip = kwargs.pop("_skip", False)
        elapsed = kwargs.pop("_elapsed", None)

        if not skip:
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000.0
                logger.error("Stage '%s' measurement failed: %s", name, exc)
                return {"error": str(elapsed), "elapsed_ms": elapsed}
            elapsed = (time.perf_counter() - start) * 1000.0
        else:
            result = None

        with self._lock:
            if name in self._stages:
                stage = self._stages[name]
                # Exponential moving average for smoothing
                alpha = 0.3
                stage.actual_ms = alpha * elapsed + (1 - alpha) * stage.actual_ms
                stage.call_count += 1
                stage.estimated_ms = stage.actual_ms  # update estimate

        return {
            "stage": name,
            "elapsed_ms": round(elapsed, 4),
            "avg_ms": round(stage.actual_ms, 4) if name in self._stages else None,
        }

    def get_stage_timings(self) -> Dict[str, Dict[str, Any]]:
        """Returns timing data for all registered stages."""
        with self._lock:
            result = {}
            for name, stage in self._stages.items():
                result[name] = {
                    "actual_ms": round(stage.actual_ms, 4),
                    "estimated_ms": round(stage.estimated_ms, 4),
                    "call_count": stage.call_count,
                    "dependencies": list(stage.dependencies),
                }
            return result

    def get_fusion(self, fusion_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve details of a specific fusion."""
        with self._lock:
            fusion = self._active_fusions.get(fusion_id)
            return dict(fusion) if fusion else None

    def clear_completed_fusions(self) -> int:
        """Remove completed fusions from active tracking. Returns count removed."""
        with self._lock:
            to_remove = [
                fid for fid, f in self._active_fusions.items()
                if f["status"] in ("completed", "completed_with_errors")
            ]
            for fid in to_remove:
                del self._active_fusions[fid]
            return len(to_remove)

    def reset(self) -> None:
        """Clear all stages and fusions."""
        with self._lock:
            self._stages.clear()
            self._stage_order.clear()
            self._active_fusions.clear()
            self._fusion_count = 0
            self._total_saved_ms = 0.0
            logger.info("PipelineFusion reset")


_fusion_instance: Optional[PipelineFusion] = None
_fusion_lock = threading.RLock()


def get_pipeline_fusion() -> PipelineFusion:
    """Singleton accessor for PipelineFusion."""
    global _fusion_instance
    with _fusion_lock:
        if _fusion_instance is None:
            _fusion_instance = PipelineFusion()
        return _fusion_instance
