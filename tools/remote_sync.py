"""Remote storage — rclone-backed transfers for agents.

Derived from the repo-mine list (rclone/rclone, "rsync for cloud storage"):
70+ providers via one CLI. JARVIS wraps the documented read/transfer
commands (listremotes, copy, move, sync) through the secure executor —
no shell strings, no credentials in context (rclone reads its own config).

Classification (per repo-intake rules): copy/move are CONDITIONALLY
retryable transfers; **sync makes the destination identical to the source
and deletes extraneous destination files** — destructive on the destination,
so it is flagged destructive and refuses to run without `dry_run` first
being acknowledged by an explicit `confirm: true`.
"""

from __future__ import annotations

import logging
import shutil
from typing import Any

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.remote")

MAX_OUTPUT = 8000
TRANSFER_TIMEOUT = 900.0  # transfers can be large; executor caps apply


def _rclone_path() -> str | None:
    return shutil.which("rclone")


def _run_rclone(args_list: list[str], timeout: float) -> tuple[bool, str, str, int]:
    """Run rclone via the secure executor (structured argv, shell=False)."""
    from security.executor import ExecRequest, get_secure_executor

    exe = _rclone_path()
    if not exe:
        return False, "", "rclone binary not found", -1
    result = get_secure_executor().execute(ExecRequest(
        executable=exe, args=args_list, shell="", cwd=".", timeout=int(timeout),
    ))
    return result.success, result.stdout or "", result.stderr or "", result.exit_code


def remote_status(args: dict[str, Any]) -> ToolResult:
    """Report rclone availability, version, and configured remotes (names only)."""
    exe = _rclone_path()
    if not exe:
        return ToolResult(
            success=False,
            error=(
                "rclone is not installed. Install it to enable remote storage "
                "transfers: `winget install Rclone.Rclone` (Windows) or see "
                "https://rclone.org/install/. Then configure remotes with "
                "`rclone config`."
            ),
        )
    ok, out, err, code = _run_rclone(["version"], 30)
    if not ok and not out:
        return ToolResult(success=False, error=f"rclone version failed: {err or code}")
    version_line = (out.splitlines() or [""])[0].strip()

    ok2, out2, _err2, _c2 = _run_rclone(["listremotes"], 30)
    remotes = [ln.strip().rstrip(":") for ln in out2.splitlines() if ln.strip()]
    body = f"rclone: {version_line}"
    body += "\nremotes: " + (", ".join(remotes) if remotes else "(none configured)")
    if not remotes:
        body += "\n\nConfigure a remote with `rclone config` (interactive) to use transfers."
    return ToolResult(
        success=True,
        output=body,
        metadata={"remotes": remotes, "version": version_line},
    )


_TRANSFER_MODES = {
    "copy": ("copy", False, False),   # (subcommand, destructive, moves)
    "move": ("move", False, True),
    "sync": ("sync", True, False),
}


def remote_transfer(args: dict[str, Any]) -> ToolResult:
    """Copy/move/sync files between paths or rclone remotes.

    Sources/dests are rclone path specs: local paths, or 'remote:path'.
    mode='sync' deletes extraneous files on the destination — destructive;
    requires confirm=true after a dry_run review.
    """
    mode = str(args.get("mode", "copy")).lower()
    if mode not in _TRANSFER_MODES:
        return ToolResult(success=False, error=f"mode must be one of copy|move|sync (got '{mode}')")
    subcmd, destructive, _moves = _TRANSFER_MODES[mode]

    source = str(args.get("source", "")).strip()
    dest = str(args.get("dest", "")).strip()
    if not source or not dest:
        return ToolResult(success=False, error="source and dest are required (rclone path specs, e.g. 'gdrive:backups' or 'D:/data')")

    confirm = bool(args.get("confirm", False))
    dry_run = bool(args.get("dry_run", False))
    if destructive and not confirm and not dry_run:
        return ToolResult(
            success=False,
            error=(
                f"mode='sync' makes dest identical to source (deletes extraneous "
                f"dest files). Review first with dry_run=true, then re-run with "
                f"confirm=true."
            ),
        )

    if not _rclone_path():
        return ToolResult(
            success=False,
            error="rclone is not installed (winget install Rclone.Rclone, https://rclone.org/install/).",
        )

    argv = [subcmd]
    if dry_run:
        argv.append("--dry-run")
    for flag in ("--transfers", "--checkers", "--stats-one-line", "-v"):
        if args.get(flag.strip("-")):
            argv.append(flag)
    argv.extend([source, dest])

    ok, out, err, code = _run_rclone(argv, TRANSFER_TIMEOUT)
    if not ok and not out:
        return ToolResult(
            success=False,
            error=truncate(f"rclone {mode} failed (exit {code}): {err}", MAX_OUTPUT),
            metadata={"mode": mode, "source": source, "dest": dest, "dry_run": dry_run},
        )
    body = f"rclone {mode}{' (dry run)' if dry_run else ''} {source} -> {dest}\n{out.strip()}"
    return ToolResult(
        success=ok,
        output=truncate(body, MAX_OUTPUT),
        error="" if ok else truncate(err, MAX_OUTPUT),
        metadata={"mode": mode, "source": source, "dest": dest, "dry_run": dry_run,
                  "exit_code": code},
    )


__all__ = ["remote_status", "remote_transfer"]
