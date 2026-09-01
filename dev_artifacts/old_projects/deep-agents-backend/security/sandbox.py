"""
Sandbox — Restricted execution environment for JARVIS MK-X.

Provides resource limits, timeout enforcement, and output capture
for untrusted or high-risk actions.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.security.sandbox")


class ShellMode(Enum):
    """Classifies how a command is executed."""
    DIRECT = "direct"       # Invoked as direct executable (safest)
    CMD_C = "cmd_c"         # Invoked via cmd /c (shell interpretation still occurs)
    SHLEX = "shlex"         # Parsed via shlex on non-Windows (Unix-like)


@dataclass
class SandboxConfig:
    """Sandbox execution configuration."""
    timeout_seconds: int = 30
    max_output_bytes: int = 1024 * 1024  # 1MB
    max_memory_mb: int = 256
    allowed_paths: list[str] = field(default_factory=lambda: [str(Path.home())])
    blocked_commands: list[str] = field(default_factory=lambda: [
        "format", "rd", "rmdir", "del /s", "rm -rf /",
        "shutdown", "reboot", "bcdedit", "reg delete",
    ])
    env_overrides: dict[str, str] = field(default_factory=dict)


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
    shell_mode: ShellMode = ShellMode.DIRECT

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
            "shell_mode": self.shell_mode.value,
        }


class Sandbox:
    """Restricted execution environment."""

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self._active_processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def check_command(self, command: str) -> tuple[bool, str]:
        """Check if a command is allowed. Returns (allowed, reason)."""
        cmd_lower = command.lower().strip()

        for blocked in self.config.blocked_commands:
            if blocked.lower() in cmd_lower:
                return False, f"Blocked command pattern: {blocked}"

        # Block dangerous shell operators
        dangerous = ["&&", "&", "||", "|", ";", ">", ">>", "2>&1", ">&", "<", "^",
                     "`", "$(", "${", "\n", "\r"]
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

    @staticmethod
    def _classify_shell_mode(command: str) -> ShellMode:
        """Determine if a command can be invoked directly or needs shell interpretation.

        Commands containing shell operators (pipes, redirects, &&, etc.) require
        shell interpretation (cmd /c on Windows) and are classified as CMD_C/SHLEX.
        On Windows, also checks for cmd builtins that have no standalone executable.
        Simple commands without shell syntax can be invoked directly.
        """
        shell_operators = ["|", "&&", "||", ">", ">>", "<", ";", "`", "$(", "${"]
        for op in shell_operators:
            if op in command:
                if sys.platform == "win32":
                    return ShellMode.CMD_C
                return ShellMode.SHLEX

        # On Windows, cmd builtins need cmd /c (they have no standalone .exe)
        if sys.platform == "win32":
            first_token = command.strip().split()[0].lower()
            cmd_builtins = {
                "echo", "dir", "type", "copy", "move", "del", "ren", "cls",
                "set", "path", "cd", "chdir", "md", "mkdir", "rd", "rmdir",
                "vol", "label", "fsutil", " assoc", "ftype",
            }
            if first_token in cmd_builtins:
                return ShellMode.CMD_C

        return ShellMode.DIRECT

    def execute(self, command: str, cwd: str | None = None,
                env: dict[str, str] | None = None) -> SandboxResult:
        """Execute a command in the sandbox.

        Shell mode classification:
        - DIRECT: simple command, invoked directly (safest)
        - CMD_C: contains shell operators, invoked via cmd /c on Windows
        - SHLEX: contains shell operators, parsed via shlex on Unix
        """

        # Pre-flight checks
        allowed, reason = self.check_command(command)
        if not allowed:
            logger.warning("Sandbox blocked command: %s (%s)", command, reason)
            return SandboxResult(success=False, blocked=True, block_reason=reason)

        if cwd:
            path_ok, path_reason = self.check_path(cwd)
            if not path_ok:
                return SandboxResult(success=False, blocked=True, block_reason=path_reason)

        # Classify shell mode — determines risk level
        shell_mode = self._classify_shell_mode(command)
        if shell_mode != ShellMode.DIRECT:
            logger.info("Shell mode %s for command: %s", shell_mode.value, command)

        # Build environment — strip sensitive vars
        exec_env = {k: v for k, v in os.environ.items()
                    if not any(s in k.upper() for s in (
                        "API_KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL",
                        "PRIVATE", "AUTH",
                    ))}
        exec_env.update(self.config.env_overrides)
        if env:
            exec_env.update(env)

        start_time = time.time()
        proc_id = hashlib.sha256(command.encode()).hexdigest()[:8]

        # Build argv based on classified shell mode
        if shell_mode == ShellMode.DIRECT:
            argv = shlex.split(command)
        elif shell_mode == ShellMode.CMD_C:
            argv = ["cmd", "/c", command]
        else:
            argv = shlex.split(command)

        try:
            proc = subprocess.Popen(
                argv,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=exec_env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )  # nosec B602

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
                    shell_mode=shell_mode,
                )

            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                duration_ms = (time.time() - start_time) * 1000
                logger.warning("Sandbox timeout: %s (%.0fs)", command, self.config.timeout_seconds)
                return SandboxResult(
                    success=False, exit_code=-1, duration_ms=duration_ms,
                    timed_out=True, stderr=f"Command timed out after {self.config.timeout_seconds}s",
                    shell_mode=shell_mode,
                )

        except FileNotFoundError:
            # On Windows, DIRECT mode may fail if the command is a cmd builtin
            # or not on PATH. Fall back to CMD_C if we haven't already tried it.
            if shell_mode == ShellMode.DIRECT and sys.platform == "win32":
                logger.info("Direct exec failed for '%s', retrying via cmd /c", command)
                return self.execute(command, cwd=cwd, env=env)
            duration_ms = (time.time() - start_time) * 1000
            return SandboxResult(success=False, exit_code=-1, duration_ms=duration_ms,
                                 stderr=f"Command not found: {argv[0]}", shell_mode=shell_mode)

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

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_processes": len(self._active_processes),
                "config": {
                    "timeout": self.config.timeout_seconds,
                    "max_output": self.config.max_output_bytes,
                    "blocked_commands": len(self.config.blocked_commands),
                },
            }
