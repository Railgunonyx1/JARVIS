"""Ahead-of-Time Warm-Up — Compile regexes, preload tokenizers, warm pools at startup.

Removes first-use delays (cold start penalties).
"""
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("optimization_system.aot_warmup")


@dataclass
class WarmUpTask:
    """A single warm-up task."""
    name: str
    func: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    priority: int = 5  # 1=highest
    completed: bool = False
    latency_ms: float = 0.0
    error: str | None = None


class AOTWarmUp:
    """Ahead-of-Time warm-up system.

    At startup:
    - Compile commonly used regexes
    - Initialize thread pools
    - Warm up LLM connection pools
    - Pre-allocate buffers
    - Pre-cache deterministic responses

    Eliminates first-use latency spikes.
    """

    def __init__(self):
        self._tasks: list[WarmUpTask] = []
        self._compiled_regexes: dict[str, Any] = {}
        self._prewarmed: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._warmup_complete = False
        self._total_latency_ms = 0.0

        # Register common regexes to pre-compile
        self._common_patterns = {
            "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            "url": r'https?://[^\s]+',
            "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "ip": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
            "date": r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
            "time": r'\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?\b',
            "number": r'\b\d+(?:\.\d+)?\b',
            "word": r'\b\w+\b',
            "whitespace": r'\s+',
            "markdown_heading": r'^#{1,6}\s+',
            "markdown_bold": r'\*{1,2}([^*]+)\*{1,2}',
            "code_block": r'```[\s\S]*?```',
            "import": r'^(?:import|from)\s+',
            "function_def": r'def\s+\w+',
            "class_def": r'class\s+\w+',
        }

    def register_task(self, name: str, func: Callable, *args, priority: int = 5, **kwargs) -> None:
        with self._lock:
            self._tasks.append(WarmUpTask(
                name=name, func=func, args=args, kwargs=kwargs, priority=priority
            ))

    def compile_regexes(self) -> dict[str, Any]:
        """Pre-compile all common regexes."""
        start = time.time()
        for name, pattern in self._common_patterns.items():
            try:
                self._compiled_regexes[name] = re.compile(pattern)
            except re.error as e:
                logger.debug("Regex compile failed for %s: %s", name, e)

        elapsed_ms = (time.time() - start) * 1000
        logger.info("Pre-compiled %d regexes in %.1fms", len(self._compiled_regexes), elapsed_ms)
        return self._compiled_regexes

    def get_compiled_regex(self, name: str):
        """Get a pre-compiled regex by name."""
        return self._compiled_regexes.get(name)

    def prewarm(self, key: str, value: Any) -> None:
        """Store a pre-warmed resource."""
        self._prewarmed[key] = value

    def get_prewarmed(self, key: str) -> Any | None:
        return self._prewarmed.get(key)

    async def run_warmup(self) -> dict[str, Any]:
        """Execute all registered warm-up tasks."""
        start = time.time()
        results = {}

        # 1. Compile regexes
        self.compile_regexes()

        # 2. Run registered tasks in priority order
        sorted_tasks = sorted(self._tasks, key=lambda t: t.priority)
        for task in sorted_tasks:
            task_start = time.time()
            try:
                if hasattr(task.func, '__call__'):
                    result = task.func(*task.args, **task.kwargs)
                    task.completed = True
                    results[task.name] = {"status": "ok", "result": result}
                else:
                    task.completed = True
                    results[task.name] = {"status": "skipped"}
            except Exception as e:
                task.error = str(e)
                results[task.name] = {"status": "error", "error": str(e)}

            task.latency_ms = (time.time() - task_start) * 1000

        self._total_latency_ms = (time.time() - start) * 1000
        self._warmup_complete = True

        logger.info("AOT warm-up complete in %.0fms (%d tasks)",
                     self._total_latency_ms, len(sorted_tasks))

        return {
            "total_ms": round(self._total_latency_ms, 1),
            "tasks_completed": sum(1 for t in self._tasks if t.completed),
            "tasks_failed": sum(1 for t in self._tasks if t.error),
            "regexes_compiled": len(self._compiled_regexes),
            "prewarmed_items": len(self._prewarmed),
            "results": results,
        }

    def is_complete(self) -> bool:
        return self._warmup_complete

    def get_stats(self) -> dict[str, Any]:
        return {
            "warmup_complete": self._warmup_complete,
            "total_latency_ms": round(self._total_latency_ms, 1),
            "registered_tasks": len(self._tasks),
            "compiled_regexes": len(self._compiled_regexes),
            "prewarmed_items": len(self._prewarmed),
        }


_warmup_instance: AOTWarmUp | None = None


def get_aot_warmup() -> AOTWarmUp:
    global _warmup_instance
    if _warmup_instance is None:
        _warmup_instance = AOTWarmUp()
    return _warmup_instance
