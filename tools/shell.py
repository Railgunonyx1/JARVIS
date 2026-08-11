"""Shell tool — executes host commands through the Secure Executor.

This module is the user/agent-facing interface only. Every command is routed
through security.executor (the single authoritative boundary): structured
``executable``+``args`` runs with shell=False, raw ``command`` strings run
through a governed PowerShell/cmd path after policy validation.
"""

from __future__ import annotations

import ast
import hashlib
import logging
import os
import shlex
from pathlib import Path
from typing import Any

from security.executor import (
    ExecRequest,
    ExecResult,
    get_secure_executor,
)
from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.shell")

DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300
MAX_OUTPUT_CHARS = 8000


def _default_cwd() -> str:
    from core.project import ProjectContext
    return str(ProjectContext.discover().root_path)


def _audit_shell_execution(command: str, args: list[str],
                           result: ExecResult) -> None:
    """Record every shell execution (allowed, blocked, or timed out) in the
    persistent audit log.

    The raw command is deliberately NOT stored — only a hash, so secrets can
    never leak into the audit DB. Audit failure must never break the command,
    so the whole write is best-effort.
    """
    try:
        from security.audit import AuditEntry, get_audit_log
        from security.policies import PermissionLevel

        payload = (command or " ".join([command, *args])).encode("utf-8", "replace")
        get_audit_log().log(AuditEntry(
            action="shell_execute",
            tool="shell.execute",
            permission_level=PermissionLevel.ELEVATED,
            allowed=not result.blocked,
            duration_ms=result.duration_ms,
            success=result.success,
            error=(result.reason or (result.stderr if not result.success else None)
                   or "")[:500] or None,
            params_hash=hashlib.sha256(payload).hexdigest()[:16],
            mode=result.mode,
        ))
    except Exception:
        logger.warning("audit write failed for shell_execute", exc_info=True)


def _coerce_args(raw_args: Any) -> list[str] | None:
    """Coerce model-supplied ``args`` to a list of strings.

    Models sometimes emit ``args`` as a stringified list (e.g. the repr of a
    Python list, or a shell-ish string). Return None when the value is not a
    usable argument list.
    """
    if isinstance(raw_args, (list, tuple)):
        return [str(a) for a in raw_args]
    if isinstance(raw_args, str):
        text = raw_args.strip()
        if not text:
            return []
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple)):
                return [str(a) for a in parsed]
        except (ValueError, SyntaxError):
            pass
        return shlex.split(text, posix=os.name != "nt")
    return None


def shell_execute(args: dict[str, Any]) -> ToolResult:
    command = (args.get("command") or "").strip()
    executable = (args.get("executable") or "").strip()
    raw_args = args.get("args") or []
    coerced = _coerce_args(raw_args)
    if coerced is None:
        return ToolResult(
            success=False,
            error="'args' must be a list of strings (or a stringified list)",
        )

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

    cwd = _default_cwd()
    if args.get("cwd"):
        resolved = Path(str(args["cwd"])).resolve()
        if not resolved.is_dir():
            return ToolResult(success=False, error=f"cwd does not exist: {args['cwd']}")
        cwd = str(resolved)

    req = ExecRequest(
        command=command,
        executable=executable,
        args=coerced,
        shell=args.get("shell") or "",  # nosec B604 -- dataclass field, not a subprocess call
        cwd=cwd,
        timeout=timeout,
    )
    result: ExecResult = get_secure_executor().execute(req)
    _audit_shell_execution(command or executable, args, result)

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
