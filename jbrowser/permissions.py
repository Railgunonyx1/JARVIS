"""J-Browser — browser risk permissions.

Browser actions are classified into risk tiers. High-risk operations
(submit/send/delete/purchase/account-change/execute_script) require explicit
approval — the same human-in-the-loop model Strawberry describes, wired to
JARVIS's existing permission/approval system.

Mapping tier -> permission key used by tools + the permission engine.
"""

from __future__ import annotations

from enum import Enum


class Risk(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Deterministic action -> risk classification.
ACTION_RISK: dict[str, Risk] = {
    # Low: read/navigate/observe
    "open": Risk.LOW,
    "navigate": Risk.LOW,
    "tabs": Risk.LOW,
    "find": Risk.LOW,
    "scroll": Risk.LOW,
    "read": Risk.LOW,
    "extract": Risk.LOW,
    "screenshot": Risk.LOW,
    "profile": Risk.LOW,
    # Medium: modifies current page state
    "click": Risk.MEDIUM,
    "type": Risk.MEDIUM,
    "select": Risk.MEDIUM,
    "download": Risk.MEDIUM,
    # High: consequential / side-effecting / irreversible
    "submit": Risk.HIGH,
    "send": Risk.HIGH,
    "delete": Risk.HIGH,
    "purchase": Risk.HIGH,
    "account_change": Risk.HIGH,
    "execute_script": Risk.HIGH,
}

# Tool-name prefix -> risk. Tools map to an action verb by their final segment
# (browser.open -> "open", browser.submit -> "submit").
_TOOL_PREFIX = "browser."


def risk_for_tool(tool_name: str) -> Risk:
    """Map a browser tool name to its risk tier."""
    verb = tool_name[len(_TOOL_PREFIX):] if tool_name.startswith(_TOOL_PREFIX) else tool_name
    verb = verb.replace(".", "_")
    return ACTION_RISK.get(
        next((k for k in ACTION_RISK if verb == k or verb.endswith("_" + k)), verb),
        Risk.LOW,
    )


def permission_key_for_tool(tool_name: str) -> str:
    """The permission key a tool should carry (mirrors existing browser.* keys)."""
    risk = risk_for_tool(tool_name)
    return f"{_TOOL_PREFIX}{risk.value}"


def requires_approval(tool_name: str) -> bool:
    """True when the tool is high-risk and must gate on user approval."""
    return risk_for_tool(tool_name) is Risk.HIGH


def describe_permissions() -> dict[str, list[str]]:
    """Summarize which browsers tools fall into each tier (for prompts/UI)."""
    result: dict[str, list[str]] = {"low": [], "medium": [], "high": []}
    for tool, risk in ACTION_RISK.items():
        result[risk.value].append(f"browser.{tool}")
    return result
