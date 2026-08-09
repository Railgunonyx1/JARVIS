"""File Manager — full file system control for JARVIS MK-X.

Capabilities: create, read, write, delete, copy, move, rename, list, search, info.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional

from core.utils import get_project_root

logger = logging.getLogger("jarvis.actions.file_manager")

# Safety: restrict operations to user directories
HOME = Path.home()
ALLOWED_ROOTS = [
    get_project_root(),            # JARVIS workspace
    HOME / "Desktop",
    HOME / "Documents",
    HOME / "Downloads",
    HOME / ".jarvis",              # data dir
]


def _safe_path(path_str: str) -> Path:
    """Resolve path and enforce access restrictions."""
    p = Path(path_str).expanduser().resolve()
    for root in ALLOWED_ROOTS:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    logger.warning("Blocked access to restricted path: %s -> %s", path_str, p)
    raise PermissionError(f"Access denied: path outside allowed directories: {p}")


def _get_desktop() -> Path:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        return Path(winreg.QueryValueEx(key, "Desktop")[0])
    except Exception:
        return HOME / "Desktop"


def file_action(action: str, parameters: dict, **kwargs) -> str:
    """Dispatch file operations."""
    handlers = {
        "list": _list_dir,
        "read": _read_file,
        "write": _write_file,
        "create": _create_file,
        "delete": _delete,
        "copy": _copy,
        "move": _move,
        "rename": _rename,
        "search": _search,
        "info": _file_info,
        "exists": _exists,
        "mkdir": _make_dir,
        "size": _dir_size,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown file action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("File action '%s' failed: %s", action, e)
        return f"File operation failed: {e}"


def _list_dir(params: dict) -> str:
    path = _safe_path(params.get("path", str(HOME / "Desktop")))
    if not path.exists():
        return f"Directory not found: {path}"
    if not path.is_dir():
        return f"Not a directory: {path}"

    entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    lines = []
    for entry in entries[:100]:  # Limit to 100 entries
        prefix = "[DIR] " if entry.is_dir() else "      "
        try:
            size = entry.stat().st_size
            if size > 1024 * 1024:
                size_str = f"{size / (1024*1024):.1f} MB"
            elif size > 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} B"
        except Exception:
            size_str = "?"
        lines.append(f"{prefix}{entry.name}  ({size_str})")

    if len(entries) > 100:
        lines.append(f"... and {len(entries) - 100} more items")

    return f"Contents of {path}:\n" + "\n".join(lines) if lines else f"Empty directory: {path}"


def _read_file(params: dict) -> str:
    path = _safe_path(params.get("path", ""))
    if not path.exists():
        return f"File not found: {path}"
    if path.is_dir():
        return f"Cannot read a directory: {path}"

    max_size = params.get("max_size", 50_000)
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_size:
            return content[:max_size] + f"\n... (truncated, total {len(content)} chars)"
        return content
    except Exception as e:
        return f"Cannot read file: {e}"


def _write_file(params: dict) -> str:
    path = _safe_path(params.get("path", ""))
    content = params.get("content", "")
    mode = params.get("mode", "w")  # w=overwrite, a=append

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, mode, encoding="utf-8") as f:
            f.write(content)
        return f"Written {len(content)} chars to {path}"
    except Exception as e:
        return f"Write failed: {e}"


def _create_file(params: dict) -> str:
    path = _safe_path(params.get("path", ""))
    content = params.get("content", "")

    if path.exists():
        return f"File already exists: {path}"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Created {path}"
    except Exception as e:
        return f"Create failed: {e}"


def _delete(params: dict) -> str:
    path = _safe_path(params.get("path", ""))
    if not path.exists():
        return f"Not found: {path}"

    try:
        if path.is_dir():
            shutil.rmtree(path)
            return f"Deleted directory: {path}"
        else:
            path.unlink()
            return f"Deleted file: {path}"
    except Exception as e:
        return f"Delete failed: {e}"


def _copy(params: dict) -> str:
    src = _safe_path(params.get("source", ""))
    dst = _safe_path(params.get("destination", ""))
    if not src.exists():
        return f"Source not found: {src}"

    try:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return f"Copied {src.name} to {dst}"
    except Exception as e:
        return f"Copy failed: {e}"


def _move(params: dict) -> str:
    src = _safe_path(params.get("source", ""))
    dst = _safe_path(params.get("destination", ""))
    if not src.exists():
        return f"Source not found: {src}"

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved {src.name} to {dst}"
    except Exception as e:
        return f"Move failed: {e}"


def _rename(params: dict) -> str:
    src = _safe_path(params.get("path", ""))
    new_name = params.get("new_name", "")
    if not src.exists():
        return f"Not found: {src}"
    if not new_name:
        return "No new name provided"

    dst = src.parent / new_name
    try:
        src.rename(dst)
        return f"Renamed to {dst.name}"
    except Exception as e:
        return f"Rename failed: {e}"


def _search(params: dict) -> str:
    query = params.get("query", "").lower()
    search_path = _safe_path(params.get("path", str(HOME / "Desktop")))
    max_results = params.get("max_results", 20)

    if not query:
        return "No search query provided"

    results = []
    try:
        for root, dirs, files in os.walk(search_path):
            for name in files + dirs:
                if query in name.lower():
                    full = Path(root) / name
                    results.append(str(full))
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break
    except PermissionError:
        pass

    if results:
        return f"Found {len(results)} matches:\n" + "\n".join(results)
    return f"No files matching '{query}' found in {search_path}"


def _file_info(params: dict) -> str:
    path = _safe_path(params.get("path", ""))
    if not path.exists():
        return f"Not found: {path}"

    stat = path.stat()
    import datetime
    modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    created = datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
    size = stat.st_size

    if size > 1024 * 1024:
        size_str = f"{size / (1024*1024):.1f} MB"
    elif size > 1024:
        size_str = f"{size / 1024:.1f} KB"
    else:
        size_str = f"{size} B"

    kind = "Directory" if path.is_dir() else "File"
    return f"{kind}: {path}\nSize: {size_str}\nModified: {modified}\nCreated: {created}"


def _exists(params: dict) -> str:
    path = _safe_path(params.get("path", ""))
    if path.exists():
        kind = "directory" if path.is_dir() else "file"
        return f"Exists ({kind}): {path}"
    return f"Not found: {path}"


def _make_dir(params: dict) -> str:
    path = _safe_path(params.get("path", ""))
    try:
        path.mkdir(parents=True, exist_ok=True)
        return f"Created directory: {path}"
    except Exception as e:
        return f"Mkdir failed: {e}"


def _dir_size(params: dict) -> str:
    path = _safe_path(params.get("path", "."))
    if not path.is_dir():
        return f"Not a directory: {path}"

    total = 0
    count = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
                count += 1
            except Exception:
                pass

    if total > 1024 * 1024 * 1024:
        size_str = f"{total / (1024**3):.1f} GB"
    elif total > 1024 * 1024:
        size_str = f"{total / (1024**2):.1f} MB"
    elif total > 1024:
        size_str = f"{total / 1024:.1f} KB"
    else:
        size_str = f"{total} B"

    return f"{path}: {size_str}, {count} files"
