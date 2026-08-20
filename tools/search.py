"""Search tools — grep/ripgrep across repository files."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from tools.schema import ToolResult, tool_result, truncate

logger = logging.getLogger("jarvis.tools.search")

_MAX_RESULTS = 200
_MAX_LINE_LEN = 300


def _resolve_project_root() -> Path:
    """Walk up from cwd to find a .git marker; fall back to cwd."""
    p = Path.cwd()
    for _ in range(10):
        if (p / ".git").exists():
            return p
        parent = p.parent
        if parent == p:
            break
        p = parent
    return Path.cwd()


async def code_search(params: dict) -> ToolResult:
    """Search file contents using regex across the repository.

    Parameters
    ----------
    pattern : str
        Regex pattern to search for (case-insensitive by default).
    path : str, optional
        Subdirectory to restrict search. Defaults to project root.
    include : str, optional
        File glob filter (e.g. ``*.py``).
    max_results : int, optional
        Cap on returned matches. Default 200.
    """
    pattern = params.get("pattern", "")
    if not pattern:
        return tool_result(False, error="pattern is required")

    search_path = params.get("path", "")
    include = params.get("include", "")
    max_results = min(int(params.get("max_results", _MAX_RESULTS)), 500)

    root = _resolve_project_root()
    target = root / search_path if search_path else root

    if not target.exists():
        return tool_result(False, error=f"Path does not exist: {search_path}")

    # Try ripgrep first (much faster), fall back to pure Python
    rg_result = _try_ripgrep(pattern, target, include, max_results)
    if rg_result is not None:
        return rg_result

    return _python_grep(pattern, target, include, max_results)


def _try_ripgrep(pattern: str, target: Path, include: str, max_results: int) -> ToolResult | None:
    """Attempt ripgrep search. Returns None if rg is unavailable."""
    rg = "rg.exe" if sys.platform == "win32" else "rg"
    try:
        cmd = [
            rg, "-n", "--no-heading", "-i",
            "--max-count", str(max_results),
            "--max-columns", str(_MAX_LINE_LEN),
            "-e", pattern,
        ]
        if include:
            cmd.extend(["-g", include])
        # Exclude common non-source dirs
        cmd.extend(["--glob", "!venv", "--glob", "!node_modules",
                     "--glob", "!__pycache__", "--glob", "!.git",
                     "--glob", "!_quarantine*"])
        cmd.append(str(target))

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=str(target), check=False,
        )
        output = result.stdout.strip()
        if not output and result.returncode == 1:
            return tool_result(True, output="No matches found.")
        if result.returncode not in (0, 1):
            return None  # rg failed, fall back
        lines = output.split("\n")
        count = len(lines)
        summary = truncate(output, 8000)
        return tool_result(
            True,
            output=summary,
            path=str(target),
            match_count=count,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return tool_result(False, error="Search timed out after 30s")
    except Exception:
        return None


def _python_grep(pattern: str, target: Path, include: str, max_results: int) -> ToolResult:
    """Pure-Python fallback grep."""
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return tool_result(False, error=f"Invalid regex: {e}")

    matches: list[str] = []
    skip = {"venv", "node_modules", "__pycache__", ".git",
            "_quarantine", "_quarantine_removed", "web", ".kilo", ".kilocode"}

    for dirpath, dirnames, filenames in os.walk(target):
        # Prune skipped directories
        dirnames[:] = [d for d in dirnames if d not in skip]

        for fname in filenames:
            if include and not Path(fname).match(include):
                continue
            fpath = Path(dirpath) / fname
            # Skip binary-ish files by extension
            if fpath.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp",
                                         ".ico", ".woff", ".woff2", ".ttf", ".exe",
                                         ".dll", ".so", ".dylib", ".pyc", ".pyo",
                                         ".db", ".sqlite", ".pdf", ".zip", ".tar",
                                         ".gz", ".rar"}:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(text.split("\n"), 1):
                    if regex.search(line):
                        rel = fpath.relative_to(target)
                        truncated_line = line.strip()[:_MAX_LINE_LEN]
                        matches.append(f"{rel}:{i}: {truncated_line}")
                        if len(matches) >= max_results:
                            break
            except Exception:
                continue
            if len(matches) >= max_results:
                break
        if len(matches) >= max_results:
            break

    if not matches:
        return tool_result(True, output="No matches found.")

    count = len(matches)
    header = f"{count} match(es) found"
    if count >= max_results:
        header += f" (capped at {max_results})"
    output = header + "\n" + "\n".join(matches)
    return tool_result(
        True,
        output=truncate(output, 8000),
        path=str(target),
        match_count=count,
    )


async def file_find(params: dict) -> ToolResult:
    """Find files by name pattern across the repository.

    Parameters
    ----------
    pattern : str
        Glob pattern (e.g. ``*.py``, ``**/test_*.py``).
    path : str, optional
        Subdirectory to search in. Defaults to project root.
    """
    pattern = params.get("pattern", "")
    if not pattern:
        return tool_result(False, error="pattern is required")

    search_path = params.get("path", "")
    root = _resolve_project_root()
    target = root / search_path if search_path else root

    if not target.exists():
        return tool_result(False, error=f"Path does not exist: {search_path}")

    skip = {"venv", "node_modules", "__pycache__", ".git",
            "_quarantine", "_quarantine_removed"}

    try:
        files = []
        for f in target.glob(pattern):
            # Skip ignored directories
            parts = f.relative_to(target).parts
            if any(p in skip for p in parts):
                continue
            files.append(str(f.relative_to(target)))
            if len(files) > 200:
                break

        if not files:
            return tool_result(True, output="No files found matching pattern.")

        output = f"{len(files)} file(s) found:\n" + "\n".join(sorted(files))
        return tool_result(True, output=truncate(output, 6000))
    except Exception as e:
        return tool_result(False, error=str(e))
