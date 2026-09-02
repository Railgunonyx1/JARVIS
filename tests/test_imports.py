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


def test_core_daemon_events_importable():
    """core.daemon.events must import without crashing.

    model_gateway and harness_selector do `from core.daemon.events import _emit`
    at runtime. Importing the package must not fail on optional/phantom
    dependencies (e.g. a missing prefix_cache plugin or a top-level
    core/tool_execution_service module).
    """
    from core.daemon.events import (
        _emit,
        make_session_id,
        make_trace_id,
    )

    ev = _emit("intent.classified", {"x": 1}, session_id=make_session_id(), trace_id=make_trace_id())
    assert ev["name"] == "intent.classified"
    assert ev["session_id"].startswith("sess_")


def test_core_daemon_package_import_does_not_require_phantom_modules():
    """Importing core.daemon must succeed even though the legacy optional
    modules (core.daemon.plugins.prefix_cache, core.tool_execution_service)
    are not present. Those are resolved lazily only when JARVISDaemon is
    constructed, which nothing currently does.
    """
    import core.daemon as daemon

    assert hasattr(daemon, "JARVISDaemon")
    assert hasattr(daemon, "get_daemon")

    # The legacy optional modules are resolved lazily only when JARVISDaemon
    # is constructed (nothing currently constructs it). They must not be
    # loaded as a side-effect of importing the package.
    assert "core.daemon.plugins" not in sys.modules
    assert "core.tool_execution_service" not in sys.modules
