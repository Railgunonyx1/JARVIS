"""Protocol Adapters -- MCP, ACP, and Codex exec compatibility.

Enables JARVIS to interoperate with external agents and editors.
Each adapter translates between the external protocol and the JARVIS
event bus / agent loop.

Architecture:
    External Agent -> Protocol Adapter -> BusEvent -> Event Bus -> Core Kernel
    Core Kernel -> BusEvent -> Event Bus -> Protocol Adapter -> External Agent
"""

from __future__ import annotations

import enum
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jarvis.protocols")


class ProtocolType(enum.Enum):
    MCP = "mcp"           # Model Context Protocol
    ACP = "acp"           # Agent Client Protocol
    CODEX_EXEC = "codex_exec"  # OpenAI Codex exec protocol


@dataclass(frozen=True)
class ProtocolMessage:
    """Canonical message format that adapters translate to/from."""
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str = ""
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    protocol: ProtocolType = ProtocolType.MCP


class MCPAdapter:
    """Adapts JARVIS to the Model Context Protocol (MCP).

    Exposes JARVIS tools as MCP tools and translates MCP requests
    into JARVIS agent actions.

    MCP is the standard protocol for exposing tools to LLM clients.
    """

    def __init__(self, agent_loop=None, tool_registry=None, tool_service=None):
        self._agent_loop = agent_loop
        self._registry = tool_registry
        self._tool_service = tool_service

    def list_tools(self) -> list[dict]:
        """Expose JARVIS tools as MCP tool definitions."""
        if self._registry is not None:
            tools = self._registry.to_openai_tools()
        elif self._tool_service is not None:
            tools = self._tool_service.list_tools()
        else:
            return []
        return [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "inputSchema": t["function"].get("parameters", {}),
            }
            for t in tools
        ]

    async def handle_request(self, method: str, params: dict[str, Any]) -> ProtocolMessage:
        """Handle an incoming MCP request."""
        if method == "tools/list":
            return ProtocolMessage(
                method=method,
                result=self.list_tools(),
                protocol=ProtocolType.MCP,
            )
        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = await self._call_tool(tool_name, arguments)
            return ProtocolMessage(
                method=method,
                result=result,
                protocol=ProtocolType.MCP,
            )
        return ProtocolMessage(
            method=method,
            error=f"Unknown MCP method: {method}",
            protocol=ProtocolType.MCP,
        )

    async def _call_tool(self, name: str, arguments: dict) -> Any:
        if self._tool_service is None:
            return {"error": "No tool execution service configured"}
        from providers.types import ToolCall
        call = ToolCall(name=name, arguments=arguments, id=uuid.uuid4().hex[:8])
        result = await self._tool_service.execute_tool(call, trace_id="mcp")
        return {
            "status": "completed" if result.success else "error",
            "tool": name,
            "output": result.output[:1000] if result.success else result.error,
        }


class ACPAdapter:
    """Adapts JARVIS to the Agent Client Protocol (ACP).

    ACP enables editors (VS Code, etc.) to communicate with agents.
    All tool calls go through ToolExecutionService.
    """

    def __init__(self, agent_loop=None, bus=None, tool_service=None):
        self._agent_loop = agent_loop
        self._bus = bus
        self._tool_service = tool_service

    async def handle_request(self, method: str, params: dict[str, Any]) -> ProtocolMessage:
        if method == "agent/status":
            return ProtocolMessage(
                method=method,
                result={"status": "ready", "agent": "jarvis-mkx"},
                protocol=ProtocolType.ACP,
            )
        if method == "agent/run":
            goal = params.get("goal", "")
            if self._agent_loop:
                result = await self._agent_loop.run(goal)
                return ProtocolMessage(
                    method=method,
                    result={"success": result.success, "response": result.response},
                    protocol=ProtocolType.ACP,
                )
            return ProtocolMessage(method=method, error="No agent loop", protocol=ProtocolType.ACP)
        if method == "agent/cancel":
            return ProtocolMessage(method=method, result={"cancelled": True}, protocol=ProtocolType.ACP)
        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = await self._call_tool(tool_name, arguments)
            return ProtocolMessage(
                method=method,
                result=result,
                protocol=ProtocolType.ACP,
            )
        if method == "tools/list":
            return ProtocolMessage(
                method=method,
                result=self._list_tools(),
                protocol=ProtocolType.ACP,
            )
        return ProtocolMessage(method=method, error=f"Unknown ACP method: {method}", protocol=ProtocolType.ACP)

    async def _call_tool(self, name: str, arguments: dict) -> Any:
        if self._tool_service is None:
            return {"error": "No tool execution service configured"}
        from providers.types import ToolCall
        call = ToolCall(name=name, arguments=arguments, id=uuid.uuid4().hex[:8])
        result = await self._tool_service.execute_tool(call, trace_id="acp")
        return {
            "status": "completed" if result.success else "error",
            "tool": name,
            "output": result.output[:1000] if result.success else result.error,
        }

    def _list_tools(self) -> list[dict]:
        if self._tool_service is None:
            return []
        tools = self._tool_service.list_tools()
        return [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
            }
            for t in tools
        ]


class CodexExecAdapter:
    """Adapts JARVIS to the Codex exec protocol.

    Enables JARVIS to act as a drop-in replacement for the Codex binary
    via path override, without replacing JARVIS's internal protocol.
    All tool calls go through ToolExecutionService.
    """

    def __init__(self, agent_loop=None, tool_service=None):
        self._agent_loop = agent_loop
        self._tool_service = tool_service

    async def handle_exec(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle a Codex exec protocol request."""
        prompt = payload.get("prompt", payload.get("input", ""))
        if not prompt:
            return {"error": "No prompt in exec request"}
        if self._agent_loop is None:
            return {"error": "No agent loop configured"}
        try:
            result = await self._agent_loop.run(prompt)
            return {
                "output": result.response,
                "success": result.success,
                "error": result.error or "",
            }
        except Exception as e:
            return {"error": str(e)[:500]}

    async def handle_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Direct tool execution through ToolExecutionService."""
        if self._tool_service is None:
            return {"error": "No tool execution service configured"}
        from providers.types import ToolCall
        call = ToolCall(name=name, arguments=arguments, id=uuid.uuid4().hex[:8])
        result = await self._tool_service.execute_tool(call, trace_id="codex")
        return {
            "status": "completed" if result.success else "error",
            "tool": name,
            "output": result.output[:1000] if result.success else result.error,
        }


class ProtocolRegistry:
    """Central registry for all protocol adapters."""

    def __init__(self):
        self._adapters: dict[ProtocolType, Any] = {}

    def register(self, protocol: ProtocolType, adapter: Any) -> None:
        self._adapters[protocol] = adapter

    def get(self, protocol: ProtocolType) -> Any:
        return self._adapters.get(protocol)

    def list_protocols(self) -> list[str]:
        return [p.value for p in self._adapters]
