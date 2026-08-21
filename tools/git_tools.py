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
    args = ["log", "--oneline", f"-{count}"]
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
    args.extend(["--", path])
    code, out, err = _git(args)
    if code != 0:
        return tool_result(False, error=err or f"git restore {path} failed")
    return tool_result(True, output=f"Restored: {path}")


async def git_blame(params: dict) -> ToolResult:
    """Show who last modified each line of a file.

    Parameters
    ----------
    path : str
        File to blame.
    """
    path = params.get("path")
    if not path:
        return tool_result(False, error="path is required")
    code, out, err = _git(["blame", "--line-porcelain", path])
    if code != 0:
        return tool_result(False, error=err or f"git blame {path} failed")
    # Parse porcelain output into readable format
    lines = out.splitlines()
    results = []
    current = {}
    for line in lines:
        if line.startswith("author "):
            current["author"] = line[7:]
        elif line.startswith("author-time "):
            import datetime
            ts = int(line[12:])
            current["date"] = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        elif line.startswith("\t"):
            current["line"] = line[1:]
            if current.get("author") and current.get("line"):
                results.append(f"{current.get('date', '?')} {current['author']}: {current['line'][:80]}")
            current = {}
    if not results:
        # Fallback to simple blame
        code2, out2, err2 = _git(["blame", "--short", path])
        if code2 == 0 and out2:
            return tool_result(True, output=truncate(out2, _MAX_OUTPUT))
        return tool_result(False, error=err or "git blame failed")
    output = "\n".join(results[:50])
    return tool_result(True, output=truncate(output, _MAX_OUTPUT))


async def git_create_branch(params: dict) -> ToolResult:
    """Create a new branch and optionally check it out.

    Parameters
    ----------
    name : str
        Branch name.
    checkout : bool
        Switch to the new branch. Default true.
    """
    name = params.get("name")
    if not name:
        return tool_result(False, error="name is required")
    args = ["branch", name]
    code, out, err = _git(args)
    if code != 0:
        return tool_result(False, error=err or f"git branch {name} failed")
    if params.get("checkout", True):
        code2, out2, err2 = _git(["checkout", name])
        if code2 != 0:
            return tool_result(True, output=f"Branch '{name}' created but checkout failed: {err2}")
    return tool_result(True, output=f"Created branch '{name}'")


async def git_stash(params: dict) -> ToolResult:
    """Stash uncommitted changes.

    Parameters
    ----------
    action : str
        'save', 'pop', 'list', or 'drop'. Default 'save'.
    message : str
        Stash message (for save only).
    """
    action = params.get("action", "save")
    if action == "list":
        code, out, err = _git(["stash", "list"])
        if code != 0:
            return tool_result(False, error=err or "git stash list failed")
        return tool_result(True, output=out or "No stashes.")
    elif action == "pop":
        code, out, err = _git(["stash", "pop"])
        if code != 0:
            return tool_result(False, error=err or "git stash pop failed")
        return tool_result(True, output=out or "Stash popped.")
    elif action == "drop":
        code, out, err = _git(["stash", "drop"])
        if code != 0:
            return tool_result(False, error=err or "git stash drop failed")
        return tool_result(True, output=out or "Stash dropped.")
    else:  # save
        args = ["stash", "save"]
        msg = params.get("message")
        if msg:
            args.append(msg)
        code, out, err = _git(args)
        if code != 0:
            return tool_result(False, error=err or "git stash save failed")
        return tool_result(True, output=out or "Changes stashed.")


async def git_show(params: dict) -> ToolResult:
    """Show a specific commit.

    Parameters
    ----------
    ref : str
        Commit ref (hash, branch, HEAD). Default HEAD.
    """
    ref = params.get("ref", "HEAD")
    code, out, err = _git(["show", "--stat", ref])
    if code != 0:
        return tool_result(False, error=err or f"git show {ref} failed")
    return tool_result(True, output=truncate(out, _MAX_OUTPUT))
