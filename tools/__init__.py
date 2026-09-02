"""JARVIS MK-X tool catalog.

Builds the default tool registry used by the agent runtime. Execution
wrappers live in core/agent/tools.py; individual tool handlers in tools/*.
"""

from __future__ import annotations

from tools.classification import classify_tool
from tools.registry import ToolRegistry
from tools.schema import Tool, ToolResult, tool_result


def build_default_registry() -> ToolRegistry:
    """Register the core M0 tool set (filesystem + shell) plus world monitor."""
    from tools.audit import run_audit, run_pytest
    from tools.browser import (
        browser_click,
        browser_extract,
        browser_open,
        browser_screenshot,
        browser_status,
        browser_type,
    )
    from tools.code_intelligence import (
        code_ast,
        code_callees,
        code_callers,
        code_definition,
        code_imports,
        code_references,
        code_symbol,
        code_typecheck,
    )
    from tools.filesystem import (
        filesystem_copy,
        filesystem_delete,
        filesystem_diff,
        filesystem_list,
        filesystem_move,
        filesystem_read,
        filesystem_tree,
        filesystem_write,
    )
    from tools.git_tools import (
        git_add,
        git_blame,
        git_branch,
        git_cherry_pick,
        git_commit,
        git_create_branch,
        git_diff,
        git_fetch,
        git_log,
        git_merge,
        git_pull,
        git_push,
        git_rebase,
        git_reset,
        git_restore,
        git_revert,
        git_show,
        git_stash,
        git_status,
        git_tag,
        git_worktree,
    )
    from tools.memory_tools import memory_forget, memory_remember, memory_retrieve, memory_stats
    from tools.patch import patch_delete, patch_insert, patch_replace
    from tools.runtime_tools import (
        runtime_errors,
        runtime_events,
        runtime_latency,
        runtime_models,
        runtime_status,
    )
    from tools.search import code_search, file_find
    from tools.security import (
        security_check_permissions,
        security_scan_code,
        security_scan_secrets,
    )
    from tools.shell import shell_execute
    from tools.system_monitor import system_status
    from tools.test_tools import test_benchmark, test_coverage, test_discover, test_failed, test_run, test_run_target
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
    registry.register_many([classify_tool(t) for t in [
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
            name="filesystem.delete",
            description="Delete a file or empty directory. Cannot delete non-empty directories.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File or empty directory to delete."},
                },
                "required": ["path"],
            },
            permission="filesystem.write",
            handler=filesystem_delete,
            category="filesystem",
        ),
        Tool(
            name="filesystem.copy",
            description="Copy a file to a new location (preserves metadata).",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source file path."},
                    "dest": {"type": "string", "description": "Destination path."},
                },
                "required": ["source", "dest"],
            },
            permission="filesystem.write",
            handler=filesystem_copy,
            category="filesystem",
        ),
        Tool(
            name="filesystem.move",
            description="Move or rename a file.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source file path."},
                    "dest": {"type": "string", "description": "Destination path."},
                },
                "required": ["source", "dest"],
            },
            permission="filesystem.write",
            handler=filesystem_move,
            category="filesystem",
        ),
        Tool(
            name="filesystem.diff",
            description="Compare two files line-by-line and show differences.",
            parameters={
                "type": "object",
                "properties": {
                    "file_a": {"type": "string", "description": "First file path."},
                    "file_b": {"type": "string", "description": "Second file path."},
                },
                "required": ["file_a", "file_b"],
            },
            permission="filesystem.read",
            handler=filesystem_diff,
            category="filesystem",
        ),
        Tool(
            name="filesystem.tree",
            description="Show directory tree structure.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path. Default project root."},
                    "max_depth": {"type": "integer", "description": "Max recursion depth. Default 3."},
                    "max_entries": {"type": "integer", "description": "Max entries to show. Default 200."},
                },
                "required": [],
            },
            permission="filesystem.read",
            handler=filesystem_tree,
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
        # ── Git (extended) ──────────────────────────────────────
        Tool(
            name="git.blame",
            description="Show who last modified each line of a file (git blame).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to blame."},
                },
                "required": ["path"],
            },
            permission="filesystem.read",
            handler=git_blame,
            category="git",
        ),
        Tool(
            name="git.create_branch",
            description="Create a new branch and optionally check it out.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Branch name."},
                    "checkout": {"type": "boolean", "description": "Switch to new branch. Default true."},
                },
                "required": ["name"],
            },
            permission="filesystem.write",
            handler=git_create_branch,
            category="git",
        ),
        Tool(
            name="git.stash",
            description="Stash uncommitted changes (save/pop/list/drop).",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "save, pop, list, or drop. Default save."},
                    "message": {"type": "string", "description": "Stash message (save only)."},
                },
                "required": [],
            },
            permission="filesystem.write",
            handler=git_stash,
            category="git",
        ),
        Tool(
            name="git.show",
            description="Show a specific commit (hash, branch, or HEAD).",
            parameters={
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "Commit ref. Default HEAD."},
                },
                "required": [],
            },
            permission="filesystem.read",
            handler=git_show,
            category="git",
        ),
        Tool(
            name="git.merge",
            description="Merge a branch into the current branch.",
            parameters={
                "type": "object",
                "properties": {
                    "branch": {"type": "string", "description": "Branch to merge."},
                },
                "required": ["branch"],
            },
            permission="filesystem.write",
            handler=git_merge,
            category="git",
        ),
        Tool(
            name="git.rebase",
            description="Rebase current branch onto another branch.",
            parameters={
                "type": "object",
                "properties": {
                    "onto": {"type": "string", "description": "Branch to rebase onto."},
                },
                "required": ["onto"],
            },
            permission="filesystem.write",
            handler=git_rebase,
            category="git",
        ),
        Tool(
            name="git.tag",
            description="Create or list git tags.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "create or list. Default create."},
                    "name": {"type": "string", "description": "Tag name (for create)."},
                    "message": {"type": "string", "description": "Tag message (for create)."},
                },
                "required": [],
            },
            permission="filesystem.write",
            handler=git_tag,
            category="git",
        ),
        Tool(
            name="git.fetch",
            description="Fetch from a remote repository.",
            parameters={
                "type": "object",
                "properties": {
                    "remote": {"type": "string", "description": "Remote name. Default origin."},
                },
                "required": [],
            },
            permission="filesystem.read",
            handler=git_fetch,
            category="git",
        ),
        Tool(
            name="git.pull",
            description="Pull changes from a remote repository.",
            parameters={
                "type": "object",
                "properties": {
                    "remote": {"type": "string", "description": "Remote name."},
                    "branch": {"type": "string", "description": "Branch name."},
                },
                "required": [],
            },
            permission="filesystem.write",
            handler=git_pull,
            category="git",
        ),
        Tool(
            name="git.push",
            description="Push commits to a remote repository.",
            parameters={
                "type": "object",
                "properties": {
                    "remote": {"type": "string", "description": "Remote name."},
                    "branch": {"type": "string", "description": "Branch name."},
                },
                "required": [],
            },
            permission="filesystem.write",
            handler=git_push,
            category="git",
        ),
        Tool(
            name="git.revert",
            description="Revert a commit by creating a new commit that undoes it.",
            parameters={
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "Commit ref to revert."},
                },
                "required": ["ref"],
            },
            permission="filesystem.write",
            handler=git_revert,
            category="git",
        ),
        Tool(
            name="git.cherry_pick",
            description="Cherry-pick a commit from another branch.",
            parameters={
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "Commit ref to cherry-pick."},
                },
                "required": ["ref"],
            },
            permission="filesystem.write",
            handler=git_cherry_pick,
            category="git",
        ),
        Tool(
            name="git.reset",
            description="Reset to a specific commit (soft/mixed/hard).",
            parameters={
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "Commit ref to reset to."},
                    "mode": {"type": "string", "description": "soft, mixed, or hard. Default mixed."},
                },
                "required": ["ref"],
            },
            permission="filesystem.write",
            handler=git_reset,
            category="git",
        ),
        Tool(
            name="git.worktree",
            description="Manage git worktrees (add/list/remove).",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "add, list, or remove."},
                    "path": {"type": "string", "description": "Worktree path (for add/remove)."},
                    "branch": {"type": "string", "description": "Branch name (for add)."},
                },
                "required": ["action"],
            },
            permission="filesystem.write",
            handler=git_worktree,
            category="git",
        ),
        # ── Code intelligence ───────────────────────────────────
        Tool(
            name="code.symbol",
            description="Find symbol definitions (classes, functions, variables) by name.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Symbol name to search for."},
                    "path": {"type": "string", "description": "Directory to search in."},
                },
                "required": ["name"],
            },
            permission="filesystem.read",
            handler=code_symbol,
            category="code",
        ),
        Tool(
            name="code.references",
            description="Find all references/usages of a symbol across the codebase.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Symbol name."},
                    "path": {"type": "string", "description": "Directory to search in."},
                },
                "required": ["name"],
            },
            permission="filesystem.read",
            handler=code_references,
            category="code",
        ),
        Tool(
            name="code.imports",
            description="Show all imports in a Python file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Python file to analyze."},
                },
                "required": ["path"],
            },
            permission="filesystem.read",
            handler=code_imports,
            category="code",
        ),
        Tool(
            name="code.typecheck",
            description="Run Python type checking (mypy or py_compile) on a file or directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File or directory to check."},
                },
                "required": [],
            },
            permission="shell.execute",
            handler=code_typecheck,
            category="code",
        ),
        Tool(
            name="code.definition",
            description="Find where a symbol is defined (class, function, variable).",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Symbol name."},
                    "path": {"type": "string", "description": "Directory to search."},
                },
                "required": ["name"],
            },
            permission="filesystem.read",
            handler=code_definition,
            category="code",
        ),
        Tool(
            name="code.callers",
            description="Find all call sites of a function or method.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Function/method name."},
                    "path": {"type": "string", "description": "Directory to search."},
                },
                "required": ["name"],
            },
            permission="filesystem.read",
            handler=code_callers,
            category="code",
        ),
        Tool(
            name="code.callees",
            description="Find what functions a given function calls (call graph).",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Python file."},
                    "function_name": {"type": "string", "description": "Function to analyze."},
                },
                "required": ["file_path", "function_name"],
            },
            permission="filesystem.read",
            handler=code_callees,
            category="code",
        ),
        Tool(
            name="code.ast",
            description="Parse a Python file and show its AST structure (classes, functions, imports).",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Python file to analyze."},
                },
                "required": ["file_path"],
            },
            permission="filesystem.read",
            handler=code_ast,
            category="code",
        ),
        # ── Test tools ──────────────────────────────────────────
        Tool(
            name="test.discover",
            description="Discover test files and count tests in the project.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to search."},
                    "pattern": {"type": "string", "description": "File glob pattern. Default test_*.py."},
                },
                "required": [],
            },
            permission="filesystem.read",
            handler=test_discover,
            category="testing",
        ),
        Tool(
            name="test.run_target",
            description="Run specific test files or test functions with pytest.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Test file, directory, or specific test."},
                    "args": {"type": "string", "description": "Extra pytest args. Default '-v --tb=short'."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds. Default 120."},
                },
                "required": ["target"],
            },
            permission="shell.execute",
            handler=test_run_target,
            category="testing",
        ),
        Tool(
            name="test.failed",
            description="Show only failed tests from a test run.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Test file or directory."},
                },
                "required": [],
            },
            permission="shell.execute",
            handler=test_failed,
            category="testing",
        ),
        Tool(
            name="test.coverage",
            description="Run tests with coverage reporting.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Test file or directory."},
                    "source": {"type": "string", "description": "Source directory to measure."},
                },
                "required": [],
            },
            permission="shell.execute",
            handler=test_coverage,
            category="testing",
        ),
        Tool(
            name="test.run",
            description="Run the full test suite with optional filtering.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Test path. Default project root."},
                    "markers": {"type": "string", "description": "Pytest marker expression."},
                    "verbose": {"type": "boolean", "description": "Verbose output. Default false."},
                },
                "required": [],
            },
            permission="shell.execute",
            handler=test_run,
            category="testing",
        ),
        Tool(
            name="test.benchmark",
            description="Run test benchmarks or show slowest tests.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Test path. Default project root."},
                },
                "required": [],
            },
            permission="shell.execute",
            handler=test_benchmark,
            category="testing",
        ),
        # ── Runtime diagnostics ─────────────────────────────────
        Tool(
            name="runtime.status",
            description="Report JARVIS runtime health: providers, memory, tools, Ollama.",
            parameters={"type": "object", "properties": {}, "required": []},
            permission="system.query",
            handler=runtime_status,
            category="runtime",
        ),
        Tool(
            name="runtime.latency",
            description="Show model/provider latency metrics and performance data.",
            parameters={"type": "object", "properties": {}, "required": []},
            permission="system.query",
            handler=runtime_latency,
            category="runtime",
        ),
        Tool(
            name="runtime.errors",
            description="Show recent errors from the agent runtime.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max errors to show. Default 20."},
                },
                "required": [],
            },
            permission="system.query",
            handler=runtime_errors,
            category="runtime",
        ),
        Tool(
            name="runtime.events",
            description="Show recent runtime events (BusEvents).",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max events. Default 20."},
                },
                "required": [],
            },
            permission="system.query",
            handler=runtime_events,
            category="runtime",
        ),
        Tool(
            name="runtime.models",
            description="Show loaded Ollama models and residency state.",
            parameters={"type": "object", "properties": {}, "required": []},
            permission="system.query",
            handler=runtime_models,
            category="runtime",
        ),
        # ── Security ────────────────────────────────────────────
        Tool(
            name="security.scan_secrets",
            description="Scan the project for hardcoded secrets and sensitive data.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to scan."},
                },
                "required": [],
            },
            permission="filesystem.read",
            handler=security_scan_secrets,
            category="security",
        ),
        Tool(
            name="security.check_permissions",
            description="Check file permissions and sensitive file exposure.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to check."},
                },
                "required": [],
            },
            permission="filesystem.read",
            handler=security_check_permissions,
            category="security",
        ),
        Tool(
            name="security.scan_code",
            description="Scan Python files for security issues (eval, exec, shell=True, pickle, etc.).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to scan. Default project root."},
                },
                "required": [],
            },
            permission="filesystem.read",
            handler=security_scan_code,
            category="security",
        ),

        # ── Self-audit ──────────────────────────────────────────────
        Tool(
            name="self.audit",
            description="Run read-only JARVIS self-audit checks (security scan + dependency basics). Optionally audit a test path with pytest when 'path' is provided.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional test path/pattern to include a pytest run."},
                },
                "required": [],
            },
            permission="filesystem.read",
            handler=lambda args: tool_result(
                True,
                str(run_audit(str(args.get("path", ".")))),
                error="",
                audit="full",
            ),
            category="audit",
        ),
    ]])
    return registry


__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "tool_result",
    "build_default_registry",
]
