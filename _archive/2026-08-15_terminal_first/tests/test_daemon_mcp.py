"""Tests for MCP handlers in the real daemon (daemon/server.py)."""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from daemon.server import DaemonServer
from mcp_jarvis.client import McpClientManager
from runtime.transport.protocol import (
    MSG_MCP_CALL_TOOL,
    MSG_MCP_DISCONNECT,
    MSG_MCP_LIST_TOOLS,
    MSG_MCP_STATUS,
)

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


class FakeTransport:
    def __init__(self):
        self.frames = []

    async def send(self, frame: dict):
        self.frames.append(frame)

    async def receive(self):
        return None


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def daemon(tmp_path, monkeypatch):
    server_py = tmp_path / "echo_server.py"
    server_py.write_text(_ECHO_SERVER, encoding="utf-8")
    cfg = tmp_path / "mcp_servers.json"
    cfg.write_text(
        json.dumps([
            {"name": "echo", "command": sys.executable, "args": [str(server_py)]}
        ]),
        encoding="utf-8",
    )
    d = DaemonServer(project_dir=r"C:\Users\aayan\Desktop\JARVIS")
    d._mcp = McpClientManager(str(cfg))
    return d


def test_mcp_status(daemon):
    t = FakeTransport()
    run(daemon._handle_mcp_status({}, "r1", t))
    r = t.frames[-1]
    assert r["type"] == "result"
    assert r["payload"]["status"]["configured"] == 1
    assert r["payload"]["status"]["connected"] == 0


def test_mcp_list_tools(daemon):
    t = FakeTransport()
    run(daemon._handle_mcp_list_tools({"server": "echo"}, "r2", t))
    r = t.frames[-1]
    assert r["type"] == "result"
    assert r["payload"]["count"] == 1
    assert r["payload"]["tools"][0]["name"] == "echo"


def test_mcp_call_tool(daemon):
    t = FakeTransport()
    run(daemon._handle_mcp_call_tool(
        {"server": "echo", "tool": "echo", "arguments": {"text": "x"}}, "r3", t
    ))
    r = t.frames[-1]
    assert r["type"] == "result"
    assert r["payload"]["result"]["text"] == "echo:x"


def test_mcp_disconnect(daemon):
    t = FakeTransport()
    run(daemon._handle_mcp_list_tools({"server": "echo"}, "r2", t))
    run(daemon._handle_mcp_disconnect({"server": "echo"}, "r4", t))
    r = t.frames[-1]
    assert r["type"] == "ok"
    assert r["payload"]["disconnected"] is True


def test_mcp_missing_server_is_clean_error(daemon):
    t = FakeTransport()
    run(daemon._handle_mcp_list_tools({}, "r5", t))
    r = t.frames[-1]
    assert r["type"] == "error"
    assert "server" in r["payload"]["message"]


def test_protocol_constants_defined():
    assert MSG_MCP_STATUS == "mcp_status"
    assert MSG_MCP_LIST_TOOLS == "mcp_list_tools"
    assert MSG_MCP_CALL_TOOL == "mcp_call_tool"
    assert MSG_MCP_DISCONNECT == "mcp_disconnect"
