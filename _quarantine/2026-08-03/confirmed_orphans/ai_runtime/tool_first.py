"""Tool-First Execution — Check tools before calling LLM.

Before calling an LLM, check: calculator, database, memory, search, filesystem.
If a tool answers directly, skip the LLM entirely.
"""
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("ai_runtime.tool_first")


@dataclass
class ToolCheck:
    """Result of checking a tool."""
    tool_name: str
    can_handle: bool
    confidence: float = 0.0
    result: Any = None
    latency_ms: float = 0.0


class ToolFirstExecutor:
    """Check tools before calling LLM to avoid unnecessary inference.

    Pattern:
    1. User asks a question
    2. Check if any tool can answer directly
    3. If yes → return tool result (fast, free)
    4. If no → fall through to LLM (slow, costs tokens)
    """

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stats = {
            "total_checks": 0,
            "tool_resolved": 0,
            "llm_required": 0,
            "avg_tool_latency_ms": 0.0,
            "tokens_saved": 0,
        }

    def register_tool(self, name: str, checker: Callable,
                      keywords: list[str] = None, avg_tokens: int = 50) -> None:
        """Register a tool that can potentially answer without LLM."""
        with self._lock:
            self._tools[name] = {
                "checker": checker,
                "keywords": keywords or [],
                "avg_tokens": avg_tokens,
                "resolved_count": 0,
            }

    def check_all_tools(self, query: str) -> ToolCheck | None:
        """Check all registered tools for a direct answer."""
        self._stats["total_checks"] += 1
        query_lower = query.lower()

        best_check = None
        best_confidence = 0.0

        with self._lock:
            tools = dict(self._tools)

        for name, tool in tools.items():
            # Quick keyword filter
            if tool["keywords"]:
                if not any(kw in query_lower for kw in tool["keywords"]):
                    continue

            start = time.time()
            try:
                can_handle, result = tool["checker"](query)
                latency_ms = (time.time() - start) * 1000

                check = ToolCheck(
                    tool_name=name,
                    can_handle=can_handle,
                    confidence=0.8 if can_handle else 0.0,
                    result=result,
                    latency_ms=latency_ms,
                )

                if can_handle and check.confidence > best_confidence:
                    best_check = check
                    best_confidence = check.confidence

            except Exception as e:
                logger.debug("Tool check %s failed: %s", name, e)

        if best_check and best_check.can_handle:
            self._stats["tool_resolved"] += 1
            self._stats["tokens_saved"] += tools[best_check.tool_name]["avg_tokens"]
            tools[best_check.tool_name]["resolved_count"] += 1
            return best_check

        self._stats["llm_required"] += 1
        return None

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            tool_usage = {
                name: tool["resolved_count"]
                for name, tool in self._tools.items()
                if tool["resolved_count"] > 0
            }
            return {
                **self._stats,
                "registered_tools": len(self._tools),
                "tool_usage": tool_usage,
            }


_tool_first_instance: ToolFirstExecutor | None = None


def get_tool_first_executor() -> ToolFirstExecutor:
    global _tool_first_instance
    if _tool_first_instance is None:
        _tool_first_instance = ToolFirstExecutor()
    return _tool_first_instance
