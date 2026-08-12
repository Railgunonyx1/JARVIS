"""Kernel runtime state snapshots.

A lightweight, JSON-friendly representation of what the daemon kernel was
doing. The persistent daemon writes a snapshot under ``~/.jarvis/state/`` on
shutdown (and after each task) so a freshly connecting client can show
"last known state" before any real work happens.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["RuntimeState", "save_snapshot", "load_snapshot"]


@dataclass
class RuntimeState:
    """Immutable-ish snapshot of kernel state at a point in time."""

    project_id: str = ""
    project: str = ""
    mode: str = "agent"
    provider: str = ""
    model: str = ""
    tools: int = 0
    mem_stats: dict[str, Any] = field(default_factory=dict)
    last_goal: str = ""
    last_result: str | None = None  # "completed" | "failed" | None
    last_trace_id: str = ""
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    pid: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeState:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


def save_snapshot(state: RuntimeState, path: Path) -> None:
    """Write a snapshot atomically (tmp file + rename)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(state.to_dict(), indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def load_snapshot(path: Path) -> RuntimeState | None:
    """Read a snapshot, returning ``None`` when missing or corrupt."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeState.from_dict(data)
    except (OSError, ValueError):
        return None
