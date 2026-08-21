"""JARVIS MK-X tool catalog.

Builds the default tool registry used by the agent runtime. Execution
wrappers live in core/agent/tools.py; individual tool handlers in tools/*.
"""

from __future__ import annotations

from tools.registry import ToolRegistry
from tools.schema import Tool, ToolResult, tool_result


def build_default_registry() -> ToolRegistry:
    """Register the core M0 tool set (filesystem + shell) plus world monitor."""
    from tools.browser import (
        browser_click,
        browser_extract,
        browser_open,
        browser_screenshot,
        browser_status,
        browser_type,
    )
    from tools.filesystem import filesystem_list, filesystem_read, filesystem_write
    from tools.git_tools import (
        git_add,
        git_branch,
        git_commit,
        git_diff,
        git_log,
        git_restore,
        git_status,
    )
    from tools.memory_tools import memory_forget, memory_remember, memory_retrieve, memory_stats
    from tools.patch import patch_delete, patch_insert, patch_replace
    from tools.search import code_search, file_find
    from tools.shell import shell_execute
    from tools.system_monitor import system_status
    from tools.web_search import web_search
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
                    "overwrite": {"type": "boolean", "description": "Allow overwriting existing file. Default true."},
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
                    "executable": {"type": "string", "description": "Executable path or name. Preferred over command."},
                    "args": {
                        "oneOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "string"},
                        ],
                        "description": "Argument list (structured, no shell). May be a list or a stringified list.",
                    },
                    "command": {"type": "string", "description": "A shell command string. Chaining blocked."},
                    "shell": {"type": "string", "enum": ["powershell", "cmd"], "description": "Shell host."},
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
            name="system.status",
            description=(
                "Report read-only host health: CPU load, RAM usage, uptime, "
                "process count, and (when available) CPU temperature and GPU "
                "load. Use for system monitoring questions."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            permission="system.query",
            handler=system_status,
            category="system",
        ),
        Tool(
            name="web.search",
            description=(
                "Search the web for a query and return ranked results (title, "
                "snippet, URL). Set mode='news' for recent news coverage. "
                "Uses Google ground-truth search when GEMINI_API_KEY is set, "
                "otherwise DuckDuckGo. Use for current-events research and "
                "fact lookup."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "mode": {
                        "type": "string", "enum": ["search", "news"],
                        "description": "Search type. Default 'search'.",
                    },
                    "limit": {"type": "integer", "description": "Max results. Default 6."},
                },
                "required": ["query"],
            },
            permission="web.search",
            handler=web_search,
            category="web",
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
                    "category": {"type": "string", "description": "Category filter (geopolitics, finance...)."},
                    "limit": {"type": "integer", "description": "Max results to return. Default 10."},
                },
                "required": ["query"],
            },
            permission="world_monitor.read",
            handler=world_monitor_search,
            category="world",
        ),
        Tool(
            name="browser.open",
            description=(
                "Open a URL and return the page title, visible text, and links. "
                "Uses a full Playwright browser when available (handles JavaScript "
                "heavy pages) and falls back to HTTP scraping otherwise. Use for "
                "web research and reading pages."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL (http(s)://) or bare domain."},
                },
                "required": ["url"],
            },
            permission="browser.open",
            handler=browser_open,
            category="browser",
        ),
        Tool(
            name="browser.screenshot",
            description=(
                "Take a screenshot of the current browser page and save it to disk. "
                "Returns the file path. Requires Playwright + chromium."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional output path (defaults to temp dir)."},
                },
                "required": [],
            },
            permission="browser.screenshot",
            handler=browser_screenshot,
            category="browser",
        ),
        Tool(
            name="browser.click",
            description=(
                "Click the first element matching a CSS selector on the current page. "
                "Requires Playwright. Useful after browser.open for interactive pages."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector."},
                },
                "required": ["selector"],
            },
            permission="browser.act",
            handler=browser_click,
            category="browser",
        ),
        Tool(
            name="browser.type",
            description=(
                "Fill a text input matching a CSS selector on the current page. "
                "Requires Playwright."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the input."},
                    "text": {"type": "string", "description": "Text to type."},
                },
                "required": ["selector", "text"],
            },
            permission="browser.act",
            handler=browser_type,
            category="browser",
        ),
        Tool(
            name="browser.extract",
            description=(
                "Extract visible text from the current page, or a specific element "
                "by CSS selector. Requires Playwright."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Optional CSS selector."},
                },
                "required": [],
            },
            permission="browser.read",
            handler=browser_extract,
            category="browser",
        ),
        Tool(
            name="browser.status",
            description=(
                "Report whether the full Playwright browser backend is available "
                "or JARVIS is falling back to HTTP scraping."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            permission="browser.read",
            handler=browser_status,
            category="browser",
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
                    "event_type": {"type": "string", "description": "Event type (conflict, disaster, cyber...)."},
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
        # ── Search ──────────────────────────────────────────────
        Tool(
            name="search.code",
            description=(
                "Search file contents using regex across the repository. "
                "Returns file:line matches. Use for finding code, references, "
                "definitions, and patterns."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for."},
                    "path": {"type": "string", "description": "Subdirectory to restrict search."},
                    "include": {"type": "string", "description": "File glob filter (e.g. *.py)."},
                    "max_results": {"type": "integer", "description": "Cap on results. Default 200."},
                },
                "required": ["pattern"],
            },
            permission="filesystem.read",
            handler=code_search,
            category="search",
        ),
        Tool(
            name="search.find",
            description="Find files by name pattern (glob) across the repository.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g. *.py, **/test_*.py)."},
                    "path": {"type": "string", "description": "Subdirectory to search in."},
                },
                "required": ["pattern"],
            },
            permission="filesystem.read",
            handler=file_find,
            category="search",
        ),
        # ── Git ─────────────────────────────────────────────────
        Tool(
            name="git.status",
            description="Show the working tree status (short format).",
            parameters={"type": "object", "properties": {}, "required": []},
            permission="filesystem.read",
            handler=git_status,
            category="git",
        ),
        Tool(
            name="git.diff",
            description="Show changes in the working tree or staged changes.",
            parameters={
                "type": "object",
                "properties": {
                    "staged": {"type": "boolean", "description": "Show staged changes. Default false."},
                    "path": {"type": "string", "description": "Restrict to a specific file."},
                },
                "required": [],
            },
            permission="filesystem.read",
            handler=git_diff,
            category="git",
        ),
        Tool(
            name="git.log",
            description="Show recent commit history.",
            parameters={
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Number of commits. Default 10."},
                    "path": {"type": "string", "description": "Restrict to a specific file."},
                },
                "required": [],
            },
            permission="filesystem.read",
            handler=git_log,
            category="git",
        ),
        Tool(
            name="git.branch",
            description="Show the current branch name.",
            parameters={"type": "object", "properties": {}, "required": []},
            permission="filesystem.read",
            handler=git_branch,
            category="git",
        ),
        Tool(
            name="git.add",
            description="Stage files for commit.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File or directory to stage. Use . for all."},
                },
                "required": ["path"],
            },
            permission="filesystem.write",
            handler=git_add,
            category="git",
        ),
        Tool(
            name="git.commit",
            description="Create a commit with staged changes.",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message."},
                },
                "required": ["message"],
            },
            permission="filesystem.write",
            handler=git_commit,
            category="git",
        ),
        Tool(
            name="git.restore",
            description="Discard changes in working tree for a file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to restore. Use . for all."},
                    "staged": {"type": "boolean", "description": "Also unstage. Default false."},
                },
                "required": ["path"],
            },
            permission="filesystem.write",
            handler=git_restore,
            category="git",
        ),
        # ── Patch editing ───────────────────────────────────────
        Tool(
            name="patch.replace",
            description=(
                "Replace exact text in a file. The old text must match uniquely "
                "(or use all=true for multiple). Preferred over full-file overwrite."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to edit."},
                    "old": {"type": "string", "description": "Exact text to find."},
                    "new": {"type": "string", "description": "Replacement text."},
                    "all": {"type": "boolean", "description": "Replace all occurrences. Default false."},
                },
                "required": ["path", "old", "new"],
            },
            permission="filesystem.write",
            handler=patch_replace,
            category="patch",
        ),
        Tool(
            name="patch.insert",
            description="Insert text at a specific line number in a file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to edit."},
                    "line": {
                        "type": "integer",
                        "description": "Line number to insert before (1-indexed). 0 = append at end.",
                    },
                    "text": {"type": "string", "description": "Text to insert."},
                },
                "required": ["path", "line", "text"],
            },
            permission="filesystem.write",
            handler=patch_insert,
            category="patch",
        ),
        Tool(
            name="patch.delete",
            description="Delete a range of lines from a file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to edit."},
                    "start": {"type": "integer", "description": "First line to delete (1-indexed, inclusive)."},
                    "end": {"type": "integer", "description": "Last line to delete (inclusive). Defaults to start."},
                },
                "required": ["path", "start"],
            },
            permission="filesystem.write",
            handler=patch_delete,
            category="patch",
        ),
        # ── Memory tools ─────────────────────────────────────────────
        Tool(
            name="memory.retrieve",
            description=(
                "Search across all memory backends (KV, vector, decisions, project knowledge) "
                "and return the most relevant results. Use this to look up previously stored "
                "information, decisions, preferences, or facts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Semantic search query."},
                    "limit": {"type": "integer", "description": "Max results (default 5, max 10)."},
                    "project": {"type": "string", "description": "Filter to a specific project."},
                },
                "required": ["query"],
            },
            permission="memory.retrieve",
            handler=memory_retrieve,
            category="memory",
        ),
        Tool(
            name="memory.remember",
            description=(
                "Store a new memory with a key, value, and category. "
                "Categories: identity, preferences, priorities, notes, projects, decisions. "
                "Use this to remember user information, preferences, or important facts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Memory key (e.g., 'user_name', 'coding_style')."},
                    "value": {"type": "string", "description": "Memory value."},
                    "category": {
                        "type": "string",
                        "description": "Category: identity, preferences, priorities, notes, projects, decisions.",
                        "enum": ["identity", "preferences", "priorities", "notes", "projects", "decisions"],
                    },
                },
                "required": ["key", "value"],
            },
            permission="memory.remember",
            handler=memory_remember,
            category="memory",
        ),
        Tool(
            name="memory.forget",
            description="Delete a memory by key.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key of the memory to delete."},
                },
                "required": ["key"],
            },
            permission="memory.forget",
            handler=memory_forget,
            category="memory",
        ),
        Tool(
            name="memory.stats",
            description="Show memory system statistics (counts, categories).",
            parameters={"type": "object", "properties": {}, "required": []},
            permission="memory.stats",
            handler=memory_stats,
            category="memory",
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
