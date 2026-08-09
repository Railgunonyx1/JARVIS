"""Import guards for the Phase 1 controlled demolition.

Sprint 1 quarantined the legacy voice/vision/desktop subsystems
(``pipeline/``, ``actions/``, ``voice_engine/``) into ``_quarantine_removed/``
as JARVIS pivots to a terminal-native engineering agent. These tests:

1. Fail if any quarantined package is resurrected at its old path.
2. Fail if the surviving entry surface ever imports a quarantined package
   eagerly (they must stay out of ``sys.modules`` after boot imports).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUARANTINED = ("pipeline", "actions", "voice_engine")
QUARANTINE_DIR = ROOT / "_quarantine_removed"


def test_quarantined_packages_removed_from_tree():
    for name in QUARANTINED:
        assert not (ROOT / name).exists(), (
            f"{name}/ was quarantined in Phase 1 (see {QUARANTINE_DIR.name}/) — "
            "do not resurrect it."
        )


def test_quarantine_archive_present():
    assert QUARANTINE_DIR.is_dir(), "missing _quarantine_removed/ archive"
    for name in QUARANTINED:
        assert (QUARANTINE_DIR / name).is_dir(), (
            f"{name} is missing from the quarantine archive"
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
