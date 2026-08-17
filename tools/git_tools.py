"""Git tools — first-class git operations for the agent."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from tools.schema import ToolResult, tool_result, truncate

logger = logging.getLogger("jarvis.tools.git")

_MAX_OUTPUT = 8000


def _git(args: list[str], cwd: str | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=cwd or str(Path.cwd()), check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "git is not installed or not in PATH"
    except subprocess.TimeoutExpired:
        return -1, "", f"git command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


async def git_status(params: dict) -> ToolResult:
    """Show the working tree status."""
    code, out, err = _git(["status", "--short"])
    if code != 0:
        return tool_result(False, error=err or "git status failed")
    output = out or "Working tree clean."
    return tool_result(True, output=truncate(output, _MAX_OUTPUT))


async def git_diff(params: dict) -> ToolResult:
    """Show changes in the working tree or staged changes.

    Parameters
    ----------
    staged : bool
        If true, show staged changes (``--cached``). Default false.
    path : str, optional
        Restrict diff to a specific file.
    """
    args = ["diff"]
    if params.get("staged"):
        args.append("--cached")
    path = params.get("path")
    if path:
        args.append("--")
        args.append(path)
    code, out, err = _git(args)
    if code != 0:
        return tool_result(False, error=err or "git diff failed")
    output = out or "No changes."
    return tool_result(True, output=truncate(output, _MAX_OUTPUT))


async def git_log(params: dict) -> ToolResult:
    """Show recent commit history.

    Parameters
    ----------
    count : int
        Number of commits to show. Default 10.
    path : str, optional
        Restrict log to a specific file.
    """
    count = min(int(params.get("count", 10)), 50)
    args = ["log", f"--oneline", f"-{count}"]
    path = params.get("path")
    if path:
        args.extend(["--", path])
    code, out, err = _git(args)
    if code != 0:
        return tool_result(False, error=err or "git log failed")
    return tool_result(True, output=truncate(out, _MAX_OUTPUT))


async def git_branch(params: dict) -> ToolResult:
    """List branches or show the current branch."""
    code, out, err = _git(["branch", "--show-current"])
    if code != 0:
        return tool_result(False, error=err or "git branch failed")
    return tool_result(True, output=out)


async def git_add(params: dict) -> ToolResult:
    """Stage files for commit.

    Parameters
    ----------
    path : str
        File or directory to stage. Use ``.`` for all.
    """
    path = params.get("path", ".")
    code, out, err = _git(["add", path])
    if code != 0:
        return tool_result(False, error=err or f"git add {path} failed")
    return tool_result(True, output=f"Staged: {path}")


async def git_commit(params: dict) -> ToolResult:
    """Create a new commit with the staged changes.

    Parameters
    ----------
    message : str
        Commit message.
    """
    message = params.get("message", "")
    if not message:
        return tool_result(False, error="message is required")
    code, out, err = _git(["commit", "-m", message])
    if code != 0:
        return tool_result(False, error=err or "git commit failed")
    return tool_result(True, output=out or "Committed.")


async def git_restore(params: dict) -> ToolResult:
    """Discard changes in working tree.

    Parameters
    ----------
    path : str
        File to restore. Use ``.`` for all.
    staged : bool
        If true, unstage as well.
    """
    path = params.get("path", ".")
    args = ["checkout"]
    if params.get("staged"):
        args.append("--")
        args.append(path)
    else:
        args.append("--")
        args.append(path)
    code, out, err = _git(args)
    if code != 0:
        return tool_result(False, error=err or f"git restore {path} failed")
    return tool_result(True, output=f"Restored: {path}")
