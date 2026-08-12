"""
MCP client plugin for JARVIS MK-X.

Registers with the existing plugin_loader.py (jarvis_plugin decorator),
so no changes to the plugin discovery system are needed — drop this
file in your plugins/ directory and it's picked up automatically.

What this gives you: connect to any MCP server (calendar, email, Slack,
home automation, whatever) by adding it to servers.json, and JARVIS can
call its tools without you writing a dedicated integration for each
service. This does NOT replace plugin_loader.py's existing pattern —
use a hand-written plugin when you want tight control over one specific
action; use this when you want to plug in an existing MCP server fast.

Requires the OFFICIAL stable SDK, not the v2 pre-release:
    pip install "mcp<2"

Config file (create this yourself): config/mcp_servers.json
[
  {
    "name": "filesystem",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"]
  },
  {
    "name": "calendar",
    "command": "python",
    "args": ["-m", "some_calendar_mcp_server"]
  }
]

Each entry is a server JARVIS can talk to over stdio. This file is not
included — you decide which servers you trust enough to connect.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from core.plugin_loader import jarvis_plugin
from core.utils import get_project_root

logger = logging.getLogger("jarvis.plugins.mcp_client")

_CONFIG_PATH = get_project_root() / "config" / "mcp_servers.json"

# One persistent event loop + set of live sessions, so we don't pay
# stdio-process-spawn cost on every single tool call.
_loop: asyncio.AbstractEventLoop | None = None
_sessions: dict[str, Any] = {}
_sessions_lock = asyncio.Lock() if False else None  # created lazily inside the loop


def _load_server_configs() -> list[dict]:
    if not _CONFIG_PATH.exists():
        return []
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to read mcp_servers.json: %s", e)
        return []


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


async def _connect(server_name: str):
    """Connect to one configured MCP server over stdio and cache the session."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    configs = {c["name"]: c for c in _load_server_configs()}
    cfg = configs.get(server_name)
    if not cfg:
        raise ValueError(
            f"No MCP server named '{server_name}' in config/mcp_servers.json. "
            f"Available: {list(configs.keys())}"
        )

    params = StdioServerParameters(command=cfg["command"], args=cfg.get("args", []))
    stdio_ctx = stdio_client(params)
    read, write = await stdio_ctx.__aenter__()
    session = ClientSession(read, write)
    await session.__aenter__()
    await session.initialize()

    _sessions[server_name] = {"session": session, "stdio_ctx": stdio_ctx}
    return session


async def _get_session(server_name: str):
    if server_name in _sessions:
        return _sessions[server_name]["session"]
    return await _connect(server_name)


async def _list_tools_async(server_name: str) -> list[dict]:
    session = await _get_session(server_name)
    result = await session.list_tools()
    return [
        {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
        for t in result.tools
    ]


async def _call_tool_async(server_name: str, tool_name: str, arguments: dict) -> str:
    session = await _get_session(server_name)
    result = await session.call_tool(tool_name, arguments=arguments)
    parts = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts) if parts else "(tool returned no text content)"


def _run(coro):
    loop = _get_loop()
    return loop.run_until_complete(coro)


@jarvis_plugin(
    name="mcp_list_servers",
    description="List configured MCP servers available to connect to.",
    patterns=["what mcp servers", "list mcp servers", "available integrations"],
)
def mcp_list_servers() -> str:
    configs = _load_server_configs()
    if not configs:
        return (
            "No MCP servers configured. Add entries to config/mcp_servers.json "
            "to connect calendar, email, Slack, etc."
        )
    names = ", ".join(c["name"] for c in configs)
    return f"Configured MCP servers: {names}"


@jarvis_plugin(
    name="mcp_list_tools",
    description="List tools available on a given MCP server.",
    patterns=["what can {server} do", "list tools for {server}"],
)
def mcp_list_tools(server_name: str) -> str:
    try:
        tools = _run(_list_tools_async(server_name))
    except Exception as e:
        logger.error("mcp_list_tools failed for %s: %s", server_name, e)
        return f"Couldn't reach MCP server '{server_name}': {e}"

    if not tools:
        return f"'{server_name}' exposes no tools."
    lines = [f"- {t['name']}: {t['description']}" for t in tools]
    return f"Tools on '{server_name}':\n" + "\n".join(lines)


@jarvis_plugin(
    name="mcp_call_tool",
    description="Call a specific tool on a connected MCP server with arguments.",
    patterns=["use {server} to {action}"],
)
def mcp_call_tool(server_name: str, tool_name: str, arguments: dict | None = None) -> str:
    arguments = arguments or {}
    try:
        return _run(_call_tool_async(server_name, tool_name, arguments))
    except Exception as e:
        logger.error("mcp_call_tool failed (%s/%s): %s", server_name, tool_name, e)
        return f"Tool call failed: {e}"


def register_plugin():
    """Called by plugin_loader.py after import, per its existing convention."""
    logger.info("MCP client plugin registered. Configured servers: %s",
                [c["name"] for c in _load_server_configs()])
