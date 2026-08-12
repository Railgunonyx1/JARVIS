"""Batch Similar Requests — Process similar tasks in single GPU batch.

OCR + OCR + OCR → Single GPU Batch → Parallel Results
"""
import asyncio
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("gpu_optimization.batch_requests")


@dataclass
class BatchItem:
    """An item in a batch request."""
    item_id: str
    data: Any
    result: Any = None
    error: str | None = None


class BatchRequestProcessor:
    """Batch similar requests for GPU efficiency.

    Instead of running N separate GPU inferences:
    1. Collect similar requests over a short window
    2. Combine into a single batch
    3. Process all at once
    4. Distribute results
    """

    BATCH_WINDOW_MS = 10  # Collect for 10ms before processing
    MAX_BATCH_SIZE = 32

    def __init__(self):
        self._pending_batches: dict[str, list[BatchItem]] = {}
        self._lock = threading.Lock()
        self._stats = {
            "total_batches": 0,
            "total_items": 0,
            "avg_batch_size": 0.0,
            "avg_speedup": 0.0,
        }

    async def submit(self, batch_type: str, data: Any, processor: Callable) -> Any:
        """Submit an item for batch processing."""
        item = BatchItem(item_id=f"item_{time.time_ns()}", data=data)

        with self._lock:
            if batch_type not in self._pending_batches:
                self._pending_batches[batch_type] = []
            self._pending_batches[batch_type].append(item)

            batch = self._pending_batches[batch_type]
            if len(batch) >= self.MAX_BATCH_SIZE:
                ready = list(batch)
                self._pending_batches[batch_type] = []
            else:
                ready = None

        if ready:
            return await self._process_batch(ready, processor)

        # Wait for batch window
        await asyncio.sleep(self.BATCH_WINDOW_MS / 1000)

        with self._lock:
            batch = self._pending_batches.get(batch_type, [])
            if item in batch:
                batch.remove(item)
                if batch:
                    ready = list(batch)
                    self._pending_batches[batch_type] = []
                else:
                    ready = [item]

        if ready:
            return await self._process_batch(ready, processor)

        return item.result

    async def _process_batch(self, items: list[BatchItem], processor: Callable) -> Any:
        """Process a batch of items."""
        self._stats["total_batches"] += 1
        self._stats["total_items"] += len(items)
        n = self._stats["total_batches"]
        self._stats["avg_batch_size"] = (
            (self._stats["avg_batch_size"] * (n - 1) + len(items)) / n
        )

        try:
            if hasattr(processor, '__call__'):
                if asyncio.iscoroutinefunction(processor):
                    results = await processor([item.data for item in items])
                else:
                    results = processor([item.data for item in items])

                if isinstance(results, list):
                    for item, result in zip(items, results):
                        item.result = result
                else:
                    for item in items:
                        item.result = results

                # Estimate speedup from batching
                self._stats["avg_speedup"] = min(len(items) * 0.8, 10.0)

        except Exception as e:
            for item in items:
                item.error = str(e)

        # Return the result for the first item
        return items[0].result if items else None

    def get_stats(self) -> dict[str, Any]:
        return dict(self._stats)


_batch_instance: BatchRequestProcessor | None = None


def get_batch_processor() -> BatchRequestProcessor:
    global _batch_instance
    if _batch_instance is None:
        _batch_instance = BatchRequestProcessor()
    return _batch_instance
