"""Filesystem tools — read / write / list with path and size guards."""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path
from typing import Any

from tools.schema import ToolResult, truncate

MAX_READ_BYTES = 50 * 1024 * 1024
MAX_ENTRIES = 500
MAX_READ_OUTPUT = 20000
MAX_TREE_DEPTH = 3
MAX_TREE_ENTRIES = 200
TREE_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}


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


def _diff_stats(diff: str) -> dict[str, int]:
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    return {"added": added, "removed": removed}


def _root() -> Path:
    from core.project import ProjectContext
    return ProjectContext.discover().root_path


def _resolve(path_str: str | None) -> Path:
    root = _root()
    if not path_str:
        return root
    path = Path(path_str)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def filesystem_write(args: dict[str, Any]) -> ToolResult:
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


def filesystem_read(args: dict[str, Any]) -> ToolResult:
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


def filesystem_list(args: dict[str, Any]) -> ToolResult:
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


def filesystem_delete(args: dict[str, Any]) -> ToolResult:
    path = _resolve(args.get("path"))
    if not path.exists():
        return ToolResult(success=False, error=f"Path not found: {path}")
    if path.is_dir():
        try:
            next(path.iterdir())
        except StopIteration:
            pass
        except OSError as e:
            return ToolResult(success=False, error=f"Cannot inspect {path}: {e}")
        else:
            return ToolResult(success=False, error=f"Directory not empty: {path}; refusing to delete")
        try:
            path.rmdir()
        except OSError as e:
            return ToolResult(success=False, error=f"Failed to delete directory {path}: {e}")
        return ToolResult(
            success=True,
            output=f"Deleted directory {path}",
            metadata={"path": str(path), "type": "dir"},
        )
    try:
        path.unlink()
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to delete {path}: {e}")
    return ToolResult(
        success=True,
        output=f"Deleted file {path}",
        metadata={"path": str(path), "type": "file"},
    )


def filesystem_copy(args: dict[str, Any]) -> ToolResult:
    source = _resolve(args.get("source"))
    dest = _resolve(args.get("dest"))
    if not source.exists():
        return ToolResult(success=False, error=f"Source not found: {source}")
    if source.is_dir():
        return ToolResult(success=False, error=f"Source is a directory: {source}")
    if dest.is_dir():
        dest = dest / source.name
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to copy {source} to {dest}: {e}")
    return ToolResult(
        success=True,
        output=f"Copied {source} to {dest}",
        metadata={"source": str(source), "dest": str(dest), "bytes": dest.stat().st_size},
    )


def filesystem_move(args: dict[str, Any]) -> ToolResult:
    source = _resolve(args.get("source"))
    dest = _resolve(args.get("dest"))
    if not source.exists():
        return ToolResult(success=False, error=f"Source not found: {source}")
    if dest.exists() and dest.is_dir():
        dest = dest / source.name
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(dest))
    except (OSError, shutil.Error) as e:
        return ToolResult(success=False, error=f"Failed to move {source} to {dest}: {e}")
    return ToolResult(
        success=True,
        output=f"Moved {source} to {dest}",
        metadata={"source": str(source), "dest": str(dest)},
    )


def filesystem_diff(args: dict[str, Any]) -> ToolResult:
    path_a = _resolve(args.get("file_a"))
    path_b = _resolve(args.get("file_b"))
    if not path_a.exists():
        return ToolResult(success=False, error=f"File not found: {path_a}")
    if not path_b.exists():
        return ToolResult(success=False, error=f"File not found: {path_b}")
    if path_a.is_dir() or path_b.is_dir():
        return ToolResult(success=False, error="Diff requires two files, not directories")
    try:
        text_a = path_a.read_text(encoding="utf-8", errors="replace")
        text_b = path_b.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to read files for diff: {e}")
    diff_lines = list(difflib.unified_diff(
        text_a.splitlines(), text_b.splitlines(),
        fromfile=str(path_a), tofile=str(path_b), lineterm="",
    ))
    stats = _diff_stats("\n".join(diff_lines))
    identical = not diff_lines
    output = "\n".join(diff_lines) if diff_lines else "(files are identical)"
    return ToolResult(
        success=True,
        output=truncate(output, MAX_READ_OUTPUT),
        metadata={
            "file_a": str(path_a),
            "file_b": str(path_b),
            "added": stats["added"],
            "removed": stats["removed"],
            "identical": identical,
        },
    )


def _tree_lines(path: Path, prefix: str, depth: int, max_depth: int, budget: list[int]) -> list[str]:
    try:
        entries = sorted(path.iterdir(), key=lambda p: p.name)
    except OSError:
        return [f"{prefix}(unreadable)"]
    lines: list[str] = []
    for entry in entries:
        if budget[0] <= 0:
            lines.append(f"{prefix}... (max entries reached)")
            break
        if entry.is_dir():
            if entry.name in TREE_SKIP_DIRS:
                continue
            budget[0] -= 1
            lines.append(f"{prefix}{entry.name}/")
            if depth + 1 < max_depth:
                lines.extend(_tree_lines(entry, prefix + "  ", depth + 1, max_depth, budget))
        else:
            budget[0] -= 1
            lines.append(f"{prefix}{entry.name}")
    return lines


def filesystem_tree(args: dict[str, Any]) -> ToolResult:
    path = _resolve(args.get("path"))
    if not path.exists():
        return ToolResult(success=False, error=f"Directory not found: {path}")
    if not path.is_dir():
        return ToolResult(success=False, error=f"Not a directory: {path}")
    max_depth = int(args.get("max_depth") or MAX_TREE_DEPTH)
    max_entries = int(args.get("max_entries") or MAX_TREE_ENTRIES)
    if max_depth < 1:
        return ToolResult(success=False, error=f"max_depth must be >= 1, got {max_depth}")
    budget = [max_entries]
    lines = _tree_lines(path, "", 0, max_depth, budget)
    shown = len(lines)
    return ToolResult(
        success=True,
        output=truncate("\n".join(lines) or "(empty)", MAX_READ_OUTPUT),
        metadata={"path": str(path), "max_depth": max_depth, "entries_shown": shown, "truncated": budget[0] <= 0},
    )
