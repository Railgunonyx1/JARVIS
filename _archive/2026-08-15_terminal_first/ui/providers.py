"""Pure data-shape helpers for the TUI (no Textual / daemon imports).

Kept import-light so the provider mapping can be unit-tested without
dragging in the UI stack. The daemon already exposes per-provider health
via its ``models`` status action (router.status); these helpers translate
that into the rows the dashboard tables render.
"""

__all__ = ["provider_rows", "DEFAULT_PROVIDER_ROWS", "MOCK_PROVIDERS"]

from __future__ import annotations

# Honest fallback rows: this repo's actual providers, clearly marked mock.
from core.config import ModelCatalog

MOCK_PROVIDERS: list[tuple[str, str, str, str, str]] = [
    ("GROQ", "ONLINE", "-", "-", ModelCatalog.GROQ_LLAMA3_1),
    ("GEMINI", "ONLINE", "-", "-", ModelCatalog.GEMINI_FLASH_20),
    ("OPENROUTER", "OFFLINE", "-", "-", "-"),
    ("OPENCODE_ZEN", "OFFLINE", "-", "-", "-"),
    ("OLLAMA", "OFFLINE", "-", "-", "qwen2.5:1.5b"),
]  # MOCK — real rows come from the daemon's router status
# ── Verified: all 3 provider rate-limit fixes already patched in upstream providers ──

# Placeholder rows; the daemon does not expose a task list yet.
MOCK_TASKS: list[tuple[str, str, str, int, str]] = [
    ("-", "Provider health check", "IDLE", 0, "-"),
    ("-", "Memory consolidation", "IDLE", 0, "-"),
    ("-", "Document index", "IDLE", 0, "-"),
]  # MOCK — no task endpoint on the daemon yet (roadmap follow-up)

# Placeholder agent plan; the daemon has no plan endpoint yet.
MOCK_PLAN: list[tuple[str, str, str]] = [
    ("1", "Analyze current memory architecture", "DONE"),
    ("2", "Review vector store implementation", "DONE"),
    ("3", "Implement hybrid search layer", "DONE"),
    ("4", "Add keyword fallback", "DONE"),
    ("5", "Update tests", "PENDING"),
    ("6", "Validate performance", "PENDING"),
]  # MOCK — real plans come from the daemon planner

# Placeholder MCP servers; the daemon has no MCP registry endpoint yet.
MOCK_MCP: list[tuple[str, str, str]] = [
    ("filesystem", "v1.2.0", "ONLINE"),
    ("github", "v1.4.1", "ONLINE"),
    ("browser", "v1.1.3", "ONLINE"),
    ("database", "v1.0.8", "ONLINE"),
]  # MOCK — real status comes from the daemon MCP registry

# Offline fallback for the skill-registry panel; mirrors real manifests so
# mock rows behave like live registry records. Fields match the daemon's
# SkillRecord.to_dict() shape: name/version/description/capabilities/
# permissions/supported_modes/entry_point/max_risk/unknown_capabilities.
MOCK_SKILL_RECORDS: list[dict[str, object]] = [
    {
        "name": "Agent Dispatch",
        "version": "1.0.0",
        "description": "Routes requests to the appropriate sub-agent via a shared scratchpad",
        "capabilities": ["ai.llm.query"],
        "permissions": [],
        "supported_modes": ["smart", "agent"],
        "entry_point": "actions.agent_dispatch:agent_dispatch",
        "max_risk": "safe",
        "unknown_capabilities": [],
    },
    {
        "name": "Bash Command",
        "version": "1.0.0",
        "description": "Run bash commands safely",
        "capabilities": ["shell.execute"],
        "permissions": [],
        "supported_modes": ["agent"],
        "entry_point": "actions.bash_command:bash_command",
        "max_risk": "critical",
        "unknown_capabilities": [],
    },
    {
        "name": "File System",
        "version": "1.0.0",
        "description": "Read, write, and manage files and directories",
        "capabilities": ["filesystem.read", "filesystem.list", "filesystem.write",
                         "filesystem.delete", "filesystem.move"],
        "permissions": [],
        "supported_modes": ["smart", "agent"],
        "entry_point": "actions.file_manager:file_manager",
        "max_risk": "critical",
        "unknown_capabilities": [],
    },
    {
        "name": "Memory Manager",
        "version": "1.0.0",
        "description": "Store and recall facts from long-term memory",
        "capabilities": ["memory.recall", "memory.store", "memory.clear"],
        "permissions": [],
        "supported_modes": ["controlled", "smart", "agent"],
        "entry_point": "memory.memory_manager:MemoryManager",
        "max_risk": "low",
        "unknown_capabilities": [],
    },
    {
        "name": "Web Search",
        "version": "1.0.0",
        "description": "Search the web and summarize the top results",
        "capabilities": ["web.search"],
        "permissions": [],
        "supported_modes": ["smart", "agent"],
        "entry_point": "actions.web_search:web_search",
        "max_risk": "safe",
        "unknown_capabilities": [],
    },
    {
        "name": "Window Manager",
        "version": "1.0.0",
        "description": "Manage window positions and states",
        "capabilities": ["window.list", "window.focus", "window.move"],
        "permissions": [],
        "supported_modes": ["controlled", "smart", "agent"],
        "entry_point": "actions.window_manager:window_manager",
        "max_risk": "low",
        "unknown_capabilities": [],
    },
]  # MOCK — real rows come from the daemon skill registry


def provider_rows(router_status: dict) -> list[tuple[str, str, str, str, str]]:
    """Map the daemon's router status dict to provider-table rows.

    ``router_status`` is what the daemon returns for the ``models`` action:
    ``{name: {available, model, package_ok, health: {latency_ms, error_rate,
    consecutive_failures, cooldown_until}}}``. Returns
    ``(name, STATUS, latency, rate, model)`` rows.
    """
    rows: list[tuple[str, str, str, str, str]] = []
    for name in sorted(router_status):
        info = router_status[name] or {}
        health = info.get("health") or {}
        latency_ms = float(health.get("latency_ms", 0.0) or 0.0)
        latency = f"{int(latency_ms)}ms" if latency_ms > 0 else "-"
        error_rate = float(health.get("error_rate", 0.0) or 0.0)
        rate = f"{error_rate * 100:.0f}%" if error_rate > 0 else "-"
        has_package = info.get("package_ok", None)  # None = unknown
        online = bool(info.get("available")) and (
            has_package is True or (has_package is None and info.get("available") is True)
        )
        rows.append((name.upper(), "ONLINE" if online else "OFFLINE",
                     latency, rate, str(info.get("model", "unknown"))))
    return rows


# Default provider rows when daemon router_status is unavailable.
# Mirrors the structure provider_rows() produces so callers can safely
# default to these without type mismatches.
DEFAULT_PROVIDER_ROWS: list[tuple[str, str, str, str, str]] = [
    ("GROQ", "ONLINE", "-", "-", "llama3-8b-8192"),
    ("GEMINI", "ONLINE", "-", "-", "gemini-1.5-flash"),
    ("OPENROUTER", "OFFLINE", "-", "-", "-"),
    ("OPENCODE_ZEN", "OFFLINE", "-", "-", "-"),
    ("OLLAMA", "OFFLINE", "-", "-", "qwen2.5:1.5b"),
]
