"""
MCP Server for JARVIS MK-X — exposes internal tools via Model Context Protocol.
Allows external clients to call JARVIS capabilities as MCP tools.
"""

import asyncio
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from core.capability_registry import get_capability
from core.mode_manager import get_mode_manager
from core.skill_loader import get_skill_loader

logger = logging.getLogger("jarvis.mcp_server")


# Mapping from capability names to executor tool names
CAPABILITY_TO_TOOL = {
    "app.launch": "open_app",
    "app.close": "open_app",
    "app.list": "open_app",
    "media.control": "computer_control",
    "media.volume": "audio",
    "system.volume": "audio",
    "clipboard.read": "clipboard",
    "clipboard.write": "clipboard",
    "clipboard.history": "clipboard",
    "window.manage": "window_manager",
    "window.list": "window_manager",
    "memory.store": "memory",
    "memory.query": "memory",
    "memory.recall": "memory",
    "filesystem.read": "file_controller",
    "filesystem.list": "file_controller",
    "filesystem.search": "file_controller",
    "filesystem.write": "file_controller",
    "filesystem.delete": "file_controller",
    "filesystem.move": "file_controller",
    "terminal.read": "shell",
    "terminal.execute": "shell",
    "process.list": "process_manager",
    "process.kill": "process_manager",
    "service.query": "service_manager",
    "service.list": "service_manager",
    "service.manage": "service_manager",
    "registry.read": "computer_settings",
    "registry.write": "computer_settings",
    "shell.execute": "shell",
    "package.install": "shell",
    "package.uninstall": "shell",
    "package.remove": "shell",
    "network.query": "network",
    "network.modify": "network",
    "display.manage": "display",
    "audio.manage": "audio",
    "startup.query": "startup_manager",
    "startup.manage": "startup_manager",
    "startup.modify": "startup_manager",
    "task.schedule": "task_scheduler",
    "task.list": "task_scheduler",
    "task.manage": "task_scheduler",
    "external.network.read": "mcp_call_tool",
    "external.network.write": "mcp_call_tool",
    "external.write": "mcp_call_tool",
    "time.query": "system_settings",
    "weather.query": "system_settings",
    "calculator": "system_settings",
    "notifications.send": "system_settings",
    "system.info": "system_settings",
    "screen.capture": "screen_analyzer",
    "screen.analyze": "screen_analyzer",
    "screen.find_element": "screen_analyzer",
    "browser.download": "browser",
    "web.search": "web_search",
    "web.open": "browser",
    "web.scrape": "browser",
}


class JarvisMCPServer:
    """MCP server that exposes JARVIS tools to external clients."""

    def __init__(self):
        self.server = Server("jarvis-mkx")
        self._tools: dict = {}
        self._register_tools()

    def _register_tools(self):
        """Register all available JARVIS capabilities as MCP tools."""
        mode_manager = get_mode_manager()
        skill_loader = get_skill_loader()

        # Get tools available in current mode
        available_capabilities = mode_manager.get_available_tool_names()
        skills = skill_loader.get_skills_for_mode()

        for cap_name in available_capabilities:
            cap = get_capability(cap_name)
            if not cap:
                continue

            # Find which skill provides this capability
            providing_skill = None
            for skill in skills.values():
                if cap_name in skill.capabilities:
                    providing_skill = skill
                    break

            # Build tool description
            description = cap.description
            if providing_skill:
                description += f" (via {providing_skill.name})"

            # Build input schema
            input_schema = {
                "type": "object",
                "properties": {
                    "parameters": {
                        "type": "object",
                        "description": f"Parameters for {cap_name}",
                        "additionalProperties": True
                    }
                }
            }

            tool = Tool(
                name=cap_name,
                description=description,
                inputSchema=input_schema
            )

            self._tools[cap_name] = tool

        # Register tool list handler
        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return list(self._tools.values())

        # Register tool call handler
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> CallToolResult:
            return await self._execute_tool(name, arguments)

    async def _execute_tool(self, cap_name: str, arguments: dict) -> CallToolResult:
        """Execute a JARVIS capability via the executor."""
        try:
            # Import executor lazily to avoid circular imports
            from core.executor import _call_tool

            # Check permissions
            mode_manager = get_mode_manager()
            if not mode_manager.is_allowed(cap_name):
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Capability '{cap_name}' not allowed in {mode_manager.get_mode()} mode")],
                    isError=True
                )

            # Map capability to executor tool name
            tool_name = CAPABILITY_TO_TOOL.get(cap_name)
            if not tool_name:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"No executor mapping for capability '{cap_name}'")],
                    isError=True
                )

            # Execute the tool
            params = arguments.get("parameters", {})
            result = _call_tool(tool_name, params, None)

            return CallToolResult(
                content=[TextContent(type="text", text=str(result))]
            )

        except Exception as e:
            logger.error(f"MCP tool {cap_name} failed: {e}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True
            )

    async def run(self):
        """Run the MCP server over stdio."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


async def main():
    """Entry point for running the MCP server."""
    logging.basicConfig(level=logging.INFO)
    server = JarvisMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
