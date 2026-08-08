"""PermissionEngine — unskippable permission gate for the agent runtime.

Flow: ToolRequest → ModeManager (mode config) → SecurityEngine (policy +
confirmation) → execute. Every check is recorded as a permission.checked
event so the trace is auditable end-to-end.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

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
        confirmation_handler: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
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

    async def check(
        self,
        tool: Tool,
        arguments: Dict[str, Any],
        trace_id: str,
        session_id: str = "",
    ) -> Tuple[bool, str]:
        """Check whether a tool call is permitted.

        Returns (allowed, reason). Never skips the checks — even in agent mode
        the mode config and security policy are always evaluated.
        """
        if not self.mode_manager.is_allowed(tool.permission, self.mode):
            reason = f"Tool '{tool.name}' is not allowed in {self.mode} mode"
            self.logger.record(trace_id, events.PERMISSION_CHECKED, {
                "tool": tool.name, "allowed": False, "reason": reason,
            })
            return False, reason

        allowed, reason = self.security.check_permission(
            tool.permission, session_id=session_id, params=arguments,
        )
        self.logger.record(trace_id, events.PERMISSION_CHECKED, {
            "tool": tool.name, "allowed": allowed, "reason": reason or "",
        })
        return allowed, reason
