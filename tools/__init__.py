"""JARVIS MK-X tool catalog.

Builds the default tool registry used by the agent runtime. Execution
wrappers live in core/agent/tools.py; individual tool handlers in tools/*.
"""

from __future__ import annotations

from tools.registry import ToolRegistry
from tools.schema import Tool, ToolResult, tool_result


def build_default_registry() -> ToolRegistry:
    """Register the core M0 tool set (filesystem + shell) plus world monitor."""
    from tools.filesystem import filesystem_read, filesystem_write, filesystem_list
    from tools.shell import shell_execute
    from tools.world_monitor import (
        world_monitor_get_alerts,
        world_monitor_get_event,
        world_monitor_get_region,
        world_monitor_get_sources,
        world_monitor_search,
        world_monitor_world_brief,
    )

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
        Tool(
            name="world_monitor.search",
            description=(
                "Search real-time global intelligence (news and events) for a query. "
                "Returns matching articles/events from World Monitor's aggregated "
                "sources. Use for current-events research: 'what is happening with X'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free-text search query."},
                    "category": {"type": "string", "description": "Optional category to narrow to (e.g. geopolitics, finance, climate)."},
                    "limit": {"type": "integer", "description": "Max results to return. Default 10."},
                },
                "required": ["query"],
            },
            permission="world_monitor.read",
            handler=world_monitor_search,
            category="world",
        ),
        Tool(
            name="world_monitor.get_alerts",
            description=(
                "Return live situational alerts: conflicts, crises, and natural "
                "disasters. Use for 'what is happening in <region> right now' and "
                "disruption awareness (aviation, shipping, infrastructure incidents)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region or country to scope alerts to."},
                    "severity": {"type": "string", "description": "Minimum severity filter."},
                    "limit": {"type": "integer", "description": "Max alerts to return. Default 10."},
                },
                "required": [],
            },
            permission="world_monitor.read",
            handler=world_monitor_get_alerts,
            category="world",
        ),
        Tool(
            name="world_monitor.get_region",
            description=(
                "Return a situational brief and risk snapshot for a country or "
                "region (political, conflict, economic, infrastructure signals)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "country": {"type": "string", "description": "Country name or ISO code."},
                    "region": {"type": "string", "description": "Broader region name (fallback if country is empty)."},
                    "limit": {"type": "integer", "description": "Max signals to return. Default 10."},
                },
                "required": ["country"],
            },
            permission="world_monitor.read",
            handler=world_monitor_get_region,
            category="world",
        ),
        Tool(
            name="world_monitor.get_event",
            description=(
                "Return detail for one specific World Monitor event id (as returned "
                "by world_monitor.search or world_monitor.get_alerts)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "The event id to look up."},
                    "event_type": {"type": "string", "description": "Optional event type (conflict, disaster, cyber, market...)."},
                },
                "required": ["event_id"],
            },
            permission="world_monitor.read",
            handler=world_monitor_get_event,
            category="world",
        ),
        Tool(
            name="world_monitor.get_sources",
            description=(
                "List the data sources and coverage World Monitor exposes "
                "(conflict, aviation, shipping, markets, weather, etc.). Use to "
                "discover what categories are available before querying."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Optional category to filter sources by."},
                    "limit": {"type": "integer", "description": "Max sources to return. Default 20."},
                },
                "required": [],
            },
            permission="world_monitor.read",
            handler=world_monitor_get_sources,
            category="world",
        ),
        Tool(
            name="world_monitor.world_brief",
            description=(
                "Return a global snapshot of what is happening in the world right "
                "now: major events across conflicts, disasters, markets, and "
                "infrastructure. Use for open-ended 'what is happening globally'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Optional region focus."},
                    "limit": {"type": "integer", "description": "Max items to return. Default 15."},
                },
                "required": [],
            },
            permission="world_monitor.read",
            handler=world_monitor_world_brief,
            category="world",
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
