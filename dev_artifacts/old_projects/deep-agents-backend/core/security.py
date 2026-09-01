"""SecurityManager — Central security for JARVIS MK-X.

Wraps security.engine.SecurityEngine and adds:
- Security context (per-request identity + authorization)
- File access policy (allowed/blocked paths, path traversal prevention)
- Risk-based prompting (clear warnings for destructive capabilities)
- Plugin permission enforcement
- DI container integration
"""

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from security.engine import SecurityEngine, get_security_engine

logger = logging.getLogger("jarvis.core.security")

# Default allowed paths for file operations
_DEFAULT_ALLOWED_DIRS = [
    os.path.expanduser("~"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
    os.path.expanduser("~/Pictures"),
    os.path.expanduser("~/Music"),
    os.path.expanduser("~/Videos"),
]

_DEFAULT_BLOCKED_DIRS = [
    "C:\\Windows" if os.name == "nt" else "/etc",
    "C:\\Program Files" if os.name == "nt" else "/boot",
    "C:\\Program Files (x86)" if os.name == "nt" else "/sys",
    "C:\\System32" if os.name == "nt" else "/proc",
    os.path.join(os.path.expanduser("~"), ".ssh"),
    os.path.join(os.path.expanduser("~"), ".gnupg"),
    os.path.join(os.path.expanduser("~"), ".aws"),
    os.path.join(os.path.expanduser("~"), ".config"),
]


@dataclass
class SecurityContext:
    identity: str = "anonymous"
    session_id: str = ""
    authorization_level: str = "standard"
    is_authenticated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class FileAccessPolicy:
    def __init__(self, allowed_dirs: list[str] | None = None,
                 blocked_dirs: list[str] | None = None):
        self._allowed_dirs = [Path(d).resolve() for d in allowed_dirs or _DEFAULT_ALLOWED_DIRS]
        self._blocked_dirs = [Path(d).resolve() for d in blocked_dirs or _DEFAULT_BLOCKED_DIRS]

    def check_path(self, path: str, mode: str = "read") -> tuple[bool, str]:
        resolved = Path(path).resolve()

        # Check blocked dirs first
        for blocked in self._blocked_dirs:
            try:
                resolved.relative_to(blocked)
                return False, f"Access denied: path is in blocked directory: {blocked}"
            except ValueError:
                continue

        # For read, allow any path not blocked
        if mode == "read":
            return True, ""

        # For write, restrict to allowed dirs
        for allowed in self._allowed_dirs:
            try:
                resolved.relative_to(allowed)
                return True, ""
            except ValueError:
                continue

        return False, "Write access denied: path not in allowed directories"

    def sanitize_path(self, path: str) -> str:
        """Resolve and block path traversal. Raises ValueError on traversal."""
        resolved = Path(path).resolve()
        if ".." in path.split(os.sep):
            logger.warning("Path traversal blocked: %s -> %s", path, resolved)
            raise ValueError(f"Path traversal not allowed: {path}")
        return str(resolved)

    def add_allowed_dir(self, path: str):
        self._allowed_dirs.append(Path(path).resolve())

    def add_blocked_dir(self, path: str):
        self._blocked_dirs.append(Path(path).resolve())

    def to_dict(self) -> dict:
        return {
            "allowed_dirs": [str(d) for d in self._allowed_dirs],
            "blocked_dirs": [str(d) for d in self._blocked_dirs],
        }


class SecurityManager:
    def __init__(self, mode: str = "smart"):
        self._engine: SecurityEngine = get_security_engine()
        self._engine.set_mode(mode)
        self._file_policy = FileAccessPolicy()
        self._contexts: dict[str, SecurityContext] = {}
        self._lock = threading.Lock()

    # ── Mode ───────────────────────────────────

    @property
    def mode(self) -> str:
        return self._engine.mode

    def set_mode(self, mode: str):
        self._engine.set_mode(mode)
        logger.info("SecurityManager mode: %s", mode)

    # ── Context ────────────────────────────────

    def create_context(self, session_id: str, identity: str = "anonymous",
                       authorization_level: str = "standard") -> SecurityContext:
        ctx = SecurityContext(
            identity=identity,
            session_id=session_id,
            authorization_level=authorization_level,
            is_authenticated=identity != "anonymous",
        )
        with self._lock:
            self._contexts[session_id] = ctx
        return ctx

    def get_context(self, session_id: str) -> SecurityContext | None:
        with self._lock:
            return self._contexts.get(session_id)

    def remove_context(self, session_id: str):
        with self._lock:
            self._contexts.pop(session_id, None)

    # ── Permission checking ────────────────────

    def check_permission(self, tool_name: str, session_id: str = "",
                         params: dict | None = None) -> tuple[bool, str]:
        return self._engine.check_permission(tool_name, session_id, params)

    def check_file_access(self, path: str, mode: str = "read",
                          session_id: str = "") -> tuple[bool, str]:
        return self._file_policy.check_path(path, mode)

    def sanitize_path(self, path: str) -> str:
        return self._file_policy.sanitize_path(path)

    # ── Risk-based prompting ───────────────────

    def get_risk_prompt(self, capability_name: str) -> str | None:
        from core.capability_registry import resolve_capability
        cap = resolve_capability(capability_name)
        if not cap:
            return None
        if not cap.requires_confirmation and not cap.is_destructive:
            return None
        prompts = {
            "filesystem.delete": "This will permanently delete files or directories.",
            "filesystem.write": "This will modify files on disk.",
            "shell.execute": "This will run a command on your system. Only proceed if you trust the command.",
            "shell.run": "This will execute a shell command.",
            "process.kill": "This will terminate a running process.",
            "system.shutdown": "This will shut down or restart your computer.",
            "system.restart": "This will restart your computer.",
            "package.install": "This will install software on your system.",
            "package.uninstall": "This will remove software from your system.",
        }
        return prompts.get(capability_name)

    def format_confirmation_prompt(self, tool_name: str,
                                    params: dict | None = None) -> str:
        base = f"Allow '{tool_name}'?"
        risk = self.get_risk_prompt(tool_name)
        if risk:
            base = f"{risk}\n{base}"
        if params:
            param_str = ", ".join(f"{k}={v}" for k, v in params.items() if k != "api_keys")
            if param_str:
                base = f"{base}\nParameters: {param_str}"
        return base

    # ── Sandbox execution ──────────────────────

    def execute_sandboxed(self, command: str, session_id: str = "",
                          cwd: str | None = None,
                          env: dict[str, str] | None = None):
        return self._engine.execute_sandboxed(command, session_id, cwd, env)

    # ── Confirmation handler ───────────────────

    def set_confirmation_handler(self, handler: Callable[[str, dict], str]):
        self._engine.set_confirmation_handler(handler)

    # ── Plugin permission check ────────────────

    def check_plugin_permissions(self, plugin_name: str,
                                  declared_permissions: list[str]) -> bool:
        for perm in declared_permissions:
            allowed, _ = self._engine.check_permission(perm)
            if not allowed:
                logger.warning("Plugin %s denied permission: %s", plugin_name, perm)
                return False
        return True

    # ── Audit ──────────────────────────────────

    def get_audit_stats(self, since: float | None = None) -> dict:
        return self._engine.get_audit_stats(since)

    # ── Status ─────────────────────────────────

    @property
    def file_policy(self) -> FileAccessPolicy:
        return self._file_policy

    def get_status(self) -> dict:
        return {
            "mode": self._engine.mode,
            "security": self._engine.get_status(),
            "file_policy": self._file_policy.to_dict(),
            "active_sessions": len(self._contexts),
        }

    def shutdown(self):
        self._engine.shutdown()
