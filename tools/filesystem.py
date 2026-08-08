"""Filesystem tools — read / write / list with path and size guards."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any, Dict, Optional

from tools.schema import ToolResult, truncate

MAX_READ_BYTES = 50 * 1024 * 1024
MAX_ENTRIES = 500
MAX_READ_OUTPUT = 20000


def _brief_diff(before: str, after: str, max_lines: int = 12) -> str:
    """Compact unified diff for change preview (returns '' when identical)."""
    if before == after:
        return ""
    diff = list(difflib.unified_diff(
        before.splitlines(), after.splitlines(), lineterm="", n=1,
    ))
    if len(diff) > max_lines + 4:
        diff = diff[: max_lines + 1] + [f"... ({len(diff) - max_lines - 1} more lines)"]
    return "\n".join(diff)


def _diff_stats(diff: str) -> Dict[str, int]:
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    return {"added": added, "removed": removed}


def _root() -> Path:
    from core.project import ProjectContext
    return ProjectContext.discover().root_path


def _resolve(path_str: Optional[str]) -> Path:
    root = _root()
    if not path_str:
        return root
    path = Path(path_str)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def filesystem_write(args: Dict[str, Any]) -> ToolResult:
    path = _resolve(args.get("path"))
    content = str(args.get("content", "") or "")
    overwrite = bool(args.get("overwrite", True))
    if path.exists() and path.is_dir():
        return ToolResult(success=False, error=f"Is a directory: {path}")
    if path.exists() and not overwrite:
        return ToolResult(success=False, error=f"File exists: {path} (set overwrite=true to replace)")
    try:
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to write {path}: {e}")
    diff = _brief_diff(before, content)
    metadata = {"path": str(path), "chars": len(content), "bytes": len(content.encode("utf-8"))}
    if diff:
        metadata["diff"] = diff
        metadata["diff_stats"] = _diff_stats(diff)
    return ToolResult(
        success=True,
        output=f"Wrote {len(content)} chars to {path}",
        metadata=metadata,
    )


def filesystem_read(args: Dict[str, Any]) -> ToolResult:
    path = _resolve(args.get("path"))
    if not path.exists():
        return ToolResult(success=False, error=f"File not found: {path}")
    if path.is_dir():
        return ToolResult(success=False, error=f"Is a directory: {path}")
    size = path.stat().st_size
    if size > MAX_READ_BYTES:
        return ToolResult(success=False, error=f"File too large ({size} bytes > {MAX_READ_BYTES}); refusing to read")
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to read {path}: {e}")
    return ToolResult(
        success=True,
        output=truncate(content, MAX_READ_OUTPUT),
        metadata={"path": str(path), "bytes": size},
    )


def filesystem_list(args: Dict[str, Any]) -> ToolResult:
    path = _resolve(args.get("path"))
    if not path.exists():
        return ToolResult(success=False, error=f"Directory not found: {path}")
    if not path.is_dir():
        return ToolResult(success=False, error=f"Not a directory: {path}")
    detail = bool(args.get("detail", False))
    try:
        entries = sorted(path.iterdir(), key=lambda p: p.name)
    except OSError as e:
        return ToolResult(success=False, error=f"Cannot list {path}: {e}")
    lines = []
    for entry in entries[:MAX_ENTRIES]:
        if detail:
            try:
                st = entry.stat()
                size = st.st_size if entry.is_file() else 0
                lines.append(f"{entry.name}\t{size}\t{'dir' if entry.is_dir() else 'file'}")
            except OSError:
                lines.append(f"{entry.name}\t?\t?")
        else:
            lines.append(f"{entry.name}/" if entry.is_dir() else entry.name)
    return ToolResult(
        success=True,
        output="\n".join(lines) or "(empty)",
        metadata={"path": str(path), "count": len(entries), "truncated": len(entries) > MAX_ENTRIES},
    )
