"""Async MCP client manager for JARVIS MK-X.

Connects to external MCP servers (stdlib, stdio) so the daemon can
discover and call their tools over its WebSocket API. Reads server
specs from config/mcp_servers.json (same file used by the CLI plugin).

Server spec (JSON):
    {"name": "filesystem", "command": "npx", "args": [...]}
    {"name": "weather", "url": "http://localhost:8000/mcp"}  # streamable HTTP

Sessions are cached until explicitly disconnected or a call fails with a
transport error (then one automatic reconnect is attempted).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.mcp_client")

_DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "mcp_servers.json",
)


class McpClientManager:
    """Manages connections to external MCP servers."""

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = config_path or _DEFAULT_CONFIG
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._tools_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configured_servers(self) -> List[Dict[str, Any]]:
        """Return the server specs from config/mcp_servers.json."""
        try:
            with open(self._config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except FileNotFoundError:
            return []
        except Exception as exc:
            logger.error("Failed to read %s: %s", self._config_path, exc)
            return []

    def _server_spec(self, name: str) -> Optional[Dict[str, Any]]:
        for cfg in self.configured_servers():
            if cfg.get("name") == name:
                return cfg
        return None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self, name: str, *, force: bool = False) -> bool:
        """Connect to an MCP server (no-op if already connected)."""
        async with self._lock:
            if name in self._sessions and not force:
                return True
            spec = self._server_spec(name)
            if not spec:
                raise ValueError(f"No MCP server named '{name}' in config.")
            if name in self._sessions:
                await self._close_session(name)

            if spec.get("url"):
                from mcp import ClientSession
                from mcp.client.streamable_http import streamablehttp_client

                ctx = streamablehttp_client(spec["url"])
                read, write = await ctx.__aenter__()
            else:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client

                params = StdioServerParameters(
                    command=spec["command"],
                    args=spec.get("args", []),
                    env=spec.get("env"),
                )
                ctx = stdio_client(params)
                read, write = await ctx.__aenter__()

            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            self._sessions[name] = {"session": session, "ctx": ctx}
            self._tools_cache.pop(name, None)
            logger.info("Connected to MCP server: %s", name)
            return True

    async def _close_session(self, name: str) -> None:
        entry = self._sessions.pop(name, None)
        self._tools_cache.pop(name, None)
        if not entry:
            return
        try:
            await entry["session"].__aexit__(None, None, None)
        except Exception:
            pass
        try:
            await entry["ctx"].__aexit__(None, None, None)
        except Exception:
            pass

    async def disconnect(self, name: str) -> bool:
        """Disconnect from an MCP server."""
        async with self._lock:
            if name not in self._sessions:
                return False
            await self._close_session(name)
            logger.info("Disconnected from MCP server: %s", name)
            return True

    async def disconnect_all(self) -> None:
        """Disconnect every server (call on daemon shutdown)."""
        async with self._lock:
            for name in list(self._sessions):
                await self._close_session(name)

    async def _get_session(self, name: str):
        await self.connect(name)
        return self._sessions[name]["session"]

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def list_tools(self, name: str, *, refresh: bool = False) -> List[Dict[str, Any]]:
        """List tools exposed by an MCP server (cached between calls)."""
        if not refresh and name in self._tools_cache:
            return self._tools_cache[name]
        session = await self._get_session(name)
        result = await session.list_tools()
        tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.inputSchema,
            }
            for t in result.tools
        ]
        self._tools_cache[name] = tools
        return tools

    async def call_tool(
        self,
        name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Call a tool on an MCP server, reconnecting once on transport errors."""
        try:
            return await self._call_tool_once(name, tool_name, arguments or {})
        except (ConnectionError, OSError, TimeoutError) as exc:
            logger.warning("MCP call failed, reconnecting %s: %s", name, exc)
            await self.disconnect(name)
            return await self._call_tool_once(name, tool_name, arguments or {})

    async def _call_tool_once(
        self, name: str, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        session = await self._get_session(name)
        result = await session.call_tool(tool_name, arguments=arguments)
        texts = []
        structured = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                texts.append(text)
            else:
                structured.append(block)
        is_error = bool(getattr(result, "isError", False))
        return {
            "server": name,
            "tool": tool_name,
            "is_error": is_error,
            "text": "\n".join(texts) if texts else "(no text content)",
            "structured": len(structured),
        }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self) -> Dict[str, Any]:
        """Snapshot of configured vs connected servers."""
        configured = self.configured_servers()
        servers = []
        for cfg in configured:
            name = cfg.get("name", "?")
            connected = name in self._sessions
            tools = len(self._tools_cache.get(name, [])) if connected else 0
            servers.append(
                {
                    "name": name,
                    "command": cfg.get("command"),
                    "url": cfg.get("url"),
                    "connected": connected,
                    "tools_cached": tools,
                }
            )
        return {
            "configured": len(configured),
            "connected": len(self._sessions),
            "servers": servers,
        }


__all__ = ["McpClientManager"]
