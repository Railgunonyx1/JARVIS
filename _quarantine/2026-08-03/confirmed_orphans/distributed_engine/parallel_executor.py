"""Parallel Executor — runs independent tasks concurrently with dependency awareness."""

import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict, deque

logger = logging.getLogger("jarvis.distributed_engine.parallel_executor")


class ParallelExecutor:
    """Executes task dicts respecting a dependency graph via thread pooling."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_completed: int = 0
        self._total_failed: int = 0
        self._total_duration_ms: float = 0.0

    def execute(
        self,
        tasks: List[Dict[str, Any]],
        max_workers: int = 4,
    ) -> List[Dict[str, Any]]:
        """Execute tasks respecting dependency order.

        Each task dict must contain:
            "id": str, "fn": Callable, "args": tuple, "kwargs": dict
        Optional:
            "dependencies": list[str]

        Returns a list of result dicts with id, result, error, duration_ms.
        """
        if not tasks:
            return []

        task_map: Dict[str, Dict[str, Any]] = {t["id"]: t for t in tasks}
        dep_map: Dict[str, List[str]] = {
            t["id"]: list(t.get("dependencies", [])) for t in tasks
        }
        in_degree: Dict[str, int] = {t["id"]: 0 for t in tasks}
        dependents: Dict[str, List[str]] = defaultdict(list)

        for t in tasks:
            for dep in t.get("dependencies", []):
                if dep in task_map:
                    in_degree[t["id"]] += 1
                    dependents[dep].append(t["id"])

        completed: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        futures: Dict[str, Future] = {}
        results: List[Dict[str, Any]] = []
        results_lock = threading.Lock()
        start = time.perf_counter()

        def _run_task(task_id: str) -> Dict[str, Any]:
            task = task_map[task_id]
            fn: Callable = task["fn"]
            args: tuple = task.get("args", ())
            kwargs: dict = task.get("kwargs", {})
            task_start = time.perf_counter()
            try:
                res = fn(*args, **kwargs)
                duration = (time.perf_counter() - task_start) * 1000.0
                return {"id": task_id, "result": res, "error": None, "duration_ms": round(duration, 2)}
            except Exception as exc:
                duration = (time.perf_counter() - task_start) * 1000.0
                return {"id": task_id, "result": None, "error": str(exc), "duration_ms": round(duration, 2)}

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            ready = deque(
                tid for tid, deg in in_degree.items() if deg == 0
            )

            while ready or futures:
                while ready:
                    tid = ready.popleft()
                    futures[tid] = pool.submit(_run_task, tid)

                done_futures = [tid for tid, f in futures.items() if f.done()]
                if not done_futures and not ready:
                    break

                for tid in done_futures:
                    fut = futures.pop(tid)
                    try:
                        res = fut.result()
                    except Exception as exc:
                        res = {"id": tid, "result": None, "error": str(exc), "duration_ms": 0.0}

                    with results_lock:
                        results.append(res)
                        if res["error"]:
                            errors[res["id"]] = res["error"]
                        else:
                            completed[res["id"]] = res["result"]

                    for dep_tid in dependents.get(tid, []):
                        in_degree[dep_tid] -= 1
                        if in_degree[dep_tid] <= 0:
                            ready.append(dep_tid)

                time.sleep(0.005)

        elapsed_ms = (time.perf_counter() - start) * 1000.0

        with self._lock:
            for r in results:
                self._total_completed += 1
                self._total_duration_ms += r["duration_ms"]
                if r["error"]:
                    self._total_failed += 1

        results.sort(key=lambda r: r["id"])
        logger.info(
            "Executed %d tasks in %.1f ms (%d failed)",
            len(results), elapsed_ms, len(errors),
        )
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate execution statistics."""
        with self._lock:
            total = self._total_completed
            avg = self._total_duration_ms / total if total > 0 else 0.0
            return {
                "tasks_completed": self._total_completed,
                "tasks_failed": self._total_failed,
                "avg_duration_ms": round(avg, 2),
                "total_duration_ms": round(self._total_duration_ms, 2),
                "parallelism_ratio": round(
                    self._total_duration_ms / max(avg, 0.001), 2
                ) if total > 0 else 0.0,
            }

    def reset_stats(self) -> None:
        """Zero out all counters."""
        with self._lock:
            self._total_completed = 0
            self._total_failed = 0
            self._total_duration_ms = 0.0


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: Optional[ParallelExecutor] = None
_instance_lock = threading.Lock()


def get_parallel_executor() -> ParallelExecutor:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ParallelExecutor()
    return _instance
