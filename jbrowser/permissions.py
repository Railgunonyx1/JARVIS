"""J-Browser — browser risk permissions (adapter over the canonical model).

Browser actions are classified by the *canonical* risk model in
``tools/classification`` (:data:`_BROWSER_ACTION_RISK` /
:func:`browser_risk_for_tool`). This module is a thin adapter/view only — it
must NOT maintain an independent risk taxonomy. High-risk operations
(submit/send/delete/purchase/account-change/execute_script) require explicit
approval through JARVIS's existing permission/approval system.
"""

from __future__ import annotations

from enum import Enum

from tools.classification import _BROWSER_ACTION_RISK, browser_risk_for_tool

__all__ = [
    "Risk",
    "risk_for_tool",
    "permission_key_for_tool",
    "requires_approval",
    "describe_permissions",
]


class Risk(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_TOOL_PREFIX = "browser."


def risk_for_tool(tool_name: str) -> Risk:
    """Map a browser tool name to its canonical risk tier."""
    return Risk(browser_risk_for_tool(tool_name))


def permission_key_for_tool(tool_name: str) -> str:
    """The permission key a tool should carry (mirrors existing browser.* keys)."""
    risk = risk_for_tool(tool_name)
    return f"{_TOOL_PREFIX}{risk.value}"


def requires_approval(tool_name: str) -> bool:
    """True when the tool is high-risk and must gate on user approval."""
    return risk_for_tool(tool_name) is Risk.HIGH


def describe_permissions() -> dict[str, list[str]]:
    """Summarize which browser tools fall into each tier (for prompts/UI)."""
    result: dict[str, list[str]] = {"low": [], "medium": [], "high": []}
    for tool in _BROWSER_ACTION_RISK:
        result[_BROWSER_ACTION_RISK[tool]].append(f"browser.{tool}")
    return result
