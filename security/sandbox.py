"""
Sandbox — Restricted execution environment for JARVIS MK-X.

Provides resource limits, timeout enforcement, and output capture
for untrusted or high-risk actions.
"""

from __future__ import annotations

import os
import sys
import time
import signal
import logging
import hashlib
import tempfile
import threading
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.security.sandbox")


@dataclass
class SandboxConfig:
    """Sandbox execution configuration."""
    timeout_seconds: int = 30
    max_output_bytes: int = 1024 * 1024  # 1MB
    max_memory_mb: int = 256
    allowed_paths: List[str] = field(default_factory=lambda: [str(Path.home())])
    blocked_commands: List[str] = field(default_factory=lambda: [
        "format", "rd", "rmdir", "del /s", "rm -rf /",
        "shutdown", "reboot", "bcdedit", "reg delete",
    ])
    env_overrides: Dict[str, str] = field(default_factory=dict)


@dataclass
class SandboxResult:
    """Result of a sandboxed execution."""
    success: bool = True
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    timed_out: bool = False
    blocked: bool = False
    block_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "stdout": self.stdout[:500],
            "stderr": self.stderr[:500],
            "exit_code": self.exit_code,
            "duration_ms": round(self.duration_ms, 1),
            "timed_out": self.timed_out,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }


class Sandbox:
    """Restricted execution environment."""

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._active_processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def check_command(self, command: str) -> tuple[bool, str]:
        """Check if a command is allowed. Returns (allowed, reason)."""
        cmd_lower = command.lower().strip()

        for blocked in self.config.blocked_commands:
            if blocked.lower() in cmd_lower:
                return False, f"Blocked command pattern: {blocked}"

        # Block dangerous shell operators
        dangerous = ["&&", "&", "||", "|", ">", ">>", "2>&1", ">&", "<", "^",
                     "\n", "\r"]
        for d in dangerous:
            if d in cmd_lower:
                # Allow common safe redirects
                if d == ">" and "nul" in cmd_lower:
                    continue
                return False, f"Blocked shell operator: {d}"

        return True, ""

    def check_path(self, path: str) -> tuple[bool, str]:
        """Check if a file path is within allowed directories."""
        try:
            resolved = str(Path(path).resolve())
            for allowed in self.config.allowed_paths:
                if resolved.startswith(str(Path(allowed).resolve())):
                    return True, ""
            return False, f"Path outside allowed directories: {path}"
        except Exception as e:
            return False, f"Invalid path: {e}"

    def execute(self, command: str, cwd: Optional[str] = None,
                env: Optional[Dict[str, str]] = None) -> SandboxResult:
        """Execute a command in the sandbox."""
        # Pre-flight checks
        allowed, reason = self.check_command(command)
        if not allowed:
            logger.warning("Sandbox blocked command: %s (%s)", command, reason)
            return SandboxResult(success=False, blocked=True, block_reason=reason)

        if cwd:
            path_ok, path_reason = self.check_path(cwd)
            if not path_ok:
                return SandboxResult(success=False, blocked=True, block_reason=path_reason)

        # Build environment
        exec_env = os.environ.copy()
        exec_env.update(self.config.env_overrides)
        if env:
            exec_env.update(env)

        start_time = time.time()
        proc_id = hashlib.sha256(command.encode()).hexdigest()[:8]

        try:
            # Use subprocess with timeout
            is_windows = sys.platform == "win32"
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=exec_env,
                creationflags=subprocess.CREATE_NO_WINDOW if is_windows else 0,
            )

            with self._lock:
                self._active_processes[proc_id] = proc

            try:
                stdout, stderr = proc.communicate(timeout=self.config.timeout_seconds)
                duration_ms = (time.time() - start_time) * 1000

                stdout_str = stdout.decode("utf-8", errors="replace")[:self.config.max_output_bytes]
                stderr_str = stderr.decode("utf-8", errors="replace")[:self.config.max_output_bytes]

                return SandboxResult(
                    success=proc.returncode == 0,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    exit_code=proc.returncode,
                    duration_ms=duration_ms,
                )

            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                duration_ms = (time.time() - start_time) * 1000
                logger.warning("Sandbox timeout: %s (%.0fs)", command, self.config.timeout_seconds)
                return SandboxResult(
                    success=False, exit_code=-1, duration_ms=duration_ms,
                    timed_out=True, stderr=f"Command timed out after {self.config.timeout_seconds}s"
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("Sandbox execution error: %s", e)
            return SandboxResult(success=False, exit_code=-1, duration_ms=duration_ms, stderr=str(e))

        finally:
            with self._lock:
                self._active_processes.pop(proc_id, None)

    def kill_all(self):
        """Kill all active sandbox processes."""
        with self._lock:
            for proc_id, proc in self._active_processes.items():
                try:
                    proc.kill()
                except Exception:
                    pass
            self._active_processes.clear()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_processes": len(self._active_processes),
                "config": {
                    "timeout": self.config.timeout_seconds,
                    "max_output": self.config.max_output_bytes,
                    "blocked_commands": len(self.config.blocked_commands),
                },
            }
