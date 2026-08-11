"""Tool schema — the Tool / ToolResult contract for the agent runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

ToolHandler = Callable[[dict[str, Any]], Awaitable["ToolResult"]]


@dataclass
class ToolResult:
    """Normalized outcome of a tool execution. Never a raw string."""

    success: bool
    output: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Tool:
    """A capability exposed to the agent, described by a JSON schema."""

    name: str
    description: str
    parameters: dict[str, Any]
    permission: str
    handler: ToolHandler
    category: str = ""

    def to_openai(self) -> dict[str, Any]:
        """Serialize to an OpenAI-style function tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "permission": self.permission,
            "category": self.category,
        }


def tool_result(success: bool, output: str = "", error: str = "",
                **metadata) -> ToolResult:
    """Convenience constructor for handlers."""
    return ToolResult(success=success, output=output, error=error, metadata=metadata)


def truncate(text: str, max_chars: int) -> str:
    """Truncate tool output to a sane size, keeping head and tail."""
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    head = text[: max_chars * 3 // 4]
    tail = text[-(max_chars // 4):]
    return f"{head}\n... [truncated {len(text) - max_chars} chars] ...\n{tail}"
