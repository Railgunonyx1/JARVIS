"""Session tools — agent-facing surface for session-scoped state.

``session.undo`` reverses the most recent reversible action the agent took
(filesystem writes/patches this session). Adapted from Mark-LIII: undo is
faster than asking permission, and confirmation is reserved for the
irreversible (handled by PermissionEngine).
"""

from __future__ import annotations

from core.agent import undo
from tools.schema import ToolResult


async def session_undo(params: dict) -> ToolResult:
    """Undo the most recent reversible session action."""
    if params.get("list"):
        hist = undo.history()
        if not hist:
            return ToolResult(success=True, output="No reversible actions this session.")
        lines = "\n".join(f"{i+1}. {h}" for i, h in enumerate(hist[:10]))
        return ToolResult(success=True, output=f"Reversible actions (most recent first):\n{lines}")

    result = undo.undo_last()
    ok = not result.startswith("Could not undo")
    return ToolResult(success=ok, output=result)


__all__ = ["session_undo"]
