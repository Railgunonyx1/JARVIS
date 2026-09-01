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


async def git_merge(params: dict) -> ToolResult:
    """Merge a branch into the current branch.

    Parameters
    ----------
    branch : str
        Branch to merge.
    """
    branch = params.get("branch")
    if not branch:
        return tool_result(False, error="branch is required")
    code, out, err = _git(["merge", branch])
    if code != 0:
        return tool_result(False, error=err or f"git merge {branch} failed")
    return tool_result(True, output=truncate(out or f"Merged '{branch}'.", _MAX_OUTPUT))


async def git_rebase(params: dict) -> ToolResult:
    """Rebase the current branch onto another branch.

    Parameters
    ----------
    onto : str
        Branch to rebase onto.
    """
    onto = params.get("onto")
    if not onto:
        return tool_result(False, error="onto is required")
    code, out, err = _git(["rebase", onto])
    if code != 0:
        return tool_result(False, error=err or f"git rebase {onto} failed")
    return tool_result(True, output=out or f"Rebased onto '{onto}'.")


async def git_tag(params: dict) -> ToolResult:
    """Create an annotated tag or list existing tags.

    Parameters
    ----------
    action : str
        'create' or 'list'. Default 'create'.
    name : str
        Tag name (required for create).
    message : str, optional
        Tag message (for create).
    """
    action = params.get("action", "create")
    if action == "list":
        code, out, err = _git(["tag"])
        if code != 0:
            return tool_result(False, error=err or "git tag list failed")
        return tool_result(True, output=out or "No tags.")
    name = params.get("name")
    if not name:
        return tool_result(False, error="name is required for tag creation")
    message = params.get("message") or name
    code, out, err = _git(["tag", "-a", name, "-m", message])
    if code != 0:
        return tool_result(False, error=err or f"git tag {name} failed")
    return tool_result(True, output=f"Created tag '{name}'")


async def git_fetch(params: dict) -> ToolResult:
    """Fetch from a remote.

    Parameters
    ----------
    remote : str
        Remote name. Default 'origin'.
    """
    remote = params.get("remote", "origin")
    code, out, err = _git(["fetch", remote])
    if code != 0:
        return tool_result(False, error=err or f"git fetch {remote} failed")
    return tool_result(True, output=out or f"Fetched from '{remote}'.")


async def git_pull(params: dict) -> ToolResult:
    """Pull from a remote branch.

    Parameters
    ----------
    remote : str, optional
        Remote name. Default 'origin'.
    branch : str, optional
        Branch to pull.
    """
    args = ["pull"]
    remote = params.get("remote", "origin")
    args.append(remote)
    branch = params.get("branch")
    if branch:
        args.append(branch)
    code, out, err = _git(args)
    if code != 0:
        return tool_result(False, error=err or "git pull failed")
    return tool_result(True, output=truncate(out or "Already up to date.", _MAX_OUTPUT))


async def git_push(params: dict) -> ToolResult:
    """Push commits to a remote branch.

    Parameters
    ----------
    remote : str, optional
        Remote name. Default 'origin'.
    branch : str, optional
        Branch to push.
    """
    args = ["push"]
    remote = params.get("remote", "origin")
    args.append(remote)
    branch = params.get("branch")
    if branch:
        args.append(branch)
    code, out, err = _git(args)
    if code != 0:
        return tool_result(False, error=err or "git push failed")
    return tool_result(True, output=out or "Pushed.")


async def git_revert(params: dict) -> ToolResult:
    """Revert a commit by creating a new commit.

    Parameters
    ----------
    ref : str
        Commit ref to revert.
    """
    ref = params.get("ref")
    if not ref:
        return tool_result(False, error="ref is required")
    code, out, err = _git(["revert", "--no-edit", ref])
    if code != 0:
        return tool_result(False, error=err or f"git revert {ref} failed")
    return tool_result(True, output=out or f"Reverted {ref}.")


async def git_cherry_pick(params: dict) -> ToolResult:
    """Apply the changes from an existing commit.

    Parameters
    ----------
    ref : str
        Commit ref to cherry-pick.
    """
    ref = params.get("ref")
    if not ref:
        return tool_result(False, error="ref is required")
    code, out, err = _git(["cherry-pick", ref])
    if code != 0:
        return tool_result(False, error=err or f"git cherry-pick {ref} failed")
    return tool_result(True, output=out or f"Cherry-picked {ref}.")


async def git_reset(params: dict) -> ToolResult:
    """Reset the current HEAD to a specified state.

    Parameters
    ----------
    ref : str
        Commit ref to reset to.
    mode : str
        'soft', 'mixed', or 'hard'. Default 'mixed'.
    """
    ref = params.get("ref")
    if not ref:
        return tool_result(False, error="ref is required")
    mode = params.get("mode", "mixed")
    if mode not in ("soft", "mixed", "hard"):
        return tool_result(False, error=f"invalid mode '{mode}', must be soft, mixed, or hard")
    code, out, err = _git(["reset", f"--{mode}", ref])
    if code != 0:
        return tool_result(False, error=err or f"git reset --{mode} {ref} failed")
    return tool_result(True, output=f"Reset to {ref} ({mode}).")


async def git_worktree(params: dict) -> ToolResult:
    """Manage multiple working trees.

    Parameters
    ----------
    action : str
        'add', 'list', or 'remove'.
    path : str
        Worktree path (required for add/remove).
    branch : str, optional
        Branch to check out in the new worktree (for add).
    """
    action = params.get("action", "list")
    if action == "list":
        code, out, err = _git(["worktree", "list"])
        if code != 0:
            return tool_result(False, error=err or "git worktree list failed")
        return tool_result(True, output=out or "No worktrees.")
    path = params.get("path")
    if not path:
        return tool_result(False, error="path is required for add/remove")
    if action == "add":
        args = ["worktree", "add", path]
        branch = params.get("branch")
        if branch:
            args.append(branch)
        code, out, err = _git(args)
        if code != 0:
            return tool_result(False, error=err or f"git worktree add {path} failed")
        return tool_result(True, output=out or f"Worktree added at '{path}'.")
    if action == "remove":
        code, out, err = _git(["worktree", "remove", path])
        if code != 0:
            return tool_result(False, error=err or f"git worktree remove {path} failed")
        return tool_result(True, output=out or f"Worktree '{path}' removed.")
    return tool_result(False, error=f"unknown action '{action}', must be add, list, or remove")
