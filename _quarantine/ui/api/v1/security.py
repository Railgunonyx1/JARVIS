"""Security API v1 — permission requests, approval, audit.

Plugins request permission through this API before executing sensitive actions.
"""
import logging
import time
from typing import Any

from api.v1.models import PermissionDecision, PermissionRequest

logger = logging.getLogger("jarvis.api.v1.security")


class SecurityAPI:
    """Stable interface for security and permissions."""

    def __init__(self, security_engine=None, approval_chain=None):
        self._engine = security_engine
        self._approval = approval_chain
        self._audit_log: list[dict[str, Any]] = []
        self._max_audit = 200

    def request_permission(self, req: PermissionRequest) -> PermissionDecision:
        try:
            if self._approval:
                result = self._approval.evaluate(
                    action=req.capability,
                    context={"input": req.user_input, "source": req.source},
                )
                decision = PermissionDecision(
                    approved=result.get("approved", False),
                    reason=result.get("reason", ""),
                )
            elif self._engine:
                result = self._engine.check(capability=req.capability)
                decision = PermissionDecision(
                    approved=result.get("allowed", False),
                    reason=result.get("reason", ""),
                )
            else:
                # No security engine — allow with warning
                decision = PermissionDecision(
                    approved=True,
                    reason="No security engine configured",
                )
        except Exception as e:
            logger.error("SecurityAPI.request_permission failed: %s", e)
            decision = PermissionDecision(
                approved=False,
                reason=f"Security check error: {e}",
            )

        self._audit_log.append({
            "capability": req.capability,
            "source": req.source,
            "trace_id": req.trace_id,
            "approved": decision.approved,
            "reason": decision.reason,
            "timestamp": time.time(),
        })
        if len(self._audit_log) > self._max_audit:
            self._audit_log = self._audit_log[-self._max_audit:]

        return decision

    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._audit_log[-limit:]

    def get_stats(self) -> dict[str, Any]:
        approved = sum(1 for e in self._audit_log if e["approved"])
        denied = len(self._audit_log) - approved
        return {
            "total_requests": len(self._audit_log),
            "approved": approved,
            "denied": denied,
            "approval_rate": round(approved / max(len(self._audit_log), 1) * 100, 1),
        }
