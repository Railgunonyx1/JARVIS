"""Patch tool — targeted file editing without full-file overwrite."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from tools.schema import ToolResult, tool_result, truncate

logger = logging.getLogger("jarvis.tools.patch")

_MAX_OUTPUT = 6000


def _resolve(path: str) -> Path:
    """Resolve a path relative to the project root."""
    p = Path(path)
    if p.is_absolute():
        return p
    # Walk up to find .git root
    candidate = Path.cwd()
    for _ in range(10):
        if (candidate / ".git").exists():
            return candidate / p
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return Path.cwd() / p


async def patch_replace(params: dict) -> ToolResult:
    """Replace exact text in a file.

    Parameters
    ----------
    path : str
        File to edit.
    old : str
        Exact text to find (must match uniquely unless ``all`` is true).
    new : str
        Replacement text.
    all : bool
        If true, replace all occurrences. Default false (must be unique).
    """
    path = params.get("path", "")
    old = params.get("old", "")
    new = params.get("new", "")
    if not path or not old:
        return tool_result(False, error="path and old are required")

    fpath = _resolve(path)
    if not fpath.exists():
        return tool_result(False, error=f"File not found: {path}")

    try:
        content = fpath.read_text(encoding="utf-8")
    except Exception as e:
        return tool_result(False, error=f"Read failed: {e}")

    count = content.count(old)
    if count == 0:
        return tool_result(False, error=f"Text not found in {path}")
    if count > 1 and not params.get("all"):
        return tool_result(False, error=f"Ambiguous: {count} matches in {path}. Use all=true or provide more context.")

    new_content = content.replace(old, new) if params.get("all") else content.replace(old, new, 1)

    try:
        fpath.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return tool_result(False, error=f"Write failed: {e}")

    operation = f"Replace {'all ' if params.get('all') else ''}{count} occurrence(s)" if count > 1 else "Replace 1 occurrence"
    return tool_result(
        True,
        output=f"{operation} in {path}",
        path=str(fpath),
        diff=_make_diff(content, new_content, path),
    )


async def patch_insert(params: dict) -> ToolResult:
    """Insert text at a specific line number.

    Parameters
    ----------
    path : str
        File to edit.
    line : int
        Line number to insert before (1-indexed). Use 0 to append at end.
    text : str
        Text to insert.
    """
    path = params.get("path", "")
    line = int(params.get("line", 0))
    text = params.get("text", "")
    if not path or not text:
        return tool_result(False, error="path and text are required")

    fpath = _resolve(path)
    if not fpath.exists():
        return tool_result(False, error=f"File not found: {path}")

    try:
        lines = fpath.read_text(encoding="utf-8").split("\n")
    except Exception as e:
        return tool_result(False, error=f"Read failed: {e}")

    if line < 0 or line > len(lines):
        return tool_result(False, error=f"Line {line} out of range (file has {len(lines)} lines)")

    new_lines = text.split("\n")
    if line == 0:
        lines.extend(new_lines)
    else:
        for i, new_line in enumerate(new_lines):
            lines.insert(line - 1 + i, new_line)

    new_content = "\n".join(lines)
    try:
        fpath.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return tool_result(False, error=f"Write failed: {e}")

    return tool_result(
        True,
        output=f"Inserted {len(new_lines)} line(s) at line {line or 'end'} in {path}",
        path=str(fpath),
    )


async def patch_delete(params: dict) -> ToolResult:
    """Delete lines from a file by line range.

    Parameters
    ----------
    path : str
        File to edit.
    start : int
        First line to delete (1-indexed, inclusive).
    end : int, optional
        Last line to delete (inclusive). Defaults to ``start`` (single line).
    """
    path = params.get("path", "")
    start = int(params.get("start", 0))
    end = int(params.get("end", start))
    if not path or start < 1:
        return tool_result(False, error="path and start (>=1) are required")

    fpath = _resolve(path)
    if not fpath.exists():
        return tool_result(False, error=f"File not found: {path}")

    try:
        lines = fpath.read_text(encoding="utf-8").split("\n")
    except Exception as e:
        return tool_result(False, error=f"Read failed: {e}")

    if start > len(lines) or end > len(lines):
        return tool_result(False, error=f"Range {start}-{end} exceeds file length ({len(lines)} lines)")

    deleted = end - start + 1
    new_lines = lines[:start - 1] + lines[end:]
    new_content = "\n".join(new_lines)

    try:
        fpath.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return tool_result(False, error=f"Write failed: {e}")

    return tool_result(
        True,
        output=f"Deleted lines {start}-{end} ({deleted} lines) from {path}",
        path=str(fpath),
    )


def _make_diff(old: str, new: str, path: str) -> str:
    """Create a unified diff between old and new content."""
    old_lines = old.split("\n")
    new_lines = new.split("\n")

    # Simple line-by-line diff
    diffs: list[str] = []
    max_lines = max(len(old_lines), len(new_lines))
    for i in range(max_lines):
        old_line = old_lines[i] if i < len(old_lines) else None
        new_line = new_lines[i] if i < len(new_lines) else None
        if old_line != new_line:
            if old_line is not None:
                diffs.append(f"-{i + 1}: {old_line}")
            if new_line is not None:
                diffs.append(f"+{i + 1}: {new_line}")
            if len(diffs) > 40:
                diffs.append("... (diff truncated)")
                break

    return "\n".join(diffs) if diffs else "(whitespace-only change)"
