"""JARVIS MK-X tool catalog.

Builds the default tool registry used by the agent runtime. Execution
wrappers live in core/agent/tools.py; individual tool handlers in tools/*.
"""

from __future__ import annotations

from tools.registry import ToolRegistry
from tools.schema import Tool, ToolResult, tool_result


def build_default_registry() -> ToolRegistry:
    """Register the core M0 tool set (filesystem + shell)."""
    from tools.filesystem import filesystem_read, filesystem_write, filesystem_list
    from tools.shell import shell_execute

    registry = ToolRegistry()
    registry.register_many([
        Tool(
            name="filesystem.write",
            description=(
                "Create or overwrite a file on disk with the given content. "
                "Paths are resolved relative to the project root."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute file path."},
                    "content": {"type": "string", "description": "Full file content to write."},
                    "overwrite": {"type": "boolean", "description": "Allow overwriting an existing file. Default true."},
                },
                "required": ["path", "content"],
            },
            permission="filesystem.write",
            handler=filesystem_write,
            category="filesystem",
        ),
        Tool(
            name="filesystem.read",
            description="Read a file and return its contents. Paths resolve relative to the project root.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute file path."},
                },
                "required": ["path"],
            },
            permission="filesystem.read",
            handler=filesystem_read,
            category="filesystem",
        ),
        Tool(
            name="filesystem.list",
            description="List entries in a directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path. Defaults to project root."},
                    "detail": {"type": "boolean", "description": "Include sizes/dates. Default false."},
                },
                "required": [],
            },
            permission="filesystem.list",
            handler=filesystem_list,
            category="filesystem",
        ),
        Tool(
            name="shell.execute",
            description=(
                "Execute a command on the host system and return its stdout/stderr. "
                "Prefer structured form: 'executable' + 'args' (runs without a shell). "
                "For shell scripts use 'command' with optional 'shell' (powershell|cmd); "
                "chaining operators and dangerous commands are rejected. "
                "Use for anything the filesystem tools cannot do. Output is truncated; "
                "long-running commands may time out."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "executable": {"type": "string", "description": "Executable path or name. Preferred over 'command'."},
                    "args": {
                        "oneOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "string"},
                        ],
                        "description": "Argument list (structured, no shell). May be a list or a stringified list.",
                    },
                    "command": {"type": "string", "description": "A shell command string. Chaining/operators are blocked."},
                    "shell": {"type": "string", "enum": ["powershell", "cmd"], "description": "Shell host for raw commands. Default powershell."},
                    "cwd": {"type": "string", "description": "Working directory. Defaults to project root."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds. Default 60, max 300."},
                },
                "required": [],
            },
            permission="shell.execute",
            handler=shell_execute,
            category="system",
        ),
    ])
    return registry


__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "tool_result",
    "build_default_registry",
]
