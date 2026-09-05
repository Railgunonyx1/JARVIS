"""Tool metadata classification.

Derives declarative tool metadata (risk, capabilities, timeout, destructive
flag, side effects, retry semantics, concurrency) from a tool's name,
permission, and category, so every registered tool gets consistent, auditable
metadata without editing each registration. Explicit values set on a Tool take
precedence over the derived defaults.

Risk levels follow the capability registry's CapabilityRisk ordering:
    safe < low < medium < high < critical
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from tools.schema import Tool

RISK_ORDER = ("safe", "low", "medium", "high", "critical")

# Permissions that imply write/host effects and drive risk upward.
_DESTRUCTIVE_PERMISSIONS = {
    "filesystem.write", "filesystem.delete",
    "shell.execute", "shell.run",
    "git.write", "process.kill", "process.start",
    "service.stop", "service.restart",
    "package.install", "package.uninstall",
}
_WRITE_SIDE_EFFECTS = {"filesystem.write", "shell.execute", "git.write"}

# Tool namespaces that spawn processes but do NOT destructively mutate the
# repo, so they are non-destructive even though they carry shell.execute
# permission (e.g. running tests, typechecking, scanning).
_NON_DESTRUCTIVE_NAMESPACES = ("test.", "code.", "security.", "search.", "runtime.", "self.")

# name -> bounding risk.
_RISK_OVERRIDES: dict[str, str] = {
    "shell.execute": "critical",
    "filesystem.write": "high",
    "filesystem.delete": "high",
    "git.push": "high",
    "git.reset": "medium",
    "git.rebase": "medium",
}

# Canonical browser action -> risk. This is the SINGLE source of truth for
# browser tools; jbrowser.permissions is a thin adapter over it (see below).
# Browser mutations (click/type/submit/...) are HIGH + destructive so an agent
# cannot silently mutate a page or trigger consequential actions.
_BROWSER_ACTION_RISK: dict[str, str] = {
    # low: observe / navigate / tab & session management
    "open": "low", "navigate": "low", "read": "low", "extract": "low",
    "screenshot": "low", "status": "low", "tabs": "low", "find": "low",
    "scroll": "low", "switch_tab": "low", "new_tab": "low", "close_tab": "low",
    "profile": "low", "permissions": "low",
    # high: consequential / side-effecting / irreversible page actions
    "click": "high", "type": "high", "select": "high", "submit": "high",
    "send": "high", "delete": "high", "purchase": "high",
    "account_change": "high", "execute_script": "high",
}


def browser_risk_for_tool(name: str) -> str:
    """Map a ``browser.<verb>`` / ``orbit.<verb>`` tool to canonical risk.

    ``_BROWSER_ACTION_RISK`` remains the single source of truth for browser
    actions; the ``orbit.`` product namespace routes through it identically.
    """
    for prefix in ("browser.", "orbit."):
        if name.startswith(prefix):
            verb = name[len(prefix):]
            break
    else:
        verb = name
    verb = verb.replace(".", "_")
    action = next(
        (k for k in _BROWSER_ACTION_RISK if verb == k or verb.endswith("_" + k)),
        verb,
    )
    return _BROWSER_ACTION_RISK.get(action, "low")

_TIMEOUT_OVERRIDES: dict[str, float] = {
    "shell.execute": 120.0,
    "test.run": 300.0,
    "test.run_target": 180.0,
    "test.coverage": 300.0,
    "test.benchmark": 300.0,
    "security.scan_code": 180.0,
    "security.scan_secrets": 180.0,
    "code.typecheck": 120.0,
    "world_monitor.search": 30.0,
    "browser.open": 60.0,
    "browser.navigate": 60.0,
    "orbit.navigate": 60.0,
    "web.search": 30.0,
}

_CAPABILITY_OVERRIDES: dict[str, tuple[str, ...]] = {
    "filesystem.write": ("fs_write", "code_edit"),
    "filesystem.delete": ("fs_write", "fs_delete"),
    "filesystem.read": ("fs_read", "code_browsing"),
    "filesystem.list": ("fs_read", "code_browsing"),
    "filesystem.tree": ("fs_read",),
    "filesystem.copy": ("fs_write",),
    "filesystem.move": ("fs_write",),
    "filesystem.diff": ("fs_read",),
    "shell.execute": ("shell", "host"),
    "system.status": ("system_query",),
    "web.search": ("web", "research"),
    "browser.open": ("web", "research"),
    "search.code": ("code_browsing", "code_search"),
    "search.find": ("code_browsing",),
    "git.status": ("code_browsing",),
    "git.diff": ("code_browsing",),
    "git.log": ("code_browsing",),
    "git.branch": ("code_browsing",),
    "git.blame": ("code_browsing",),
}


def classify_tool(tool: Tool) -> Tool:
    """Return a copy of ``tool`` with derived metadata where not already set.

    Only fills fields whose current value looks like an unset default
    (``safe``/empty/60.0/False). Explicitly-set metadata is preserved.
    """
    updates: dict[str, Any] = {}

    name = tool.name
    permission = tool.permission
    category = tool.category

    if tool.risk == "safe":
        updates["risk"] = _derive_risk(name, permission, category)
    if not tool.capabilities:
        updates["capabilities"] = _derive_capabilities(name, category)
    if tool.timeout_seconds == 60.0:
        updates["timeout_seconds"] = _TIMEOUT_OVERRIDES.get(name, 60.0)
    if not tool.side_effects:
        updates["side_effects"] = _side_effects_for(name, permission)
    if not tool.is_destructive:
        updates["is_destructive"] = _derive_destructive(
            risk=updates.get("risk", tool.risk),
            name=name,
        )
    if tool.retry_semantics == "non_idempotent":
        derived = _retry_semantics_for(name, category)
        if derived != "non_idempotent":
            updates["retry_semantics"] = derived
    if tool.concurrency == "parallel":
        derived = _concurrency_for(name, category)
        if derived != "parallel":
            updates["concurrency"] = derived

    return replace(tool, **updates)


def _derive_risk(name: str, permission: str, category: str) -> str:
    explicit = _RISK_OVERRIDES.get(name)
    if explicit:
        return explicit
    if permission in _DESTRUCTIVE_PERMISSIONS:
        if name.startswith(_NON_DESTRUCTIVE_NAMESPACES):
            return "low"
        return "high"
    if permission.startswith(("filesystem.write", "shell", "git.write")):
        return "medium"
    if category in ("browser", "orbit") and name.startswith(("browser.", "orbit.")):
        return browser_risk_for_tool(name)
    if category in ("testing", "runtime", "memory", "web", "world", "search", "security", "code"):
        return "low"
    return "safe"


def _derive_capabilities(name: str, category: str) -> tuple[str, ...]:
    return _CAPABILITY_OVERRIDES.get(name) or ((category,) if category else ())


def _derive_destructive(risk: str, name: str) -> bool:
    if name.startswith(_NON_DESTRUCTIVE_NAMESPACES):
        return False
    return risk in ("high", "critical")


def _side_effects_for(name: str, permission: str) -> tuple[str, ...]:
    effects = []
    if permission in _WRITE_SIDE_EFFECTS:
        effects.append("fs_write")
    if permission in ("shell.execute", "shell.run"):
        effects.append("process_spawn")
    if name.startswith("web.") or name.startswith("browser.") or name.startswith("orbit."):
        effects.append("network_egress")
    if name.startswith("git."):
        effects.append("git_mutation")
    return tuple(effects)


def risk_level(risk: str) -> int:
    """Ordinal of a risk level (higher = riskier). Unknown maps to 0."""
    try:
        return RISK_ORDER.index(risk)
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Retry semantics + concurrency (G5): declarative hints for the harness.
#
# retry_semantics -- how a failed/recovered run may safely re-invoke a tool:
#   READ         re-run is free of side effects and returns the same view
#   IDEMPOTENT   re-run converges to the same outcome
#   CONDITIONALLY retryable but the result depends on intervening state/network
#   NON          re-running changes state again (never auto-retry)
# concurrency   -- "parallel" (safe to run concurrently) vs "serialized"
#   (writes on the same resource must not overlap). Actual serialization of
#   shared resources comes from the ownership registry (ResourceLock /
#   RESOURCE_LOCKED); this is the declarative scheduler hint.
# ---------------------------------------------------------------------------

_READ_VERBS = {
    "read", "extract", "status", "tabs", "list", "list_tabs", "find",
    "permissions", "profile", "search",
}
_IDEMPOTENT_VERBS = {"close_tab", "switch_tab", "activate_tab", "activate"}
_CONDITIONAL_VERBS = {"open", "navigate", "reload", "scroll", "screenshot", "go"}


def _orbit_verb(name: str) -> str:
    for prefix in ("browser.", "orbit."):
        if name.startswith(prefix):
            verb = name[len(prefix):]
            break
    else:
        verb = name
    return verb.replace(".", "_")


def _retry_semantics_for(name: str, category: str) -> str:
    if name in _RETRY_READS:
        return "READ"
    if category in ("browser", "orbit") and name.startswith(("browser.", "orbit.")):
        verb = _orbit_verb(name)
        if verb in _READ_VERBS or verb.endswith(("_read", "_extract", "_find")):
            return "READ"
        if verb in _IDEMPOTENT_VERBS:
            return "IDEMPOTENT"
        if verb in _CONDITIONAL_VERBS:
            return "CONDITIONALLY"
        return "NON"
    return "non_idempotent"


def _concurrency_for(name: str, category: str) -> str:
    if category in ("browser", "orbit") and name.startswith(("browser.", "orbit.")):
        verb = _orbit_verb(name)
        if verb in _READ_VERBS or verb.endswith(("_read", "_extract", "_find")):
            return "parallel"
        return "serialized"
    return "parallel"


_RETRY_READS = {
    "web.search", "world_monitor.search", "search.code", "search.find",
    "security.scan_code", "security.scan_secrets", "system.status",
}
