"""JARVIS Orbit — runtime seam (the DSH -> tools -> browser vertical slice).

This is the minimal orchestrator that ties a DSH request to the real agent
stack without bypassing anything:

    DSH request  ->  OrbitRuntime.handle_command
                  ->  ToolExecutionService.execute_tool   (single boundary)
                  ->  orbit.* handler -> BrowserController -> CDPBackend -> CDP

It exists so Phase-C3/G3-G4 can be tested end-to-end and the same seam becomes
:class:`jbrowser_bridge.backend.KernelBackend` (G7) when the model gateway is
wired. Security is NOT enforced here: permissions/approval live in the
PermissionEngine owned by the ToolExecutionService.
"""

from __future__ import annotations

from typing import Any

from core.agent.permissions import PermissionEngine
from core.agent.tool_service import ToolExecutionService
from core.decision_logger import get_decision_logger
from orbit.tools import build_orbit_tools
from providers.types import ToolCall
from tools.registry import ToolRegistry


class OrbitRuntime:
    """Executes Orbit browsing commands through the canonical tool boundary."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        permissions: PermissionEngine | None = None,
        service: ToolExecutionService | None = None,
    ) -> None:
        self.registry = registry or self._default_registry()
        if service is not None:
            self.service = service
        else:
            self.service = ToolExecutionService(
                registry=self.registry,
                permissions=permissions or PermissionEngine(
                    get_decision_logger(), mode="agent", fail_closed_risky=True,
                ),
            )

    @staticmethod
    def _default_registry() -> ToolRegistry:
        reg = ToolRegistry()
        reg.register_many(build_orbit_tools())
        return reg

    # ------------------------------------------------------------ commands
    def command_schema(self) -> dict[str, Any]:
        """Describe the DSH command surface (for the bridge/KernelBackend)."""
        return {
            "execution": "Any browsing command executes exactly one orbit.* tool "
                         "through ToolExecutionService.",
            "tools": [t.name for t in self.registry.list()],
            "ownership": "Tabs are owned by the agent that created them; "
                         "concurrent ownership conflicts raise RESOURCE_LOCKED.",
            "network": "Private/loopback/link-local destinations denied by default.",
        }

    async def handle_command(
        self,
        command: dict[str, Any],
        *,
        trace_id: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        """Execute a DSH command against the Orbit browser.

        ``command`` shape (canonical DSH action envelope):
            {"action": "browse" | "browser.*",
             "tool": "<orbit.tool>",
             "arguments": {...}}

        Returns the ToolExecutionResult serialized for the caller, including
        the read-back surface when the tool is navigation/read.
        """
        tool_name = str(command.get("tool") or command.get("action") or "").strip()
        arguments = dict(command.get("arguments") or {})
        if command.get("action") == "cleanup":
            from orbit.controller import reset_orbit_controller
            reset_orbit_controller()
            return {"success": True, "output": "Orbit session cleaned up."}
        if not tool_name:
            return {"success": False, "error": "command missing 'tool' or 'action'"}

        call = ToolCall(name=tool_name, arguments=arguments, id=command.get("id", ""))
        result = await self.service.execute_tool(
            call, trace_id=trace_id, session_id=session_id,
        )
        payload: dict[str, Any] = {
            "success": result.success,
            "tool": result.tool_name,
            "output": result.output,
            "error": result.error or None,
            "duration_ms": result.duration_ms,
            "permission_denied": result.permission_denied,
            "permission_reason": result.permission_reason or None,
            "metadata": result.metadata or {},
        }
        if command.get("action") == "browse":
            # Observation via orbit.read metadata when the tool already
            # produced it. The old path called controller.read() here — a
            # SECOND browser operation outside the ToolExecutionService
            # boundary (bypassed permissions/ownership for every "browse"
            # command). The runtime performs no browser operations itself.
            payload["observation"] = (result.metadata or {}).get("page") or {}
        return payload

    def _readback_removed(self) -> None:
        """Placeholder kept so historical references fail loudly in review.

        The old ``_readback()`` called ``controller.read()`` from the runtime,
        executing a browser operation outside the canonical tool boundary.
        Observation now belongs to ``orbit.read`` (the tool), whose metadata
        is surfaced as ``payload["observation"]``.
        """
