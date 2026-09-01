"""Background memory worker and memory lifecycle (Stage 1G).

Expensive memory work (embeddings, extraction, graph updates, compaction)
never runs on the chat path. The worker runs a priority queue:

    HIGH    — persist decisions / explicit saves
    MEDIUM  — create embeddings
    LOW     — compression & decay
    IDLE    — graph updates / archival

``drain()`` processes pending work synchronously (used at shutdown and by
tests that need deterministic ordering); ``close()`` drains then stops.
"""

from __future__ import annotations

import heapq
import itertools
import logging
import threading
from collections.abc import Callable
from typing import Any

from memory.models import MemoryItem

logger = logging.getLogger("jarvis.memory.lifecycle")

# Numeric priority — lower number runs first.
PRIORITY_HIGH = 0
PRIORITY_MEDIUM = 1
PRIORITY_LOW = 2
PRIORITY_IDLE = 3
PRIORITY_NAMES = {0: "HIGH", 1: "MEDIUM", 2: "LOW", 3: "IDLE"}

# Session memory promotes to long-term when it clears this bar.
RETENTION_HIGH = 0.5


class MemoryWorker:
    """Priority queue of callables with explicit consumption.

    ``enqueue()`` only queues work and never spawns a thread, so a caller
    that immediately ``drain()`` sees deterministic priority order. The
    optional background thread starts only via an explicit ``start()``
    (production calls it from ``get_mem()``) and is paused while ``drain()``
    runs, so shutdown and tests never race the background consumer.
    """

    def __init__(self) -> None:
        self._heap: list[tuple] = []
        self._seq = itertools.count()
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None
        self._paused = False
        self._stop = False

    def enqueue(self, priority: int, fn: Callable, *args: Any, **kwargs: Any) -> None:
        with self._cond:
            if self._stop:
                return
            heapq.heappush(self._heap, (priority, next(self._seq), fn, args, kwargs))
            self._cond.notify()

    def start(self) -> None:
        """Explicitly start the background draining thread (production)."""
        with self._cond:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="jarvis-memory-worker", daemon=True)
            self._thread.start()

    def pause(self) -> None:
        """Suspend the background thread (owned by ``drain()``)."""
        with self._cond:
            self._paused = True
            self._cond.notify_all()

    def resume(self) -> None:
        with self._cond:
            self._paused = False
            self._cond.notify_all()

    def _pop(self) -> tuple | None:
        with self._cond:
            return heapq.heappop(self._heap) if self._heap else None

    def _run(self) -> None:
        while True:
            with self._cond:
                if self._stop and not self._heap:
                    return
                if self._paused or not self._heap:
                    self._cond.wait(timeout=0.5)
                    continue
                item = heapq.heappop(self._heap)
            self._execute(item)

    def _execute(self, item: tuple) -> None:
        priority, _, fn, args, kwargs = item
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("Memory worker job %s failed (%s)",
                             fn.__name__, PRIORITY_NAMES.get(priority, "?"))

    def drain(self) -> int:
        """Run all currently-queued jobs in priority order, synchronously."""
        ran = 0
        self.pause()
        try:
            while True:
                item = self._pop()
                if item is None:
                    return ran
                self._execute(item)
                ran += 1
        finally:
            self.resume()

    def pending(self) -> int:
        with self._cond:
            return len(self._heap)

    def close(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()
            thread = self._thread
        self.drain()
        if thread is not None:
            thread.join(timeout=2.0)


class MemoryLifecycle:
    """Session → long-term → archive lifecycle + background task scheduling."""

    ARCHIVE_WINDOW_DAYS = 90

    def __init__(self, worker: MemoryWorker | None = None) -> None:
        self._worker = worker or MemoryWorker()
        self._session: dict[str, MemoryItem] = {}
        self._session_lock = threading.Lock()

    # ── session memory ────────────────────────────────────────────────
    def store_session(self, item: MemoryItem, promote_fn: Callable | None = None) -> None:
        """Buffer an item for the current session; promote to long-term when important."""
        with self._session_lock:
            self._session[item.content[:80] or "item"] = item
        if item.importance >= RETENTION_HIGH and promote_fn is not None:
            self.enqueue(PRIORITY_HIGH, promote_fn, item)

    def recall_session(self, query: str, top_k: int = 5) -> list[MemoryItem]:
        query = query.lower()
        scored = []
        with self._session_lock:
            for item in self._session.values():
                if query in item.content.lower():
                    scored.append((item, item.importance))
                elif any(query in t for t in item.tags):
                    scored.append((item, item.importance * 0.8))
        scored.sort(key=lambda pair: -pair[1])
        return [item for item, _ in scored[:top_k]]

    def session_size(self) -> int:
        with self._session_lock:
            return len(self._session)

    # ── scheduling ────────────────────────────────────────────────────
    def save_decision(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
        self.enqueue(PRIORITY_HIGH, fn, *args, **kwargs)

    def embed(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
        self.enqueue(PRIORITY_MEDIUM, fn, *args, **kwargs)

    def compress(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
        self.enqueue(PRIORITY_LOW, fn, *args, **kwargs)

    def graph_update(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
        self.enqueue(PRIORITY_IDLE, fn, *args, **kwargs)

    def enqueue(self, priority: int, fn: Callable, *args: Any, **kwargs: Any) -> None:
        self._worker.enqueue(priority, fn, *args, **kwargs)

    def start(self) -> None:
        """Start the background draining thread (production entry points)."""
        self._worker.start()

    def drain(self) -> int:
        return self._worker.drain()

    def pending(self) -> int:
        return self._worker.pending()

    def get_stats(self) -> dict[str, Any]:
        return {
            "session": self.session_size(),
            "queue": self._worker.pending(),
        }

    def close(self) -> None:
        self._worker.close()
