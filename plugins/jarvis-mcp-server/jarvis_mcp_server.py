"""JARVIS MCP Server — expose JARVIS's real tool catalog to MCP clients.

Built on the official Model Context Protocol SDK. Reads the live tool
registry from ``tools.build_default_registry`` so DSH (or any MCP client)
sees JARVIS's actual tools with their real JSON schemas.

Usage (spawned by DSH's dsh-mcp-client):
    python plugins/jarvis-mcp-server/jarvis_mcp_server.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

import anyio

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from tools.registry import ToolRegistry
from tools.schema import ToolResult


def main() -> None:
    """Build and run the JARVIS MCP server over stdio."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("jarvis.mcp")

    registry = _load_registry()
    server = Server("jarvis-mcp-server")
    tools: dict[str, Tool] = {}

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return list(tools.values())

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> CallToolResult:
        tool = tools.get(name)
        if tool is None:
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text=f"Unknown tool: {name}")],
            )
        args = arguments or {}
        try:
            raw = await _execute_handler(registry, name, args)
            text = _render_result(raw)
            return CallToolResult(
                isError=False,
                content=[TextContent(type="text", text=text)],
            )
        except Exception as exc:  # noqa: BLE001 - surface any handler failure as a tool error
            logger.exception("tool %s failed", name)
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text=f"{type(exc).__name__}: {exc}")],
            )

    async def serve() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    def build_tool_views() -> None:
        for tool in registry.list():
            tools[tool.name] = Tool(
                name=tool.name,
                description=tool.description,
                inputSchema=tool.parameters,
            )

    build_tool_views()
    logger.info("JARVIS MCP server exposing %d tools", len(tools))
    anyio.run(serve)


def _load_registry() -> ToolRegistry:
    from tools import build_default_registry
    return build_default_registry()


async def _execute_handler(registry: ToolRegistry, name: str, arguments: dict) -> object:
    tool = registry.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    handler = tool.handler
    if asyncio.iscoroutinefunction(handler):
        return await handler(arguments)
    return await asyncio.to_thread(handler, arguments)


def _render_result(raw: object) -> str:
    """Normalize a handler result (str / dict / ToolResult) to text."""
    if isinstance(raw, ToolResult):
        if not raw.success and raw.error:
            return f"error: {raw.error}"
        return raw.output if raw.output else json.dumps(raw.metadata, default=str)
    if isinstance(raw, dict):
        return json.dumps(raw, default=str, indent=2)
    if raw is None:
        return "(no output)"
    return str(raw)


if __name__ == "__main__":
    main()
