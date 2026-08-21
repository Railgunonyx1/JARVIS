"""Execution Lanes — interruptible parallel inference for JARVIS MK-X.

Enables lightweight requests (memory lookups, status queries) to run on the
1B model in parallel with a main 3B/4B coding task, without blocking either.

Architecture:
    User request
         │
         ▼
    RequestClassifier
         │
    ┌────┴─────────────┐
    │                  │
    ▼                  ▼
  MAIN TASK        INTERRUPT
  3B / 4B           1B
    │                  │
    │    (parallel)    │
    │                  │
    └────────┬─────────┘
             ▼
         Result
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger("jarvis.lanes")


# ── Execution Lane ──────────────────────────────────────────────────────

class ExecutionLane(str, Enum):
    """Which execution lane a request belongs to."""
    MAIN = "main"           # Full 3B/4B coding task
    INTERRUPT = "interrupt"  # Lightweight 1B query (memory, status, etc.)


class RequestClass(str, Enum):
    """How to classify an incoming request."""
    MAIN_TASK = "main_task"
    LIGHTWEIGHT_INTERRUPT = "lightweight_interrupt"
    MAIN_TASK_MODIFICATION = "main_task_modification"


# ── Interrupt Capabilities ──────────────────────────────────────────────

# Tools that the 1B interrupt lane is ALLOWED to use.
# Read-only, non-destructive, fast.
_INTERRUPT_ALLOWED_TOOLS: frozenset[str] = frozenset({
    "memory.retrieve",
    "memory.search",
    "memory.recent",
    "memory.stats",
    "context.lookup",
    "system.status",
    "git.status",
    "git.branch",
    "git.log",
    "filesystem.read",
    "filesystem.list",
    "search.code",
})

# Patterns that indicate a request is a lightweight interrupt.
_INTERRUPT_PATTERNS: list[re.Pattern] = [
    # Memory/status queries
    re.compile(r"^(what|who|how|when|where)\s+(do you|does|is|are|was|were)\s+(know|remember|know about)", re.I),
    re.compile(r"^(what|who|how)\s+(is|are|was|were)\s+(my|the|our|your)\s+(name|role|project|decision|plan|status)", re.I),
    re.compile(r"^(retrieve|recall|lookup|find|search)\s+(what|our|the|my|info|info about|memory)", re.I),
    re.compile(r"^(what|tell me)\s+(did we|have we|should we)\s+(decide|choose|agree|plan)", re.I),
    re.compile(r"^(status|current|what's|whats)\s+(the\s+)?(status|state|progress|plan|decision)", re.I),
    re.compile(r"^(status|progress|plan)\s+(of|for|on|about)\s+", re.I),
    re.compile(r"^(show|list|display)\s+(me\s+)?(the\s+)?(memory|status|plan|progress|decision)", re.I),
    re.compile(r"^(what|which)\s+(files?|code|function|class)\s+(are|is|was)\s+(being|currently|modified|changed)", re.I),
    re.compile(r"^(remember|recall)\s+(that|when|what|how)", re.I),
    re.compile(r"^(what|how)\s+(is|was)\s+(the|our|my)\s+(architecture|design|approach|strategy)", re.I),
    re.compile(r"^(do you|did you)\s+(know|remember|have)\s+(any|a|the)\s+(context|info|details?)", re.I),
]

# Patterns that indicate a request MODIFIES the main task (should NOT be interrupt).
_MODIFICATION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(remember this|store this|save this|add to memory)\b", re.I),
    re.compile(r"\b(change|modify|update|rewrite|refactor|fix|implement|add|remove|delete)\b", re.I),
    re.compile(r"\b(execute|run|deploy|build|install|compile)\b", re.I),
    re.compile(r"\b(git commit|git push|git merge|git rebase)\b", re.I),
]


# ── Request Classification ──────────────────────────────────────────────

@dataclass(frozen=True)
class ClassifiedRequest:
    """Result of classifying an incoming request."""
    request_class: RequestClass
    lane: ExecutionLane
    confidence: float
    reason: str = ""
    allowed_tools: tuple[str, ...] = ()
    parent_task_id: str | None = None  # Set for interrupts


class RequestClassifier:
    """Classifies incoming requests as main task or lightweight interrupt.

    The classifier answers: "Can this run on the 1B model without blocking
    the current 3B/4B task?"
    """

    def classify(
        self,
        text: str,
        active_task_id: str | None = None,
        active_task_status: str | None = None,
    ) -> ClassifiedRequest:
        """Classify a request for lane assignment.

        Args:
            text: The user's request text.
            active_task_id: ID of the currently running main task (if any).
            active_task_status: Status of the current main task.

        Returns:
            ClassifiedRequest with lane and capability constraints.
        """
        t = text.strip()
        if not t:
            return ClassifiedRequest(
                request_class=RequestClass.MAIN_TASK,
                lane=ExecutionLane.MAIN,
                confidence=0.5,
                reason="empty request",
            )

        tl = t.lower()

        # Check if this is a modification request (MUST go to main lane)
        for pattern in _MODIFICATION_PATTERNS:
            if pattern.search(tl):
                return ClassifiedRequest(
                    request_class=RequestClass.MAIN_TASK_MODIFICATION,
                    lane=ExecutionLane.MAIN,
                    confidence=0.9,
                    reason=f"modification detected: {pattern.pattern[:40]}",
                )

        # Check if this is a lightweight interrupt
        for pattern in _INTERRUPT_PATTERNS:
            if pattern.search(tl):
                # But only if there's actually a main task running
                if active_task_id and active_task_status in (None, "executing", "planning"):
                    return ClassifiedRequest(
                        request_class=RequestClass.LIGHTWEIGHT_INTERRUPT,
                        lane=ExecutionLane.INTERRUPT,
                        confidence=0.85,
                        reason=f"lightweight pattern: {pattern.pattern[:40]}",
                        allowed_tools=_INTERRUPT_ALLOWED_TOOLS,
                        parent_task_id=active_task_id,
                    )

        # No active task or doesn't match interrupt patterns → main lane
        return ClassifiedRequest(
            request_class=RequestClass.MAIN_TASK,
            lane=ExecutionLane.MAIN,
            confidence=0.7,
            reason="default: main task",
        )

    def can_use_interrupt(self, text: str) -> bool:
        """Quick check: could this possibly be an interrupt?"""
        tl = text.strip().lower()
        if not tl:
            return False
        # Must NOT be a modification
        for pattern in _MODIFICATION_PATTERNS:
            if pattern.search(tl):
                return False
        # Must match an interrupt pattern
        for pattern in _INTERRUPT_PATTERNS:
            if pattern.search(tl):
                return True
        return False


# ── Task Registry ───────────────────────────────────────────────────────

@dataclass
class TaskHandle:
    """Handle for a running task."""
    task_id: str
    goal: str
    lane: ExecutionLane
    model: str
    start_time: float = field(default_factory=time.time)
    future: asyncio.Future | None = None
    parent_task_id: str | None = None

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self.start_time) * 1000


class TaskRegistry:
    """Tracks all running tasks across both lanes."""

    def __init__(self):
        self._tasks: dict[str, TaskHandle] = {}
        self._main_task: TaskHandle | None = None

    def register(self, handle: TaskHandle) -> None:
        self._tasks[handle.task_id] = handle
        if handle.lane == ExecutionLane.MAIN:
            self._main_task = handle

    def unregister(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        if self._main_task and self._main_task.task_id == task_id:
            self._main_task = None

    @property
    def main_task(self) -> TaskHandle | None:
        return self._main_task

    @property
    def active_interrupts(self) -> list[TaskHandle]:
        return [
            h for h in self._tasks.values()
            if h.lane == ExecutionLane.INTERRUPT
        ]

    @property
    def has_active_main(self) -> bool:
        return (
            self._main_task is not None
            and self._main_task.future is not None
            and not self._main_task.future.done()
        )

    def summary(self) -> dict[str, Any]:
        return {
            "main": {
                "task_id": self._main_task.task_id if self._main_task else None,
                "goal": self._main_task.goal[:60] if self._main_task else None,
                "model": self._main_task.model if self._main_task else None,
                "elapsed_ms": self._main_task.elapsed_ms if self._main_task else 0,
            },
            "interrupts_active": len(self.active_interrupts),
            "total_tasks": len(self._tasks),
        }


# ── Interrupt Executor ──────────────────────────────────────────────────

class InterruptExecutor:
    """Runs lightweight requests on the 1B model in parallel with the main task.

    The interrupt lane has a STRICT capability profile:
    - Read-only tools only (memory, status, filesystem.read, search.code)
    - No code modification
    - No shell execution
    - No destructive actions
    - No complex tool chains
    - No verification steps
    """

    def __init__(
        self,
        router,  # ProviderRouter
        registry,  # ToolRegistry
        mem=None,
        project=None,
    ):
        self._router = router
        self._registry = registry
        self._mem = mem
        self._project = project
        self._task_registry = TaskRegistry()
        self._interrupt_count = 0
        self._interrupt_results: list[dict[str, Any]] = []

    @property
    def task_registry(self) -> TaskRegistry:
        return self._task_registry

    def _generate_interrupt_id(self) -> str:
        self._interrupt_count += 1
        return f"interrupt_{self._interrupt_count}_{uuid.uuid4().hex[:8]}"

    async def execute(
        self,
        text: str,
        classification: ClassifiedRequest,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Execute a lightweight interrupt on the 1B model.

        Returns a result dict with:
        - success: bool
        - response: str
        - task_id: str
        - latency_ms: float
        - model: str
        """
        task_id = self._generate_interrupt_id()
        start = time.time()

        handle = TaskHandle(
            task_id=task_id,
            goal=text,
            lane=ExecutionLane.INTERRUPT,
            model="qwen2.5:1.5b",  # Always 1B for interrupts
            parent_task_id=classification.parent_task_id,
        )
        self._task_registry.register(handle)

        try:
            # Build minimal context for the interrupt
            from core.agent.context import AgentContextBuilder
            context_builder = AgentContextBuilder(self._registry)

            # For memory queries, include memory context
            if self._mem is not None:
                messages, system_prompt = context_builder.build(
                    text, self._project, self._mem
                )
            else:
                messages = [{"role": "user", "content": text}]
                system_prompt = "You are JARVIS, an engineering assistant. Be concise."

            # Restrict tools to interrupt-safe set
            all_tools = self._registry.to_openai_tools()
            allowed_names = set(classification.allowed_tools)
            tools = [
                t for t in all_tools
                if t.get("function", {}).get("name", "") in allowed_names
            ]

            # Swap to 1B model for the interrupt
            original_model = self._router.get_ollama_model()
            self._router.swap_ollama_model("qwen2.5:1.5b")

            try:
                # Single LLM call — no tool loop for interrupts
                from providers.types import LLMResponse
                response: LLMResponse = await asyncio.wait_for(
                    self._router.complete(
                        messages,
                        system_prompt=system_prompt,
                        max_tokens=512,
                        temperature=0.3,
                        tools=tools if tools else None,
                    ),
                    timeout=10.0,  # 10s hard timeout for interrupts
                )

                final_text = response.text or ""
                latency_ms = (time.time() - start) * 1000

                result = {
                    "success": bool(final_text),
                    "response": final_text,
                    "task_id": task_id,
                    "latency_ms": round(latency_ms, 1),
                    "model": response.model or "qwen2.5:1.5b",
                    "parent_task_id": classification.parent_task_id,
                }

                self._interrupt_results.append(result)
                logger.info(
                    "Interrupt completed: %s in %.0fms (model=%s)",
                    task_id, latency_ms, result["model"],
                )
                return result

            finally:
                # Restore original model
                self._router.swap_ollama_model(original_model)

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start) * 1000
            result = {
                "success": False,
                "response": "",
                "task_id": task_id,
                "latency_ms": round(latency_ms, 1),
                "model": "qwen2.5:1.5b",
                "error": "interrupt timeout (10s)",
                "parent_task_id": classification.parent_task_id,
            }
            self._interrupt_results.append(result)
            return result

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            result = {
                "success": False,
                "response": "",
                "task_id": task_id,
                "latency_ms": round(latency_ms, 1),
                "model": "qwen2.5:1.5b",
                "error": str(e)[:200],
                "parent_task_id": classification.parent_task_id,
            }
            self._interrupt_results.append(result)
            return result

        finally:
            self._task_registry.unregister(task_id)

    def get_stats(self) -> dict[str, Any]:
        """Return interrupt lane statistics."""
        return {
            "total_interrupts": self._interrupt_count,
            "recent_results": self._interrupt_results[-5:],
            "task_registry": self._task_registry.summary(),
        }
