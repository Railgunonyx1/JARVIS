"""Tool executor for JARVIS - prevents duplicate tool calls.

Maintains a set of executed call IDs to ensure each tool call
is only executed once per agent loop iteration.
"""

import json
import logging
from typing import Any

logger = logging.getLogger("jarvis.tools.executor")


class ToolCall:
    """Represents a tool call with a unique identifier."""

    def __init__(self, name: str, arguments: dict, call_id: str | None = None):
        self.name = name
        self.arguments = arguments or {}
        self.id = call_id or self._generate_id()

    def _generate_id(self) -> str:
        """Generate a unique ID for this tool call."""
        import hashlib
        call_str = f"{self.name}:{json.dumps(self.arguments, sort_keys=True)}"
        return f"tc_{hashlib.md5(call_str.encode()).hexdigest()[:8]}"

    def __repr__(self):
        return f"ToolCall(id={self.id}, name={self.name})"

    def __eq__(self, other):
        if other is None:
            return False
        return self.id == other.id and self.name == other.name

    def __hash__(self):
        return hash(self.id)


class ToolExecutor:
    """Executes tool calls with duplicate prevention."""

    def __init__(self):
        self.executed_calls: set[str] = set()
        self.call_history: list[ToolCall] = []

    def should_execute(self, tool_call: ToolCall) -> bool:
        """Check if this tool call has already been executed."""
        if tool_call.id in self.executed_calls:
            logger.info(
                "Skipping duplicate tool call: %s (id=%s already executed)",
                tool_call.name, tool_call.id
            )
            return False
        return True

    def mark_executed(self, tool_call: ToolCall) -> None:
        """Mark a tool call as executed."""
        self.executed_calls.add(tool_call.id)
        self.call_history.append(tool_call)
        # Keep history manageable
        if len(self.call_history) > 100:
            self.call_history = self.call_history[-50:]

    async def execute(self, tool_name: str, arguments: dict,
                      executor_func) -> Any:
        """Execute a tool call with duplicate prevention.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            executor_func: Async function that performs the actual execution

        Returns:
            Tool execution result
        """
        tool_call = ToolCall(tool_name, arguments)

        if not self.should_execute(tool_call):
            # Return cached result from history if available
            for prev in reversed(self.call_history):
                if prev.name == tool_name and prev.arguments == arguments:
                    logger.info("Returning cached result for duplicate tool call")
                    return self._get_cached_result(prev)

            # If not in history, still prevent execution
            logger.warning("Blocked duplicate tool call without history entry")
            return {"status": "blocked", "reason": "duplicate_call"}

        # Execute the tool
        try:
            result = await executor_func(tool_name, arguments)
            self.mark_executed(tool_call)
            return result
        except Exception as e:
            logger.error("Tool execution error: %s", e, exc_info=True)
            # Still mark as executed so it isn't retried loopingly
            self.mark_executed(tool_call)
            return {"status": "error", "error": str(e), "name": tool_name}

    def _get_cached_result(self, tool_call: ToolCall) -> dict:
        """Get cached result from history (stub - would store actual results)."""
        # In a full implementation, this would return the actual previous result
        # For now, return a marker indicating it was cached
        return {
            "status": "cached",
            "note": "Previous execution result - details stored in call history",
            "call_id": tool_call.id
        }

    def reset(self) -> None:
        """Reset the executor state (for new agent loop iteration)."""
        self.executed_calls.clear()
        self.call_history.clear()


# Convenience function for agent loop integration
_executor = ToolExecutor()

def execute_tool(tool_name: str, arguments: dict, executor_func) -> Any:
    """Convenience function for agent loop integration.

    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments
        executor_func: Async function that performs the actual execution

    Returns:
        Tool execution result
    """
    return _executor.execute(tool_name, arguments, executor_func)


def reset_tool_executor() -> None:
    """Reset the global executor state (call between agent loop iterations)."""
    _executor.reset()
