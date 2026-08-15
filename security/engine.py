"""
Security Engine — Central security coordinator for JARVIS MK-X.

Ties together policies, sandbox, and audit logging.
Provides the main API for permission checking and secure execution.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from security.audit import AuditEntry, get_audit_log
from security.executor import ExecRequest, get_secure_executor
from security.policies import (
    PermissionLevel,
    Policy,
    get_policy,
)
from security.sandbox import Sandbox, SandboxConfig, SandboxResult

logger = logging.getLogger("jarvis.security.engine")


class SecurityEngine:
    """Central security coordinator."""

    def __init__(self, mode: str = "smart"):
        self._mode = mode
        self._policy = get_policy(mode)
        self._sandbox = Sandbox(SandboxConfig(
            timeout_seconds=self._policy.timeout_seconds,
        ))
        self._audit = get_audit_log()
        self._lock = threading.Lock()

        # Rate limiting
        self._action_counts: dict[str, list[float]] = {}
        self._rate_window = 60.0  # 1 minute window

        # Confirmation callbacks — return one of "once" | "run" | "deny".
        # The decision is recorded in the audit log (operator-accountable).
        self._confirmation_handler: Callable[[str, dict], str] | None = None

        logger.info("Security engine initialized (mode=%s)", mode)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def policy(self) -> Policy:
        return self._policy

    def set_mode(self, mode: str):
        """Switch security mode (hot-reloadable)."""
        with self._lock:
            self._mode = mode
            self._policy = get_policy(mode)
            self._sandbox = Sandbox(SandboxConfig(
                timeout_seconds=self._policy.timeout_seconds,
            ))
            logger.info("Security mode changed to: %s", mode)

    def set_confirmation_handler(self, handler: Callable[[str, dict], str]):
        """Set a callback for user confirmation prompts.

        The handler receives (tool_name, params) and returns a decision:
        ``"once"``, ``"run"``, or ``"deny"``. ``"once"``/``"run"`` are
        treated as allow; ``"deny"`` blocks the action. The decision is
        recorded in the audit log.
        """
        self._confirmation_handler = handler

    def check_permission(self, tool_name: str, session_id: str = "",
                         params: dict | None = None) -> tuple[bool, str]:
        """Check if an action is permitted.

        Returns: (allowed, reason)
        """
        params = params or {}
        level, rule = self._policy.check_permission(tool_name)

        # Check base permission
        if level == PermissionLevel.DENIED:
            self._log_denied(tool_name, session_id, "Permission denied by policy")
            return False, f"Action '{tool_name}' is denied by policy"

        # Check rate limiting
        if rule and rule.max_frequency > 0:
            if self._is_rate_limited(tool_name, rule.max_frequency):
                self._log_denied(tool_name, session_id, "Rate limited")
                return False, f"Action '{tool_name}' is rate limited (max {rule.max_frequency}/min)"

        # Check confirmation requirement
        if rule and rule.requires_confirmation:
            if self._confirmation_handler:
                decision = self._confirmation_handler(tool_name, params)
                if decision not in ("once", "run", "deny"):
                    logger.warning("confirmation handler returned invalid decision %r", decision)
                    decision = "deny"
                if decision == "deny":
                    self._log_denied(tool_name, session_id, "User denied confirmation")
                    return False, f"Action '{tool_name}' was denied by user"
                # Log confirmed action (once / run both allow)
                self._log_action(tool_name, session_id, level, confirmed=True,
                                 decision=decision)
            else:
                logger.warning("Confirmation required for %s but no handler set", tool_name)

        # Log allowed decisions too — the gate must leave an auditable trail
        # for every call, not just denials and confirmations.
        self._log_allowed(tool_name, session_id, level)

        return True, ""

    def execute_sandboxed(self, command: str, session_id: str = "",
                          cwd: str | None = None,
                          env: dict[str, str] | None = None) -> SandboxResult:
        """Execute a command through the authoritative Secure Executor.

        The executor (security.executor) is the single execution boundary:
        policy classification, structured shell=False runs, governed shell
        scripts, resource limits, and env sanitization all happen there.
        This method adds permission pre-check + audit logging on top.
        """
        start_time = time.time()

        # Pre-check
        allowed, reason = self.check_permission("action.shell.run", session_id)
        if not allowed:
            return SandboxResult(success=False, blocked=True, block_reason=reason)

        # Execute
        req = ExecRequest(command=command, cwd=cwd, env=env,
                          timeout=self._policy.timeout_seconds)
        result = get_secure_executor().execute(req)
        duration_ms = (time.time() - start_time) * 1000

        # Audit
        entry = AuditEntry(
            session_id=session_id,
            action="shell_execute",
            tool="action.shell.run",
            permission_level=PermissionLevel.ELEVATED,
            allowed=not result.blocked,
            duration_ms=duration_ms,
            success=result.success,
            error=result.stderr if not result.success else None,
        )
        self._audit.log(entry)

        return SandboxResult(
            success=result.success,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            duration_ms=duration_ms,
            timed_out=result.timed_out,
            blocked=result.blocked,
            block_reason=result.reason,
        )

    def validate_action(self, tool_name: str, session_id: str = "",
                        mode: str = "") -> tuple[bool, str, dict[str, Any]]:
        """Full validation: permission + sandbox + audit.

        Returns: (allowed, reason, metadata)
        """
        metadata = {
            "tool": tool_name,
            "mode": mode or self._mode,
            "timestamp": time.time(),
        }

        allowed, reason = self.check_permission(tool_name, session_id)
        metadata["allowed"] = allowed
        metadata["reason"] = reason

        if not allowed:
            entry = AuditEntry(
                session_id=session_id,
                action="validate_denied",
                tool=tool_name,
                allowed=False,
                mode=mode or self._mode,
            )
            self._audit.log(entry)

        return allowed, reason, metadata

    def _is_rate_limited(self, tool_name: str, max_freq: int) -> bool:
        """Check if an action exceeds its rate limit."""
        now = time.time()
        cutoff = now - self._rate_window

        with self._lock:
            if tool_name not in self._action_counts:
                self._action_counts[tool_name] = []

            # Prune old entries
            self._action_counts[tool_name] = [
                t for t in self._action_counts[tool_name] if t > cutoff
            ]

            if len(self._action_counts[tool_name]) >= max_freq:
                return True

            self._action_counts[tool_name].append(now)
            return False

    def _log_denied(self, tool: str, session_id: str, reason: str):
        entry = AuditEntry(
            session_id=session_id,
            action="denied",
            tool=tool,
            allowed=False,
            error=reason,
            mode=self._mode,
        )
        self._audit.log(entry)

    def _log_action(self, tool: str, session_id: str, level: PermissionLevel,
                    confirmed: bool = False, decision: str = ""):
        entry = AuditEntry(
            session_id=session_id,
            action="confirmed",
            tool=tool,
            permission_level=level,
            allowed=True,
            confirmed=confirmed,
            mode=self._mode,
            decision=decision,
        )
        self._audit.log(entry)

    def _log_allowed(self, tool: str, session_id: str,
                     level: PermissionLevel):
        entry = AuditEntry(
            session_id=session_id,
            action="allowed",
            tool=tool,
            permission_level=level,
            allowed=True,
            mode=self._mode,
        )
        self._audit.log(entry)

    def get_audit_stats(self, since: float | None = None) -> dict[str, Any]:
        return self._audit.get_stats(since)

    def get_status(self) -> dict[str, Any]:
        return {
            "mode": self._mode,
            "policy": self._policy.to_dict(),
            "sandbox": self._sandbox.get_status(),
            "audit_stats": self._audit.get_stats(time.time() - 3600),
        }

    def shutdown(self):
        self._sandbox.kill_all()
        self._audit.flush()
        self._audit.close()
        logger.info("Security engine shutdown")


# Global singleton
_engine: SecurityEngine | None = None
_engine_lock = threading.Lock()


def get_security_engine() -> SecurityEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = SecurityEngine()
    return _engine
