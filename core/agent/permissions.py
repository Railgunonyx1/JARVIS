"""PermissionEngine — unskippable permission gate for the agent runtime.

Flow: ToolRequest → ModeManager (mode config) → SecurityEngine (policy +
confirmation) → execute. Every check is recorded as a permission.checked
event so the trace is auditable end-to-end.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from core import events
from core.decision_logger import DecisionLogger
from core.mode_manager import ExecutionMode, get_mode_manager
from security.engine import get_security_engine
from security.sensitive_sites import SENSITIVE_SITES
from tools.schema import Tool

_CONFIRMABLE_SECURITY_MODE = {"plan": "controlled", "controlled": "controlled",
                              "smart": "smart", "agent": "agent"}

# Permission matrix: modes in which a destructive/high-risk tool with NO wired
# consent channel must fail closed (denied) rather than proceed. Controlled and
# Smart are consent-first modes (see SECURITY.md); Plan is read-only; Agent is
# the autonomous coding posture. An explicit ``fail_closed_risky`` overrides.
_FAIL_CLOSED_MODES = frozenset({ExecutionMode.CONTROLLED, ExecutionMode.SMART})

# ── Canonical path gate (qwen-code #6923 pattern) ───────────────────────────
# Restrictive checks MUST match the canonical destination (symlinks followed,
# dangling targets resolved, ``..`` normalized), so a denied destination cannot
# be spelled around with a link or traversal. The allow side stays lexical-only
# — this gate only ever denies; canonical equality never grants a permission.
_PATH_KEYS = (
    "path", "file", "file_a", "file_b", "source", "dest", "destination",
    "target", "cwd",
)

# ── MCP trust (two-key, qwen-code pattern) ──────────────────────────────────
# A tool from an external MCP server may only ride its declared low-risk /
# read-only status to auto-approval when BOTH keys are present: the server is
# explicitly trusted (config ``"trusted": true`` or constructor) AND the
# workspace is trusted (JARVIS_TRUST_MCP_WORKSPACE=1 or constructor). One key
# alone degrades to "ask"; with no consent channel wired it fails closed.
_MCP_SOURCE_PREFIX = "mcp:"
_MCP_TRUST_ENV_VAR = "JARVIS_TRUST_MCP_WORKSPACE"
_TRUST_ENV_TRUE = frozenset({"1", "true", "yes", "on"})

# Resolved lazily; tests may set this directly.
_MCP_CONFIG_PATH: Path | None = None


def _project_root() -> Path:
    from core.project import ProjectContext
    return ProjectContext.discover().root_path


def _canonical_destination(raw: str, root: Path) -> Path:
    """Canonical destination of a path argument (restrictive matching)."""
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute():
        path = root / path
    return path.resolve(strict=False)


def _mcp_config_path() -> Path:
    global _MCP_CONFIG_PATH
    if _MCP_CONFIG_PATH is None:
        from core.utils import get_project_root
        _MCP_CONFIG_PATH = get_project_root() / "config" / "mcp_servers.json"
    return _MCP_CONFIG_PATH


def _default_trusted_mcp_servers() -> frozenset[str]:
    """Servers opted in with ``"trusted": true`` in config/mcp_servers.json."""
    try:
        import json
        path = _mcp_config_path()
        if not path.exists():
            return frozenset()
        entries = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return frozenset()
    if not isinstance(entries, list):
        return frozenset()
    return frozenset(
        str(entry.get("name"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("trusted") is True and entry.get("name")
    )


class PermissionEngine:
    """Bridges mode configuration and the security engine for tool calls."""

    def __init__(
        self,
        decision_logger: DecisionLogger,
        mode: str = ExecutionMode.AGENT,
        confirmation_handler: Callable[[str, dict[str, Any]], str] | None = None,
        fail_closed_risky: bool | None = None,
        trusted_mcp_servers: Iterable[str] | None = None,
        trusted_workspace: bool | None = None,
    ) -> None:
        self.logger = decision_logger
        self.mode_manager = get_mode_manager()
        self.mode = self._resolve_mode(mode)
        self.security = get_security_engine()
        self.security.set_mode(_CONFIRMABLE_SECURITY_MODE[self.mode])
        self.confirmation_handler = confirmation_handler
        # Consent matrix (audit Phase 1): in consent-first modes (Controlled,
        # Smart) a destructive/high-risk tool with no wired consent channel is
        # DENIED. Agent mode keeps its autonomous posture; Orbit passes True
        # explicitly. An explicit argument always wins -- including across
        # later set_mode() transitions (see _fail_closed_explicit).
        self._fail_closed_explicit = fail_closed_risky is not None
        if fail_closed_risky is None:
            fail_closed_risky = self.mode in _FAIL_CLOSED_MODES
        self.fail_closed_risky = fail_closed_risky
        if confirmation_handler:
            self.security.set_confirmation_handler(confirmation_handler)
        # MCP trust key 1: explicitly trusted servers (constructor, else the
        # ``"trusted": true`` opt-in in config/mcp_servers.json).
        if trusted_mcp_servers is None:
            trusted_mcp_servers = _default_trusted_mcp_servers()
        self._trusted_mcp_servers = frozenset(str(s) for s in trusted_mcp_servers)
        # MCP trust key 2: trusted workspace (explicit argument wins; else the
        # environment opt-in). Never derived from mode -- consent is
        # mode-independent.
        if trusted_workspace is None:
            env = os.environ.get(_MCP_TRUST_ENV_VAR, "").strip().lower()
            trusted_workspace = env in _TRUST_ENV_TRUE
        self.trusted_workspace = bool(trusted_workspace)

    @staticmethod
    def consent_matrix() -> dict[str, bool]:
        """Documented fail-closed posture per execution mode (no explicit override)."""
        return {
            ExecutionMode.PLAN: False,
            ExecutionMode.CONTROLLED: True,
            ExecutionMode.SMART: True,
            ExecutionMode.AGENT: False,
        }

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
        # Audit fix (P1): the mode-derived default risk posture must follow the
        # mode, or Agent -> Controlled would keep fail_closed_risky=False and
        # silently stop failing closed. An explicit constructor override stays.
        if not self._fail_closed_explicit:
            self.fail_closed_risky = self.mode in _FAIL_CLOSED_MODES
        return True

    @staticmethod
    def _is_risky(tool: Tool) -> bool:
        """A tool is risk-gated when its classifier flags it destructive or
        high/critical risk.
        """
        if bool(getattr(tool, "is_destructive", False)):
            return True
        return getattr(tool, "risk", "safe") in ("high", "critical")

    def _record_denial(self, tool: Tool, trace_id: str, reason: str, gate: str) -> None:
        self.logger.record(trace_id, events.PERMISSION_CHECKED, {
            "tool": tool.name, "allowed": False, "reason": reason,
            "risk": getattr(tool, "risk", "safe"),
            "is_destructive": bool(getattr(tool, "is_destructive", False)),
            "gate": gate,
        })

    def _apply_path_gate(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        trace_id: str,
    ) -> tuple[bool, str]:
        """Restrictive canonical-path gate (qwen-code #6923 pattern).

        Every path-ish argument of a filesystem or MCP-sourced tool is
        canonicalized (symlinks followed, including dangling links and links in
        the nearest existing ancestor; ``..`` normalized; ``~`` expanded) and
        must land inside the project root. Restrictive matching is deliberately
        asymmetric: only the canonical destination is checked for denial, and
        no spelling of a path ever *grants* access — an in-root raw spelling
        whose canonical destination escapes is still denied.

        This is the defense-in-depth layer for tools the boundary-aware
        filesystem handlers do not cover — above all MCP-sourced tools, which
        arrive with foreign path arguments and no in-handler `_resolve`.
        """
        permission = str(getattr(tool, "permission", "") or "")
        source = str(getattr(tool, "source", "") or "")
        if not permission.startswith("filesystem.") and not source.startswith(_MCP_SOURCE_PREFIX):
            return True, ""
        if not isinstance(arguments, dict):
            return True, ""

        root = _project_root().resolve()
        seen: set[str] = set()
        for key in _PATH_KEYS:
            raw = arguments.get(key)
            if not isinstance(raw, str) or not raw.strip() or raw in seen:
                continue
            seen.add(raw)
            if "://" in raw:
                continue
            try:
                canonical = _canonical_destination(raw, root)
            except (OSError, RuntimeError, ValueError):
                reason = (
                    f"Path argument '{key}' for tool '{tool.name}' could not be "
                    "canonicalized — fail closed"
                )
                self._record_denial(tool, trace_id, reason, "path")
                return False, reason
            try:
                canonical.relative_to(root)
            except ValueError:
                reason = (
                    f"Path '{raw}' resolves outside the project root "
                    f"({canonical}) — denied"
                )
                self._record_denial(tool, trace_id, reason, "path")
                return False, reason
        return True, ""

    def _apply_mcp_trust_gate(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        trace_id: str,
    ) -> tuple[bool, str]:
        """Two-key trust gate for MCP-sourced tools (qwen-code pattern).

        A tool from an external MCP server may only ride its declared
        low-risk / read-only status to auto-approval when BOTH keys are
        present: the server is explicitly trusted AND the workspace is
        trusted. Missing either key degrades the call to explicit consent;
        with no consent channel wired it fails closed — independent of mode
        (invariant 9: consent is mode-independent). Destructive/high-risk MCP
        tools are untouched here: they already flow through the risk gate.
        """
        source = str(getattr(tool, "source", "") or "")
        if not source.startswith(_MCP_SOURCE_PREFIX):
            return True, ""
        if self._is_risky(tool):
            return True, ""
        server = source[len(_MCP_SOURCE_PREFIX):] or "unknown"
        if server in self._trusted_mcp_servers and self.trusted_workspace:
            return True, ""

        missing = []
        if server not in self._trusted_mcp_servers:
            missing.append(f"MCP server '{server}' is not trusted")
        if not self.trusted_workspace:
            missing.append(
                f"workspace is not trusted (set {_MCP_TRUST_ENV_VAR}=1 or pass "
                "trusted_workspace=True)"
            )
        base = f"MCP tool '{tool.name}' claimed low-risk, but " + " and ".join(missing)

        handler = self.confirmation_handler
        if handler is None:
            reason = base + " — no consent channel wired (fail closed)"
            self._record_denial(tool, trace_id, reason, "mcp_trust")
            return False, reason

        decision = handler(tool.name, arguments)
        if decision not in ("once", "run", "deny"):
            decision = "deny"
        if decision == "deny":
            reason = f"User denied approval for MCP tool '{tool.name}' ({base.lower()})"
            self._record_denial(tool, trace_id, reason, "mcp_trust")
            return False, reason
        return True, ""

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
        if not self._is_risky(tool):
            return True, ""
        if self.confirmation_handler is None:
            if self.fail_closed_risky:
                reason = (
                    f"Tool '{tool.name}' requires explicit operator approval "
                    "(no consent channel wired — fail closed)"
                )
                self._record_denial(tool, trace_id, reason, "risk")
                return False, reason
            return True, ""
        if self.mode_manager.requires_confirmation(tool.permission, self.mode):
            return True, ""

        decision = self.confirmation_handler(tool.name, arguments)
        if decision not in ("once", "run", "deny"):
            decision = "deny"
        if decision == "deny":
            reason = f"User denied confirmation for risky tool '{tool.name}'"
            self._record_denial(tool, trace_id, reason, "risk")
            return False, reason
        return True, ""

    def _apply_sensitive_site_gate(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        trace_id: str,
    ) -> tuple[bool, str]:
        """Consent gate for navigation to sensitive origins (G5).

        A tool that *opens a destination* (permission ending in ``.open``) to a
        sensitive host always requires explicit operator consent — even when the
        tool itself classifies as low-risk (e.g. plain navigation to a banking /
        webmail / account-console origin). Fail closed: with no consent channel
        wired, or on denial, the navigation is blocked regardless of mode;
        auto-approval (low/medium) never bypasses this gate.
        """
        if not tool.permission.endswith(".open"):
            return True, ""
        url = str(arguments.get("url") or "").strip()
        if not url or not SENSITIVE_SITES.match(url):
            return True, ""

        handler = self.confirmation_handler
        if handler is None:
            reason = (
                f"Navigation to sensitive site requires explicit consent ({url})"
            )
            self._record_denial(tool, trace_id, reason, "sensitive_site")
            return False, reason

        decision = handler(tool.name, arguments)
        if decision not in ("once", "run", "deny"):
            decision = "deny"
        if decision == "deny":
            reason = f"User denied navigation to sensitive site ({url})"
            self._record_denial(tool, trace_id, reason, "sensitive_site")
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

        path_allowed, path_reason = self._apply_path_gate(tool, arguments, trace_id)
        if not path_allowed:
            return False, path_reason

        risk_allowed, risk_reason = self._apply_risk_gate(tool, arguments, trace_id, session_id)
        if not risk_allowed:
            return False, risk_reason

        mcp_allowed, mcp_reason = self._apply_mcp_trust_gate(tool, arguments, trace_id)
        if not mcp_allowed:
            return False, mcp_reason

        sensitive_allowed, sensitive_reason = self._apply_sensitive_site_gate(
            tool, arguments, trace_id,
        )
        if not sensitive_allowed:
            return False, sensitive_reason

        allowed, reason = self.security.check_permission(
            tool.permission, session_id=session_id, params=arguments,
        )
        self.logger.record(trace_id, events.PERMISSION_CHECKED, {
            "tool": tool.name, "allowed": allowed, "reason": reason or "",
            "risk": getattr(tool, "risk", "safe"),
            "is_destructive": bool(getattr(tool, "is_destructive", False)),
        })
        return allowed, reason
