"""PermissionEngine — unskippable permission gate for the agent runtime.

Flow: ToolRequest → ModeManager (mode config) → SecurityEngine (policy +
confirmation) → execute. Every check is recorded as a permission.checked
event so the trace is auditable end-to-end.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core import events
from core.decision_logger import DecisionLogger
from core.mode_manager import ExecutionMode, get_mode_manager
from security.engine import get_security_engine
from tools.schema import Tool

_CONFIRMABLE_SECURITY_MODE = {"plan": "controlled", "controlled": "controlled",
                              "smart": "smart", "agent": "agent"}


class PermissionEngine:
    """Bridges mode configuration and the security engine for tool calls."""

    def __init__(
        self,
        decision_logger: DecisionLogger,
        mode: str = ExecutionMode.AGENT,
        confirmation_handler: Callable[[str, dict[str, Any]], str] | None = None,
    ) -> None:
        self.logger = decision_logger
        self.mode_manager = get_mode_manager()
        self.mode = self._resolve_mode(mode)
        self.security = get_security_engine()
        self.security.set_mode(_CONFIRMABLE_SECURITY_MODE[self.mode])
        self.confirmation_handler = confirmation_handler
        if confirmation_handler:
            self.security.set_confirmation_handler(confirmation_handler)

    @staticmethod
    def _resolve_mode(mode: str) -> ExecutionMode:
        try:
            resolved = ExecutionMode(mode)
        except ValueError:
            resolved = ExecutionMode.AGENT
        if resolved not in (ExecutionMode.PLAN, ExecutionMode.CONTROLLED,
                            ExecutionMode.SMART, ExecutionMode.AGENT):
            resolved = ExecutionMode.AGENT
        return resolved

    def set_mode(self, mode: str) -> bool:
        self.mode = self._resolve_mode(mode)
        self.security.set_mode(_CONFIRMABLE_SECURITY_MODE[self.mode])
        return True

    @staticmethod
    def _is_risky(tool: Tool) -> bool:
        """A tool is risk-gated when its classifier flags it destructive or
        high/critical risk.
        """
        if bool(getattr(tool, "is_destructive", False)):
            return True
        return getattr(tool, "risk", "safe") in ("high", "critical")

    def _apply_risk_gate(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        trace_id: str,
        session_id: str,
    ) -> tuple[bool, str]:
        """Opt-in confirmation gate for risky destructive tools.

        Only activates when a confirmation handler is wired AND the tool is
        classified destructive/high-risk AND its permission is not already
        confirmation-gated by the current mode config. With no handler wired
        this is a no-op (returns allowed), so default agent autonomy is
        preserved. Commands the SAME decision vocabulary as the security
        engine: once/run = allow, deny = deny.
        """
        if self.confirmation_handler is None:
            return True, ""
        if not self._is_risky(tool):
            return True, ""
        if self.mode_manager.requires_confirmation(tool.permission, self.mode):
            return True, ""

        decision = self.confirmation_handler(tool.name, arguments)
        if decision not in ("once", "run", "deny"):
            decision = "deny"
        if decision == "deny":
            reason = f"User denied confirmation for risky tool '{tool.name}'"
            self.logger.record(trace_id, events.PERMISSION_CHECKED, {
                "tool": tool.name, "allowed": False, "reason": reason,
                "risk": getattr(tool, "risk", "safe"),
                "is_destructive": bool(getattr(tool, "is_destructive", False)),
                "gate": "risk",
            })
            return False, reason
        return True, ""

    async def check(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        trace_id: str,
        session_id: str = "",
    ) -> tuple[bool, str]:
        """Check whether a tool call is permitted.

        Returns (allowed, reason). Never skips the checks — even in agent mode
        the mode config and security policy are always evaluated.
        """
        if not self.mode_manager.is_allowed(tool.permission, self.mode):
            reason = f"Tool '{tool.name}' is not allowed in {self.mode} mode"
            self.logger.record(trace_id, events.PERMISSION_CHECKED, {
                "tool": tool.name, "allowed": False, "reason": reason,
                "risk": getattr(tool, "risk", "safe"),
                "is_destructive": bool(getattr(tool, "is_destructive", False)),
            })
            return False, reason

        risk_allowed, risk_reason = self._apply_risk_gate(tool, arguments, trace_id, session_id)
        if not risk_allowed:
            return False, risk_reason

        allowed, reason = self.security.check_permission(
            tool.permission, session_id=session_id, params=arguments,
        )
        self.logger.record(trace_id, events.PERMISSION_CHECKED, {
            "tool": tool.name, "allowed": allowed, "reason": reason or "",
            "risk": getattr(tool, "risk", "safe"),
            "is_destructive": bool(getattr(tool, "is_destructive", False)),
        })
        return allowed, reason
