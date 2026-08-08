"""ToolRegistry — owns registration, discovery, lookup, and serialization.

Runtime execution stays in core/agent/tools.py; this module is purely the
catalog. No tool logic lives here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.schema import Tool


class ToolRegistry:
    """Thread-safe registry of registered tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def register_many(self, tools: List[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def remove(self, name: str) -> None:
        self._tools.pop(name, None)

    def list(self) -> List[Tool]:
        return list(self._tools.values())

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_openai() for tool in self._tools.values()]

    def to_dicts(self) -> List[Dict[str, Any]]:
        return [tool.to_dict() for tool in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)
