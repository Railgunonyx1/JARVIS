"""Adaptive Policy Engine — adjusts access policies based on trust tiers."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

logger = logging.getLogger("jarvis.security.adaptive_policy")

_TIER_HIGH = "high_trust"
_TIER_MEDIUM = "medium"
_TIER_LOW = "low"

_DEFAULT_POLICIES: dict[str, dict] = {
    "shell.execute": {
        _TIER_HIGH: {"allowed": True, "requires_approval": False},
        _TIER_MEDIUM: {"allowed": True, "requires_approval": True},
        _TIER_LOW: {"allowed": False, "requires_approval": False},
    },
    "file.write": {
        _TIER_HIGH: {"allowed": True, "requires_approval": False},
        _TIER_MEDIUM: {"allowed": True, "requires_approval": False},
        _TIER_LOW: {"allowed": True, "requires_approval": True},
    },
    "file.delete": {
        _TIER_HIGH: {"allowed": True, "requires_approval": True},
        _TIER_MEDIUM: {"allowed": False, "requires_approval": False},
        _TIER_LOW: {"allowed": False, "requires_approval": False},
    },
    "network.request": {
        _TIER_HIGH: {"allowed": True, "requires_approval": False},
        _TIER_MEDIUM: {"allowed": True, "requires_approval": False},
        _TIER_LOW: {"allowed": True, "requires_approval": True},
    },
    "config.modify": {
        _TIER_HIGH: {"allowed": True, "requires_approval": True},
        _TIER_MEDIUM: {"allowed": False, "requires_approval": False},
        _TIER_LOW: {"allowed": False, "requires_approval": False},
    },
    "system.reboot": {
        _TIER_HIGH: {"allowed": False, "requires_approval": False},
        _TIER_MEDIUM: {"allowed": False, "requires_approval": False},
        _TIER_LOW: {"allowed": False, "requires_approval": False},
    },
}

_AUDIT_LIMIT = 5000


class AdaptivePolicyEngine:
    """Trust-tiered access control with full audit logging."""

    def __init__(self) -> None:
        self._policies: dict[str, dict] = {
            action: dict(tiers) for action, tiers in _DEFAULT_POLICIES.items()
        }
        self._audit_log: deque = deque(maxlen=_AUDIT_LIMIT)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_access(
        self,
        action: str,
        user_trust: float,
        context: dict | None = None,
    ) -> dict:
        """Decide whether *action* is allowed for a user with *user_trust*.

        Returns dict with ``allowed``, ``confidence``, and ``policy_used``.
        """
        tier = _trust_to_tier(user_trust)

        with self._lock:
            action_policies = self._policies.get(action)
            if action_policies is None:
                # Unknown action — default-deny
                decision = {
                    "allowed": False,
                    "confidence": 0.9,
                    "policy_used": f"default_deny({tier})",
                }
                self.audit_log(action, "denied", "Unknown action — default deny")
                return decision

            tier_policy = action_policies.get(tier)
            if tier_policy is None:
                # No explicit tier rule — deny
                decision = {
                    "allowed": False,
                    "confidence": 0.8,
                    "policy_used": f"no_rule({tier})",
                }
                self.audit_log(action, "denied", f"No rule for tier '{tier}'")
                return decision

        allowed = tier_policy["allowed"]
        requires_approval = tier_policy["requires_approval"]

        # Confidence based on trust distance from tier boundary
        confidence = _confidence_for_trust(user_trust)
        policy_label = f"{tier}/{action}"

        if requires_approval and allowed:
            ctx = context or {}
            user_approved = ctx.get("user_approved", False)
            if not user_approved:
                self.audit_log(action, "pending_approval", f"Requires user approval ({tier})")
                return {
                    "allowed": False,
                    "confidence": confidence,
                    "policy_used": f"{policy_label}(awaiting_approval)",
                }

        status = "allowed" if allowed else "denied"
        reason = f"Tier '{tier}' policy for '{action}'"
        self.audit_log(action, status, reason)

        return {
            "allowed": allowed,
            "confidence": confidence,
            "policy_used": policy_label,
        }

    # ------------------------------------------------------------------
    # Policy management
    # ------------------------------------------------------------------

    def update_policy(self, action: str, rule: str, tier: str) -> None:
        """Update a policy rule for *action* at the given *tier*.

        *rule* must be ``"allow"``, ``"deny"``, ``"allow_requires_approval"``,
        or ``"deny_requires_approval"``.
        """
        allowed_map = {
            "allow": (True, False),
            "deny": (False, False),
            "allow_requires_approval": (True, True),
            "deny_requires_approval": (False, True),
        }
        if rule not in allowed_map:
            raise ValueError(f"Invalid rule '{rule}', expected one of: {list(allowed_map)}")

        if tier not in (_TIER_HIGH, _TIER_MEDIUM, _TIER_LOW):
            raise ValueError(f"Invalid tier '{tier}', expected one of: {_TIER_HIGH}, {_TIER_MEDIUM}, {_TIER_LOW}")

        allowed, requires_approval = allowed_map[rule]
        with self._lock:
            if action not in self._policies:
                self._policies[action] = {}
            self._policies[action][tier] = {
                "allowed": allowed,
                "requires_approval": requires_approval,
            }
        logger.info(
            "Policy updated: action='%s' tier='%s' -> allowed=%s, approval=%s",
            action,
            tier,
            allowed,
            requires_approval,
        )

    def get_active_policies(self) -> dict[str, dict]:
        """Return a snapshot of all current policies."""
        with self._lock:
            return {
                action: {t: dict(p) for t, p in tiers.items()}
                for action, tiers in self._policies.items()
            }

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def audit_log(self, action: str, decision: str, reason: str) -> None:
        """Append an entry to the audit trail."""
        entry = {
            "timestamp": time.perf_counter(),
            "action": action,
            "decision": decision,
            "reason": reason,
        }
        with self._lock:
            self._audit_log.append(entry)

    def get_audit_trail(self, limit: int = 100) -> list:
        """Return the most recent audit entries."""
        with self._lock:
            trail = list(self._audit_log)
        return trail[-limit:]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trust_to_tier(trust: float) -> str:
    if trust > 0.8:
        return _TIER_HIGH
    if trust >= 0.5:
        return _TIER_MEDIUM
    return _TIER_LOW


def _confidence_for_trust(trust: float) -> float:
    """Higher confidence when trust is far from tier boundaries."""
    distances = [abs(trust - 0.8), abs(trust - 0.5), abs(trust - 0.0)]
    min_dist = min(distances)
    return round(min(0.5 + min_dist, 0.99), 4)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: AdaptivePolicyEngine | None = None
_instance_lock = threading.Lock()


def get_adaptive_policy() -> AdaptivePolicyEngine:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = AdaptivePolicyEngine()
    return _instance
