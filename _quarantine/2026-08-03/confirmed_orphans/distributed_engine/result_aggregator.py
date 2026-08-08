"""Result Aggregator — collects and merges results from parallel task batches."""

import time
import threading
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.distributed_engine.result_aggregator")

_BATCH_TTL_SECONDS = 3600.0  # auto-clean after 1 hour


class ResultAggregator:
    """Thread-safe result collector for parallel task batches."""

    def __init__(self) -> None:
        self._batches: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def create_batch(self, batch_id: str, expected_count: int) -> None:
        """Create a new result batch expecting *expected_count* results."""
        with self._lock:
            self._batches[batch_id] = {
                "expected": max(1, expected_count),
                "results": [],
                "errors": [],
                "start_time": time.monotonic(),
            }
            logger.info(
                "Created batch '%s' expecting %d results",
                batch_id, expected_count,
            )

    def add_result(
        self,
        batch_id: str,
        task_id: str,
        result: Any,
        error: Optional[str] = None,
    ) -> None:
        """Add a task result to the named batch."""
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                logger.warning("Batch '%s' not found, creating on the fly", batch_id)
                self._batches[batch_id] = {
                    "expected": 1,
                    "results": [],
                    "errors": [],
                    "start_time": time.monotonic(),
                }
                batch = self._batches[batch_id]

            entry = {"task_id": task_id, "result": result}
            if error:
                entry["error"] = error
                batch["errors"].append(entry)
            else:
                batch["results"].append(entry)

            self._clean_expired()

    def is_complete(self, batch_id: str) -> bool:
        """Return True if all expected results have been received."""
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return False
            total = len(batch["results"]) + len(batch["errors"])
            return total >= batch["expected"]

    def get_results(self, batch_id: str) -> Dict[str, Any]:
        """Return a snapshot of the batch with results, errors, and elapsed time."""
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return {"results": [], "errors": [], "duration_ms": 0.0}
            elapsed = (time.monotonic() - batch["start_time"]) * 1000.0
            return {
                "results": list(batch["results"]),
                "errors": list(batch["errors"]),
                "duration_ms": round(elapsed, 2),
            }

    def get_aggregate(self, batch_id: str, strategy: str = "collect") -> Any:
        """Aggregate results using the given strategy.

        Strategies:
            "collect" — return a list of all non-error results (default).
            "first"   — return the first non-None result.
            "merge"   — merge all results as dicts (last-write-wins).
        """
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return [] if strategy == "collect" else None

            results = [r["result"] for r in batch["results"]]

        if strategy == "first":
            for r in results:
                if r is not None:
                    return r
            return None

        if strategy == "merge":
            merged: Dict[str, Any] = {}
            for r in results:
                if isinstance(r, dict):
                    merged.update(r)
            return merged

        # default: collect
        return results

    def remove_batch(self, batch_id: str) -> bool:
        """Manually remove a batch. Returns True if it existed."""
        with self._lock:
            if batch_id in self._batches:
                del self._batches[batch_id]
                return True
            return False

    def _clean_expired(self) -> None:
        """Remove batches older than _BATCH_TTL_SECONDS. Caller must hold _lock."""
        now = time.monotonic()
        expired = [
            bid for bid, b in self._batches.items()
            if (now - b["start_time"]) > _BATCH_TTL_SECONDS
        ]
        for bid in expired:
            del self._batches[bid]
        if expired:
            logger.debug("Cleaned %d expired batches", len(expired))

    def get_all_batches(self) -> Dict[str, dict]:
        """Return metadata for all active batches (for diagnostics)."""
        with self._lock:
            self._clean_expired()
            summary: Dict[str, dict] = {}
            for bid, b in self._batches.items():
                elapsed = (time.monotonic() - b["start_time"]) * 1000.0
                summary[bid] = {
                    "expected": b["expected"],
                    "received": len(b["results"]) + len(b["errors"]),
                    "errors": len(b["errors"]),
                    "duration_ms": round(elapsed, 2),
                    "complete": (len(b["results"]) + len(b["errors"])) >= b["expected"],
                }
            return summary


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: Optional[ResultAggregator] = None
_instance_lock = threading.Lock()


def get_result_aggregator() -> ResultAggregator:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ResultAggregator()
    return _instance
