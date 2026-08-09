"""Shell tool — executes host commands with safety constraints.

Guards: timeout, output truncation, sanitized environment (no secrets),
explicit cwd, and a mandatory permission check in the agent runtime.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from tools.schema import ToolResult, truncate

DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300
MAX_OUTPUT_CHARS = 8000

_SECRET_PATTERNS = (
    "api_key", "apikey", "token", "secret", "password", "credential",
    "authorization", "groq", "gemini", "openrouter", "opencode", "openai",
)


def _sanitized_env() -> Dict[str, str]:
    """Environment copy with credential-like variables removed."""
    env = dict(os.environ)
    for key in list(env):
        lower = key.lower()
        if any(pattern in lower for pattern in _SECRET_PATTERNS):
            env.pop(key, None)
    return env


def _default_cwd() -> str:
    from core.project import ProjectContext
    return str(ProjectContext.discover().root_path)


def shell_execute(args: Dict[str, Any]) -> ToolResult:
    command = (args.get("command") or "").strip()
    if not command:
        return ToolResult(success=False, error="No command provided")
    try:
        timeout = min(int(args.get("timeout") or DEFAULT_TIMEOUT), MAX_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    cwd = _default_cwd()
    if args.get("cwd"):
        resolved = Path(str(args["cwd"])).resolve()
        if not resolved.is_dir():
            return ToolResult(success=False, error=f"cwd does not exist: {args['cwd']}")
        cwd = str(resolved)

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        # Shell tool is permission-gated by the agent runtime before execution.
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
            env=_sanitized_env(),
            creationflags=creationflags,
            check=False,
        )  # nosec B602
    except subprocess.TimeoutExpired:
        return ToolResult(
            success=False,
            error=f"Command timed out after {timeout}s",
            metadata={"timeout_s": timeout, "cwd": cwd},
        )
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to run command: {e}")

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    output = truncate(stdout, MAX_OUTPUT_CHARS)
    if proc.returncode != 0 and not output:
        output = truncate(stderr, MAX_OUTPUT_CHARS)

    return ToolResult(
        success=proc.returncode == 0,
        output=output,
        error="" if proc.returncode == 0 else truncate(stderr, MAX_OUTPUT_CHARS),
        metadata={
            "exit_code": proc.returncode,
            "cwd": cwd,
            "shell": "cmd" if os.name == "nt" else "sh",
            "truncated": len(stdout) > MAX_OUTPUT_CHARS,
        },
    )
