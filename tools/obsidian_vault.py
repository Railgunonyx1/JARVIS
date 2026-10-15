"""Obsidian vault filesystem bridge.

Reads/writes the Obsidian vault at /home/Railgunonyx/Desktop/Obsidean/1
directly on disk. Obsidian is treated only as the viewer/editor for this
vault; this module never launches or drives the Obsidian app.

All paths returned are relative to the vault root, never absolute, so agent
output stays vault-scoped even though the module works on absolute paths
under the hood.

Undo: writes and deletes register with core/agent/undo so session.undo can
reverse them (same pattern tools/filesystem.py uses).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

from tools.schema import ToolResult, truncate

_MAX_READ_BYTES = 2_000_000  # 2 MB per note
_MAX_READ_OUTPUT = 20000
_MAX_LIST_ENTRIES = 500
_VAULT_ROOT = Path("/home/Railgunonyx/Desktop/Obsidean/1")
_VAULT_ROOT.mkdir(parents=True, exist_ok=True)

IDX = Path(".obsidian") / "cache" / "jarvis_index.json"

_SKIP_DOT_PREFIX = True
_SKIP_DIRS = {".obsidian", ".trash", "__pycache__", ".git", "node_modules"}


def _relative_to_vault(path: Path) -> Path:
    """Absolute path -> vault-relative path, or ValueError if outside."""
    try:
        return path.resolve().relative_to(_VAULT_ROOT.resolve())
    except ValueError as e:
        raise ValueError(f"Path {path} is outside the Obsidian vault {_VAULT_ROOT}.") from e


def _resolve_vault(path_str: str | None) -> Path:
    """Vault-relative path string -> absolute Path, scoped to the vault."""
    if not path_str:
        return _VAULT_ROOT
    candidate = Path(path_str)
    if not candidate.is_absolute():
        candidate = _VAULT_ROOT / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(_VAULT_ROOT.resolve()):
        raise ValueError(f"Path {path_str} escapes the Obsidian vault.")
    return resolved


def _visible_entries(dir_path: Path):
    """Yield non-hidden, non-system entries under a vault directory."""
    try:
        for entry in sorted(dir_path.iterdir()):
            name = entry.name
            if name.startswith(".") and entry.is_dir():
                continue
            if entry.is_dir() and name in _SKIP_DIRS:
                continue
            yield entry
    except OSError:
        return


def _brief_diff(before: str, after: str, max_lines: int = 12) -> str:
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


def _md_snippet(text: str, max_chars: int = 120) -> str:
    text = text.strip()
    if not text:
        return "(empty note)"
    if len(text) <= max_chars:
        return text
    head = text[: max_chars]
    return head + "\n... [truncated] ..." + text[-40:]


def _sanitize_markdown_title(name: str) -> str:
    name = name.strip().replace("/", "-").replace("\\", "-")
    name = re.sub(r"[<>:\"/\\|?*]", "-", name)
    return name or "untitled"


# ---------------------------------------------------------------------------
# Read / write / list / tree — the core vault manipulation surface.
# ---------------------------------------------------------------------------

def vault_read(args: dict[str, Any]) -> ToolResult:
    path = _resolve_vault(args.get("path"))
    if path.is_dir():
        return ToolResult(success=False, error=f"Is a directory: {path}")
    if not path.exists():
        return ToolResult(success=False, error=f"Note not found: {path.relative_to(_VAULT_ROOT)}")
    size = path.stat().st_size
    if size > _MAX_READ_BYTES:
        return ToolResult(success=False, error=f"Note too large ({size} bytes > {_MAX_READ_BYTES}); refusing to read")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to read {path}: {e}")
    return ToolResult(
        success=True,
        output=truncate(text, _MAX_READ_OUTPUT),
        metadata={
            "path": str(path.relative_to(_VAULT_ROOT)),
            "bytes": size,
            "exists": True,
        },
    )


def vault_write(args: dict[str, Any]) -> ToolResult:
    path = _resolve_vault(args.get("path"))
    if path.is_dir():
        return ToolResult(success=False, error=f"Is a directory: {path}")
    if not path.is_relative_to(_VAULT_ROOT.resolve()):
        return ToolResult(success=False, error="Path is outside the Obsidian vault.")
    content = str(args.get("content", "") or "")
    overwrite = bool(args.get("overwrite", True))
    if path.exists() and not overwrite:
        return ToolResult(success=False, error=(f"Note already exists: {path.relative_to(_VAULT_ROOT)} "
                                               "(set overwrite=true)"))
    if path.exists() and path.is_dir():
        return ToolResult(success=False, error=f"Is a directory: {path}")
    try:
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to write {path}: {e}")
    from core.agent.undo import push_undo_for_write
    push_undo_for_write(
        path,
        before,
        content,
        f"wrote obsidian note {path.relative_to(_VAULT_ROOT)}" + (" (created)" if not before else ""),
    )
    diff = _brief_diff(before, content)
    metadata: dict[str, Any] = {
        "path": str(path.relative_to(_VAULT_ROOT)),
        "chars": len(content),
        "bytes": len(content.encode("utf-8")),
        "exists": path.exists(),
    }
    if diff:
        metadata["diff"] = diff
        metadata["diff_stats"] = _diff_stats(diff)
    return ToolResult(
        success=True,
        output=f"Wrote {len(content)} chars to {path.relative_to(_VAULT_ROOT)}",
        metadata=metadata,
    )


def vault_list(args: dict[str, Any]) -> ToolResult:
    path = _resolve_vault(args.get("path", "."))
    if not path.exists():
        return ToolResult(success=False, error=f"Directory not found: {path.relative_to(_VAULT_ROOT.resolve())}")
    if not path.is_dir():
        return ToolResult(success=False, error=f"Not a directory: {path.relative_to(_VAULT_ROOT.resolve())}")
    detail = bool(args.get("detail", False))
    entries = list(_visible_entries(path))[:_MAX_LIST_ENTRIES]
    lines: list[str] = []
    for entry in entries:
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
        output="\n".join(lines) or "(empty vault)",
        metadata={
            "path": str(path.relative_to(_VAULT_ROOT)),
            "count": len(entries),
            "truncated": len(entries) >= _MAX_LIST_ENTRIES,
        },
    )


def vault_tree(args: dict[str, Any]) -> ToolResult:
    path = _resolve_vault(args.get("path", "."))
    if not path.exists():
        return ToolResult(success=False, error=f"Directory not found: {path.relative_to(_VAULT_ROOT)}")
    if not path.is_dir():
        return ToolResult(success=False, error=f"Not a directory: {path.relative_to(_VAULT_ROOT)}")
    max_depth = int(args.get("max_depth", 3))
    max_entries = int(args.get("max_entries", 200))
    if max_depth < 1:
        return ToolResult(success=False, error=f"max_depth must be >= 1, got {max_depth}")

    lines: list[str] = []
    budget = [max_entries]

    def _walk(current: Path, depth: int, prefix: str) -> None:
        if budget[0] <= 0:
            lines.append(f"{prefix}... (max entries reached)")
            return
        try:
            sorted_entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            lines.append(f"{prefix}(unreadable)")
            return
        for entry in sorted_entries:
            if budget[0] <= 0:
                lines.append(f"{prefix}... (max entries reached)")
                return
            if entry.is_dir():
                if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                    continue
                budget[0] -= 1
                lines.append(f"{prefix}{entry.name}/")
                if depth + 1 < max_depth:
                    _walk(entry, depth + 1, prefix + "  ")
            else:
                budget[0] -= 1
                lines.append(f"{prefix}{entry.name}")

    _walk(path, 0, "")
    return ToolResult(
        success=True,
        output=truncate("\n".join(lines) or "(empty vault)", _MAX_READ_OUTPUT),
        metadata={
            "path": str(path.relative_to(_VAULT_ROOT)),
            "max_depth": max_depth,
            "entries_shown": len(lines),
            "truncated": budget[0] <= 0,
        },
    )


def vault_delete(args: dict[str, Any]) -> ToolResult:
    path = _resolve_vault(args.get("path"))
    if not path.exists():
        return ToolResult(success=False, error=f"Note not found: {path.relative_to(_VAULT_ROOT)}")
    if path.is_dir():
        try:
            next(path.iterdir())
        except StopIteration:
            pass
        except OSError as e:
            return ToolResult(success=False, error=f"Cannot inspect {path}: {e}")
        else:
            return ToolResult(success=False, error=(f"Directory not empty: {path.relative_to(_VAULT_ROOT)}; "
                                                   "refusing to delete"))
        try:
            path.rmdir()
        except OSError as e:
            return ToolResult(success=False, error=f"Failed to delete directory {path}: {e}")
        return ToolResult(
            success=True,
            output=f"Deleted directory {path.relative_to(_VAULT_ROOT)}",
            metadata={"path": str(path.relative_to(_VAULT_ROOT)), "type": "dir"},
        )
    before: str = ""
    try:
        if path.stat().st_size <= 1_000_000:
            before = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        pass
    try:
        path.unlink()
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to delete {path}: {e}")
    from core.agent.undo import push_undo_for_write
    if before:
        push_undo_for_write(
            path, before, "", f"deleted obsidian note {path.relative_to(_VAULT_ROOT)}"
        )
    return ToolResult(
        success=True,
        output=f"Deleted note {path.relative_to(_VAULT_ROOT)}",
        metadata={"path": str(path.relative_to(_VAULT_ROOT)), "type": "file"},
    )


def vault_move(args: dict[str, Any]) -> ToolResult:
    source = _resolve_vault(args.get("source"))
    dest = _resolve_vault(args.get("dest"))
    if not source.exists():
        return ToolResult(success=False, error=f"Source not found: {source.relative_to(_VAULT_ROOT)}")
    if not source.is_relative_to(_VAULT_ROOT.resolve()) or not dest.is_relative_to(_VAULT_ROOT.resolve()):
        return ToolResult(success=False, error="Source and destination must be inside the Obsidian vault.")
    if dest.exists() and dest.is_dir():
        dest = dest / source.name
    overwrite = bool(args.get("overwrite", False))
    if dest.exists() and not overwrite:
        return ToolResult(success=False, error=(f"Destination exists: {dest.relative_to(_VAULT_ROOT)} "
                                               "(set overwrite=true)"))
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        source.rename(dest)
    except (OSError, ValueError) as e:
        return ToolResult(success=False, error=(f"Failed to move {source.relative_to(_VAULT_ROOT)} to "
                                               f"{dest.relative_to(_VAULT_ROOT)}: {e}"))
    return ToolResult(
        success=True,
        output=f"Moved {source.relative_to(_VAULT_ROOT)} to {dest.relative_to(_VAULT_ROOT)}",
        metadata={"source": str(source.relative_to(_VAULT_ROOT)), "dest": str(dest.relative_to(_VAULT_ROOT))},
    )


def vault_create(args: dict[str, Any]) -> ToolResult:
    title = str(args.get("title", "")).strip() or "untitled"
    name = _sanitize_markdown_title(title) + ".md"
    path = _VAULT_ROOT / name
    if path.exists():
        return ToolResult(success=False, error=f"Note already exists: {name} (use vault.write with overwrite=true)")
    try:
        path.write_text(f"# {title}\n\n", encoding="utf-8")
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to create note {name}: {e}")
    from core.agent.undo import push_undo_for_write
    push_undo_for_write(
        path, "", f"# {title}\n\n", f"created obsidian note {name}"
    )
    return ToolResult(
        success=True,
        output=f"Created note {name}",
        metadata={"path": name, "title": title, "bytes": len(f"# {title}\n\n".encode())},
    )


def vault_read_index(args: dict[str, Any]) -> ToolResult:
    """Return the agent-maintained note index (titles, last modified, tags)."""
    if not IDX.is_file():
        return ToolResult(success=True, output="(no cached vault index yet)", metadata={"indexed": 0})
    try:
        data = IDX.read_text(encoding="utf-8", errors="replace")
        import json as _json
        parsed = _json.loads(data)
        return ToolResult(
            success=True,
            output=truncate(_json.dumps(parsed, indent=2), _MAX_READ_OUTPUT),
            metadata={"indexed": len(parsed.get("notes", []))},
        )
    except (OSError, ValueError) as e:
        return ToolResult(success=False, error=f"Failed to read vault index: {e}")


def vault_list_notes(args: dict[str, Any]) -> ToolResult:
    """List only markdown notes (not directories), with size and mtime."""
    path = _resolve_vault(args.get("path", "."))
    if not path.exists():
        return ToolResult(success=False, error=f"Directory not found: {path.relative_to(_VAULT_ROOT)}")
    if not path.is_dir():
        return ToolResult(success=False, error=f"Not a directory: {path.relative_to(_VAULT_ROOT)}")
    lines: list[str] = []
    count = 0
    for entry in _visible_entries(path):
        if entry.is_dir():
            continue
        if entry.suffix.lower() != ".md":
            continue
        if count >= _MAX_LIST_ENTRIES:
            lines.append("(more notes not shown)")
            break
        try:
            st = entry.stat()
            lines.append(f"{entry.name}\t{st.st_size}\t{st.st_mtime:.0f}")
        except OSError:
            lines.append(f"{entry.name}\t?\t?")
        count += 1
    return ToolResult(
        success=True,
        output="\n".join(lines) or "(no markdown notes)",
        metadata={"path": str(path.relative_to(_VAULT_ROOT)), "count": count, "truncated": count >= _MAX_LIST_ENTRIES},
    )


def vault_search(args: dict[str, Any]) -> ToolResult:
    """Plain-text search across markdown notes in the vault."""
    query = str(args.get("query", "")).strip()
    if not query:
        return ToolResult(success=False, error="query is required")
    case_sensitive = bool(args.get("case_sensitive", False))
    path = _resolve_vault(args.get("path", "."))
    if not path.exists():
        return ToolResult(success=False, error=f"Directory not found: {path.relative_to(_VAULT_ROOT)}")
    results: list[dict[str, Any]] = []
    pattern = re.compile(re.escape(query), 0 if case_sensitive else re.IGNORECASE)
    for entry in _visible_entries(path):
        if not entry.is_file():
            continue
        if entry.suffix.lower() != ".md":
            continue
        if entry.stat().st_size > _MAX_READ_BYTES:
            continue
        try:
            text = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matches = [m.start() for m in pattern.finditer(text)]
        if not matches:
            continue
        snippets: list[str] = []
        for pos in matches[:3]:
            start = max(0, pos - 60)
            end = min(len(text), pos + 120)
            snippets.append("..." + text[start:end].replace("\n", " ") + "...")
        results.append({
            "path": str(entry.relative_to(_VAULT_ROOT)),
            "hits": len(matches),
            "snippet": "\n".join(snippets),
        })
    return ToolResult(
        success=True,
        output="\n".join(
            (f"{r['path']}  ({r['hits']} hit{'s' if r['hits'] != 1 else ''})"
             + (f"\n{r['snippet']}" if r["snippet"] else ""))
            for r in results
        ) or f"No matches for '{query}'",
        metadata={"query": query, "hits": sum(r["hits"] for r in results), "files": [r["path"] for r in results]},
    )


def vault_rebuild_index(args: dict[str, Any]) -> ToolResult:
    """Rebuild the agent-side note index from the vault on disk."""
    try:
        notes: list[dict[str, Any]] = []
        for entry in _visible_entries(_VAULT_ROOT):
            if not entry.is_file() or entry.suffix.lower() != ".md":
                continue
            try:
                st = entry.stat()
                text = entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            title = (text.splitlines() or [""])[0].lstrip("# ").strip() or entry.name
            tags = sorted({t for t in re.findall(r"#[\w-]+", text)})
            notes.append({
                "path": str(entry.relative_to(_VAULT_ROOT)),
                "name": entry.name,
                "title": title,
                "bytes": st.st_size,
                "mtime": st.st_mtime,
                "tags": tags,
            })
        data = {"vault": str(_VAULT_ROOT), "notes": notes}
        IDX.parent.mkdir(parents=True, exist_ok=True)
        IDX.write_text(
            (__import__("json", fromlist=["json"]).dumps(data, indent=2)),
            encoding="utf-8",
        )
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to rebuild vault index: {e}")
    return ToolResult(
        success=True,
        output=f"Indexed {len(notes)} notes in the Obsidian vault",
        metadata={"indexed": len(notes), "index_path": str(IDX.relative_to(_VAULT_ROOT))},
    )


def vault_diff(args: dict[str, Any]) -> ToolResult:
    a = _resolve_vault(args.get("file_a"))
    b = _resolve_vault(args.get("file_b"))
    for p, label in ((a, "file_a"), (b, "file_b")):
        if not p.exists():
            return ToolResult(success=False, error=f"{label} not found: {p.relative_to(_VAULT_ROOT)}")
        if p.is_dir():
            return ToolResult(success=False, error=f"{label} is a directory: {p.relative_to(_VAULT_ROOT)}")
        if not p.is_relative_to(_VAULT_ROOT.resolve()):
            return ToolResult(success=False, error=f"{label} is outside the Obsidian vault.")
    try:
        text_a = a.read_text(encoding="utf-8", errors="replace")
        text_b = b.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return ToolResult(success=False, error=f"Failed to read notes for diff: {e}")
    diff_lines = list(difflib.unified_diff(
        text_a.splitlines(), text_b.splitlines(),
        fromfile=str(a.relative_to(_VAULT_ROOT)), tofile=str(b.relative_to(_VAULT_ROOT)), lineterm="",
    ))
    stats = _diff_stats("\n".join(diff_lines))
    identical = not diff_lines
    output = "\n".join(diff_lines) if diff_lines else "(notes are identical)"
    return ToolResult(
        success=True,
        output=truncate(output, _MAX_READ_OUTPUT),
        metadata={
            "file_a": str(a.relative_to(_VAULT_ROOT)),
            "file_b": str(b.relative_to(_VAULT_ROOT)),
            "added": stats["added"],
            "removed": stats["removed"],
            "identical": identical,
        },
    )


__all__ = [
    "vault_read",
    "vault_write",
    "vault_list",
    "vault_tree",
    "vault_delete",
    "vault_move",
    "vault_create",
    "vault_read_index",
    "vault_list_notes",
    "vault_search",
    "vault_rebuild_index",
    "vault_diff",
]
