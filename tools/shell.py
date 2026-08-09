"""Shell tool — executes host commands through the Secure Executor.

This module is the user/agent-facing interface only. Every command is routed
through security.executor (the single authoritative boundary): structured
``executable``+``args`` runs with shell=False, raw ``command`` strings run
through a governed PowerShell/cmd path after policy validation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from security.executor import (
    ExecRequest,
    ExecResult,
    get_secure_executor,
    sanitize_environment,
)
from tools.schema import ToolResult, truncate

DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300
MAX_OUTPUT_CHARS = 8000


def _default_cwd() -> str:
    from core.project import ProjectContext
    return str(ProjectContext.discover().root_path)


def shell_execute(args: Dict[str, Any]) -> ToolResult:
    command = (args.get("command") or "").strip()
    executable = (args.get("executable") or "").strip()
    raw_args = args.get("args") or []

    if command and executable:
        return ToolResult(
            success=False,
            error="Provide either 'command' or 'executable'+'args', not both",
        )
    if not command and not executable:
        return ToolResult(success=False, error="No command provided")

    try:
        timeout = min(int(args.get("timeout") or DEFAULT_TIMEOUT), MAX_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    if not isinstance(raw_args, (list, tuple)):
        return ToolResult(success=False, error="'args' must be a list of strings")

    cwd = _default_cwd()
    if args.get("cwd"):
        resolved = Path(str(args["cwd"])).resolve()
        if not resolved.is_dir():
            return ToolResult(success=False, error=f"cwd does not exist: {args['cwd']}")
        cwd = str(resolved)

    req = ExecRequest(
        command=command,
        executable=executable,
        args=[str(a) for a in raw_args],
        shell=args.get("shell") or "",  # nosec B604 -- dataclass field, not a subprocess call
        cwd=cwd,
        timeout=timeout,
    )
    result: ExecResult = get_secure_executor().execute(req)

    if result.blocked:
        return ToolResult(
            success=False,
            error=f"Command blocked: {result.reason}",
            metadata={"blocked": True, "cwd": cwd, "mode": result.mode},
        )

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    output = truncate(stdout, MAX_OUTPUT_CHARS)
    if result.exit_code != 0 and not output:
        output = truncate(stderr, MAX_OUTPUT_CHARS)

    return ToolResult(
        success=result.success,
        output=output,
        error="" if result.success else truncate(stderr, MAX_OUTPUT_CHARS),
        metadata={
            "exit_code": result.exit_code,
            "cwd": cwd,
            "mode": result.mode,
            "timed_out": result.timed_out,
            "truncated": len(stdout) > MAX_OUTPUT_CHARS,
        },
    )
