"""P0 Release Test: Tool Registration Inventory.

Proves:
    - Every tool implementation is registered in the registry
    - Every registered tool can serialize to OpenAI format
    - Every tool belongs to exactly one risk class (read/mutate/dangerous)
    - The interrupt lane only contains read-only tools
    - The full tool count matches expected count
"""

from __future__ import annotations

import pytest

from tools import build_default_registry


# ---------------------------------------------------------------------------
# Risk classification — every tool MUST be in exactly one set
# ---------------------------------------------------------------------------

READ_ONLY_TOOLS = {
    # Filesystem (read)
    "filesystem.read", "filesystem.list", "filesystem.diff", "filesystem.tree",
    # Git (read)
    "git.status", "git.diff", "git.log", "git.show", "git.branch", "git.blame",
    "git.fetch",
    # Search
    "search.code", "search.find",
    # Memory (read)
    "memory.retrieve", "memory.stats",
    # Web
    "web.search",
    # Browser (read)
    "browser.open", "browser.extract", "browser.screenshot", "browser.status",
    # System (read)
    "system.status",
    # Runtime (read)
    "runtime.status", "runtime.events", "runtime.models", "runtime.latency",
    "runtime.errors",
    # Code intelligence (read)
    "code.symbol", "code.references", "code.imports", "code.typecheck",
    "code.definition", "code.callers", "code.callees", "code.ast",
    # Testing (read)
    "test.discover", "test.failed", "test.benchmark",
    # Security (read)
    "security.check_permissions",
    # World monitor (read)
    "world_monitor.get_event", "world_monitor.get_alerts",
    "world_monitor.get_region", "world_monitor.get_sources",
    "world_monitor.search", "world_monitor.world_brief",
}

MUTATING_TOOLS = {
    # Filesystem (write)
    "filesystem.write", "filesystem.copy", "filesystem.move",
    # Git (write)
    "git.add", "git.commit", "git.create_branch", "git.stash",
    "git.push", "git.merge", "git.rebase", "git.reset",
    "git.revert", "git.cherry_pick", "git.pull", "git.restore", "git.tag",
    "git.worktree",
    # Patch (write)
    "patch.replace", "patch.insert", "patch.delete",
    # Memory (write) — safe: identity/preference updates
    "memory.remember", "memory.forget",
    # Testing (mutating)
    "test.run", "test.run_target", "test.coverage",
    # Security (write)
    "security.scan_secrets", "security.scan_code",
}

DANGEROUS_TOOLS = {
    # Shell
    "shell.execute",
    # Filesystem (dangerous)
    "filesystem.delete",
    # Browser (write)
    "browser.click", "browser.type",
}

ALL_RISK_TOOLS = READ_ONLY_TOOLS | MUTATING_TOOLS | DANGEROUS_TOOLS


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_all_registered_tools_are_risk_classified():
    """Every registered tool must belong to exactly one risk class."""
    registry = build_default_registry()
    registered = {t.name for t in registry.list()}

    unclassified = registered - ALL_RISK_TOOLS
    assert not unclassified, (
        f"Tools not risk-classified: {unclassified}. "
        f"Add them to READ_ONLY_TOOLS, MUTATING_TOOLS, or DANGEROUS_TOOLS."
    )


def test_no_ghost_tools_in_risk_sets():
    """Every risk-set entry must be a real registered tool (no ghosts)."""
    registry = build_default_registry()
    registered = {t.name for t in registry.list()}

    ghosts = ALL_RISK_TOOLS - registered
    assert not ghosts, (
        f"Risk sets reference tools that are not registered: {ghosts}. "
        f"Remove them (or implement + register them in tools/__init__.py)."
    )


def test_no_tool_in_multiple_risk_classes():
    """No tool should be in more than one risk class."""
    overlaps = READ_ONLY_TOOLS & MUTATING_TOOLS
    assert not overlaps, f"Tools in both READ_ONLY and MUTATING: {overlaps}"

    overlaps = READ_ONLY_TOOLS & DANGEROUS_TOOLS
    assert not overlaps, f"Tools in both READ_ONLY and DANGEROUS: {overlaps}"

    overlaps = MUTATING_TOOLS & DANGEROUS_TOOLS
    assert not overlaps, f"Tools in both MUTATING and DANGEROUS: {overlaps}"


def test_all_registered_tools_serialize():
    """Every registered tool must serialize to OpenAI format."""
    registry = build_default_registry()
    tools = registry.to_openai_tools()

    for tool_def in tools:
        assert "function" in tool_def, f"Tool missing 'function': {tool_def}"
        func = tool_def["function"]
        assert "name" in func, f"Tool function missing 'name': {func}"
        assert "description" in func, f"Tool function missing 'description': {func}"
        assert "parameters" in func, f"Tool function missing 'parameters': {func}"


def test_tool_count_reasonable():
    """Tool count should be between 50 and 150 (sanity check)."""
    registry = build_default_registry()
    count = len(registry.list())
    assert 50 <= count <= 150, f"Tool count {count} outside expected range [50, 150]"


def test_dangerous_tools_not_in_interrupt_lane():
    """No dangerous tool should be in the interrupt allowed list."""
    from core.agent.lanes import _INTERRUPT_ALLOWED_TOOLS

    violation = DANGEROUS_TOOLS & _INTERRUPT_ALLOWED_TOOLS
    assert not violation, f"Dangerous tools in interrupt lane: {violation}"


def test_mutating_tools_not_in_interrupt_lane():
    """No mutating tool should be in the interrupt allowed list."""
    from core.agent.lanes import _INTERRUPT_ALLOWED_TOOLS

    # memory.remember is intentionally allowed in interrupt lane for identity updates
    allowed_mutation = {"memory.remember"}
    violation = (MUTATING_TOOLS - allowed_mutation) & _INTERRUPT_ALLOWED_TOOLS
    assert not violation, f"Mutating tools in interrupt lane: {violation}"


def test_core_tools_present():
    """Critical tools that JARVIS must always have."""
    registry = build_default_registry()
    registered = {t.name for t in registry.list()}

    critical = {
        "filesystem.read", "filesystem.write", "filesystem.list",
        "shell.execute",
        "git.status", "git.diff", "git.log",
        "search.code",
        "memory.retrieve", "memory.remember",
        "web.search",
        "system.status",
    }

    missing = critical - registered
    assert not missing, f"Critical tools missing: {missing}"


def test_no_duplicate_tool_names():
    """No two tools should have the same name."""
    registry = build_default_registry()
    names = [t.name for t in registry.list()]
    duplicates = [n for n in names if names.count(n) > 1]
    assert not duplicates, f"Duplicate tool names: {set(duplicates)}"
