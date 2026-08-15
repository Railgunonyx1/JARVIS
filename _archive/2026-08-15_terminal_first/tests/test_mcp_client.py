"""Tests for the async MCP client manager (mcp_jarvis/client.py)."""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from mcp_jarvis.client import McpClientManager

_ECHO_SERVER = r"""
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

server = Server("test-echo")

@server.list_tools()
async def list_tools():
    return [Tool(name="echo", description="Echo text", inputSchema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
    })]

@server.call_tool()
async def call_tool(name, arguments):
    return CallToolResult(content=[TextContent(type="text", text=f"echo:{arguments.get('text', '')}")])

async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())

asyncio.run(main())
"""


@pytest.fixture
def echo_config(tmp_path):
    server_py = tmp_path / "echo_server.py"
    server_py.write_text(_ECHO_SERVER, encoding="utf-8")
    cfg = tmp_path / "mcp_servers.json"
    cfg.write_text(
        json.dumps([
            {
                "name": "echo",
                "command": sys.executable,
                "args": [str(server_py)],
            }
        ]),
        encoding="utf-8",
    )
    return str(cfg)


_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return a process-wide event loop.

    McpClientManager holds stdio subprocess transports that are bound to the
    loop they were created on. A fresh loop per call (the previous helper)
    would strand those transports and hang on disconnect, so tests share one
    loop just like the daemon does.
    """
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def run(coro):
    loop = _get_loop()
    try:
        return loop.run_until_complete(coro)
    except Exception:
        import traceback

        traceback.print_exc()
        raise


def test_configured_servers_loads(echo_config):
    mgr = McpClientManager(echo_config)
    assert [s["name"] for s in mgr.configured_servers()] == ["echo"]


def test_status_initial(echo_config):
    mgr = McpClientManager(echo_config)
    status = run(mgr.status())
    assert status["configured"] == 1
    assert status["connected"] == 0


def test_list_tools_connects(echo_config):
    mgr = McpClientManager(echo_config)
    tools = run(mgr.list_tools("echo"))
    assert tools[0]["name"] == "echo"
    assert "input_schema" in tools[0]


def test_call_tool(echo_config):
    mgr = McpClientManager(echo_config)
    result = run(mgr.call_tool("echo", "echo", {"text": "hi"}))
    assert result["is_error"] is False
    assert result["text"] == "echo:hi"


def test_unknown_server_raises_valueerror(echo_config):
    mgr = McpClientManager(echo_config)
    with pytest.raises(ValueError):
        run(mgr.list_tools("missing"))


def test_disconnect(echo_config):
    mgr = McpClientManager(echo_config)
    run(mgr.list_tools("echo"))
    assert run(mgr.status())["connected"] == 1
    assert run(mgr.disconnect("echo")) is True
    assert run(mgr.status())["connected"] == 0


def test_disconnect_all(echo_config):
    mgr = McpClientManager(echo_config)
    run(mgr.list_tools("echo"))
    run(mgr.disconnect_all())
    assert run(mgr.status())["connected"] == 0


def test_missing_config_file_is_clean():
    mgr = McpClientManager("/nonexistent/mcp_servers.json")
    assert mgr.configured_servers() == []
    assert run(mgr.status())["configured"] == 0
