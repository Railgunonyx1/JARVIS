"""Project identity for JARVIS daemons.

A daemon is bound to one project (memory, tools, and workspace index are
project-specific), so the CLI must only reuse a daemon whose project matches
the current working directory. Identity is a stable fingerprint derived from
the git root when available, else the resolved absolute path (case-folded on
Windows so C:/Foo and c:/foo match).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

__all__ = ["find_git_root", "project_id", "project_label"]


def find_git_root(path: Path) -> Path | None:
    """Walk up from ``path`` looking for a ``.git`` directory (or file)."""
    current = path.resolve()
    if current.is_file():
        current = current.parent
    for parent in (current, *current.parents):
        if (parent / ".git").exists():
            return parent
    return None


def project_id(path: Path) -> str:
    """Deterministic short identity for a project path."""
    resolved = Path(path).resolve()
    root = find_git_root(resolved) or resolved
    key = str(root)
    if os.name == "nt":
        key = key.lower()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def project_label(path: Path) -> str:
    """Human-readable label for logs/status (dir name + short id)."""
    return f"{Path(path).name or str(path)}"
