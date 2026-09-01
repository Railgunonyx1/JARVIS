"""Observability configuration — environment-driven, no heavy imports.

Two-mode philosophy:

    Production   JARVIS_TRACE=0  → no spans, no DB, ~0 ns overhead
    Performance  JARVIS_TRACE=1  → spans in memory; daemon persists to SQLite

The tracer is on by default so request timelines travel with every result; set
``JARVIS_TRACE=0`` to disable span creation entirely. The performance database
lives outside the repository under ``~/.jarvis/perf.db`` (override with
``JARVIS_OBSERVABILITY_DB``) so runtime data is never committed to git.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["JARVIS_HOME", "perf_db_path", "trace_enabled"]

JARVIS_HOME = Path.home() / ".jarvis"


def perf_db_path() -> Path:
    """Performance database path (``JARVIS_OBSERVABILITY_DB`` overrides)."""
    env = os.environ.get("JARVIS_OBSERVABILITY_DB")
    if env:
        return Path(env)
    return JARVIS_HOME / "perf.db"


def trace_enabled() -> bool:
    """Span creation is on unless ``JARVIS_TRACE=0``."""
    return os.environ.get("JARVIS_TRACE", "1") != "0"
