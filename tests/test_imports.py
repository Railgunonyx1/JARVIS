"""Import guards for the Phase 1 controlled demolition.

Sprint 1 quarantined the legacy voice/vision/desktop subsystems
(``pipeline/``, ``actions/``, ``voice_engine/``) and later deleted them
entirely. These tests ensure they are never resurrected at their old path.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUARANTINED = ("pipeline", "actions", "voice_engine")


def test_quarantined_packages_removed_from_tree():
    for name in QUARANTINED:
        assert not (ROOT / name).exists(), (
            f"{name}/ was removed in Phase 1 — do not resurrect it."
        )


def test_surviving_entry_surface_does_not_import_quarantined():
    import cli.main  # noqa: F401
    from core.agent.loop import AgentLoop  # noqa: F401
    from memory.mem import get_mem  # noqa: F401
    from runtime.startup_profile import StartupProfiler  # noqa: F401

    for name in QUARANTINED:
        assert name not in sys.modules, (
            f"surviving entry surface eagerly imports quarantined package {name!r}"
        )
