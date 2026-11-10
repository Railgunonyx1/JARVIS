"""Import guards for the Dynamic Island application and shared AI runtime."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUARANTINED = ("pipeline", "actions", "voice_engine", "cli", "jbrowser", "orbit")


def test_removed_product_surfaces_stay_removed():
    for name in ("cli", "jbrowser", "orbit", "orbit-browser", "jbrowser-bridge", "extensions"):
        assert not (ROOT / name).exists(), f"Removed product surface unexpectedly exists: {name}/"


def test_dynamic_island_and_agent_runtime_importable():
    island = ROOT / "dynamic-island"
    sys.path.insert(0, str(island))
    sys.path.insert(0, str(ROOT))
    import app.main  # noqa: F401
    from core.agent.loop import AgentLoop  # noqa: F401
    from memory.mem import get_mem  # noqa: F401
    from runtime.startup_profile import StartupProfiler  # noqa: F401

    for name in QUARANTINED:
        assert name not in sys.modules, f"Unexpected legacy package imported: {name!r}"


def test_core_daemon_events_importable():
    from core.daemon.events import _emit, make_session_id, make_trace_id

    ev = _emit("intent.classified", {"x": 1}, session_id=make_session_id(), trace_id=make_trace_id())
    assert ev["name"] == "intent.classified"
    assert ev["session_id"].startswith("sess_")


def test_core_daemon_package_import_does_not_require_phantom_modules():
    import core.daemon as daemon

    assert hasattr(daemon, "JARVISDaemon")
    assert hasattr(daemon, "get_daemon")
    assert "core.daemon.plugins" not in sys.modules
    assert "core.tool_execution_service" not in sys.modules
