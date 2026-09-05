"""JARVIS Orbit — selective-memory facade (G12).

Binds the canonical :class:`memory.store.MemoryStore` to the Orbit profile
directory and hands out a single ``get_orbit_memory()`` instance, mirroring
the ``get_orbit_controller()`` singleton discipline: every ``orbit.memory_*``
tool routes through here, and tests inject a throwaway store by seeding the
singleton with an explicit ``data_dir`` first.

Stable identity + ownership live in :mod:`memory.keyspace` (constellation
keyspace: ``user.*`` / ``agent.<id>.*`` / ``system.*``); BLOB mode (binary
artifacts) is a first-class store surface that never appears in text recall.
"""

from __future__ import annotations

import threading
from pathlib import Path

from memory.store import MemoryStore

# Orbit profile directory (gitignored runtime state; Chromium profile + memory).
ORBIT_DATA_DIR = Path("config/browser_profiles/orbit") / "memory"


_orbit_memory: MemoryStore | None = None
_orbit_memory_lock = threading.Lock()


def get_orbit_memory(data_dir: Path | None = None) -> MemoryStore:
    """Module-level singleton memory store bound to the Orbit profile.

    Pass ``data_dir`` on first call to point tests at a temp directory.
    """
    global _orbit_memory
    if _orbit_memory is None:
        with _orbit_memory_lock:
            if _orbit_memory is None:
                _orbit_memory = MemoryStore(data_dir=data_dir or ORBIT_DATA_DIR)
    return _orbit_memory


def reset_orbit_memory() -> None:
    """Drop the singleton (for tests / shutdown)."""
    global _orbit_memory
    if _orbit_memory is not None:
        try:
            _orbit_memory.shutdown()
        except Exception:  # noqa: BLE001 - teardown is best-effort
            pass
    _orbit_memory = None
