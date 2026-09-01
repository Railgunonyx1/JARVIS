"""
JARVIS MCP Server

Exposes JARVIS's tools via MCP (Model Context Protocol) so DSH can use them.
This server runs as a subprocess and communicates via stdio.

Usage:
    python jarvis_mcp_server.py
    
DSH connects via:
    - id: jarvis-tools
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: jarvis
        transport: stdio
        command: python
        args: ['plugins/jarvis-mcp-server/jarvis_mcp_server.py']
"""

import json
import sys
import os
import asyncio
from typing import Any, Dict, List, Optional

# Add JARVIS to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# ── MCP Protocol Implementation ────────────────────────────────────────────

class MCPServer:
    """Minimal MCP server implementation over stdio."""
    
    def __init__(self):
        self.tools: Dict[str, Dict] = {}
        self._register_tools()
    
    def _register_tools(self):
        """Register all JARVIS tools."""
        
        # Filesystem tools
        self.tools["filesystem.read"] = {
            "name": "filesystem.read",
            "description": "Read file contents from the filesystem",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                    "offset": {"type": "integer", "description": "Line offset (optional)"},
                    "limit": {"type": "integer", "description": "Max lines to read (optional)"},
                },
                "required": ["path"],
            },
        }
        
        self.tools["filesystem.write"] = {
            "name": "filesystem.write",
            "description": "Write content to a file",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        }
        
        self.tools["filesystem.search"] = {
            "name": "filesystem.search",
            "description": "Search for files matching a pattern",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern to match"},
                    "path": {"type": "string", "description": "Directory to search in"},
                },
                "required": ["pattern"],
            },
        }
        
        # Shell tools
        self.tools["shell.execute"] = {
            "name": "shell.execute",
            "description": "Execute a shell command",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute"},
                    "cwd": {"type": "string", "description": "Working directory (optional)"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (optional)"},
                },
                "required": ["command"],
            },
        }
        
        # Memory tools
        self.tools["memory.recall"] = {
            "name": "memory.recall",
            "description": "Recall memories related to a query",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Query to search memories"},
                    "limit": {"type": "integer", "description": "Max memories to return (optional)"},
                },
                "required": ["query"],
            },
        }
        
        self.tools["memory.remember"] = {
            "name": "memory.remember",
            "description": "Store a new memory",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Memory key/category"},
                    "value": {"type": "string", "description": "Memory content"},
                },
                "required": ["key", "value"],
            },
        }
        
        # Search tools
        self.tools["web.search"] = {
            "name": "web.search",
            "description": "Search the web for information",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        }
        
        # Verification tools
        self.tools["verification.run_tests"] = {
            "name": "verification.run_tests",
            "description": "Run project tests",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Test file pattern (optional)"},
                },
            },
        }
        
        self.tools["verification.run_lint"] = {
            "name": "verification.run_lint",
            "description": "Run linter on project",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        }
    
    def handle_request(self, request: Dict) -> Dict:
        """Handle an MCP request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        if method == "initialize":
            return self._handle_initialize(request_id, params)
        elif method == "tools/list":
            return self._handle_list_tools(request_id)
        elif method == "tools/call":
            return self._handle_call_tool(request_id, params)
        else:
            return self._error(request_id, -32601, f"Method not found: {method}")
    
    def _handle_initialize(self, request_id: Any, params: Dict) -> Dict:
        """Handle initialize request."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "jarvis-mcp-server",
                    "version": "0.1.0",
                },
            },
        }
    
    def _handle_list_tools(self, request_id: Any) -> Dict:
        """Handle tools/list request."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": list(self.tools.values()),
            },
        }
    
    def _handle_call_tool(self, request_id: Any, params: Dict) -> Dict:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name not in self.tools:
            return self._error(request_id, -32602, f"Unknown tool: {tool_name}")
        
        try:
            result = self._execute_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2),
                        }
                    ],
                },
            }
        except Exception as e:
            return self._error(request_id, -32000, str(e))
    
    def _execute_tool(self, tool_name: str, arguments: Dict) -> Any:
        """Execute a JARVIS tool."""
        from core.agent.tools import ToolRegistry
        
        tr = ToolRegistry()
        return tr.execute(tool_name, arguments)
    
    def _error(self, request_id: Any, code: int, message: str) -> Dict:
        """Create an error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }

# ── Main Loop ──────────────────────────────────────────────────────────────

def main():
    """Run the MCP server."""
    server = MCPServer()
    
    # Read from stdin, write to stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            request = json.loads(line)
            response = server.handle_request(request)
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError as e:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {e}",
                },
            }
            print(json.dumps(response), flush=True)

if __name__ == "__main__":
    main()
