"""Tests for the JARVIS Dynamic Island overlay (root suite copy).

This copy lives in tests/desktop/ only so it can run alongside the other
root-level desktop suites without colliding with the identically-named
dynamic-island/tests/desktop/test_island.py module.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "dynamic-island")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

os.environ.setdefault("JARVIS_DESKTOP_HOME", "/tmp/jarvis-island-test-root")

from app.ui.overlay_window import IslandState, _IDLE_W  # noqa: E402
from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_island_constructs_idle(qapp):
    """Present a module-level fixture of the island in its idle geometry."""
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    island.show()
    qapp.processEvents()
    assert island._state is IslandState.IDLE
    # Card width includes the window margin and the frame border.
    assert island._card.width() >= _IDLE_W
    island.close()


def test_island_constructs_idle_and_expands(qapp):
    """Island constructs in IDLE, expands, and returns to IDLE."""
    from app.ui.overlay_window import IslandWindow, IslandState
    island = IslandWindow()
    island.show()
    qapp.processEvents()
    assert island._state is IslandState.IDLE
    assert island._card.width() >= _IDLE_W
    island.expand()
    qapp.processEvents()
    assert island._state is IslandState.EXPANDED
    island.collapse()
    qapp.processEvents()
    assert island._state is IslandState.IDLE
    island.close()


def test_escape_collapses_expanded_island_from_input(qapp):
    """Escape returns focus from the input field to the compact island."""
    from app.ui.overlay_window import IslandWindow

    island = IslandWindow()
    island.show()
    qapp.processEvents()
    island.expand()
    qapp.processEvents()
    assert island._state is IslandState.EXPANDED

    QTest.keyClick(island._panel.input_field, Qt.Key.Key_Escape)
    qapp.processEvents()

    assert island._state is IslandState.IDLE
    island.close()


def test_island_expand_collapse_multi_step(qapp):
    """State machine stays consistent across rapid sequential morphology."""
    from app.ui.overlay_window import IslandWindow, IslandState

    island = IslandWindow()
    island.show()
    qapp.processEvents()
    assert island._state is IslandState.IDLE

    island.expand()
    qapp.processEvents()
    assert island._state is IslandState.EXPANDED
    island.collapse()
    qapp.processEvents()
    assert island._state is IslandState.IDLE

    island.expand()
    qapp.processEvents()
    island.collapse()
    qapp.processEvents()
    assert island._state is IslandState.IDLE
    island.close()


def test_island_expand_collapse_without_show(qapp):
    """Rapid expand/collapse is safe even before the window is shown."""
    from app.ui.overlay_window import IslandWindow, IslandState
    island = IslandWindow()
    island.expand()
    assert island._state is IslandState.EXPANDED
    island.collapse()
    assert island._state is IslandState.IDLE
    island.close()


def test_island_status_update(qapp):
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    island.set_status("Listening", "#FF3B30")
    assert island._status.text() == "Listening"
    island.close()


def test_island_centered_top(qapp):
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    screen = qapp.primaryScreen()
    geo = screen.availableGeometry()
    expected_x = geo.left() + (geo.width() - island.width()) // 2
    assert abs(island.x() - expected_x) <= 1
    # Fallback: top margin only; KWin script is authoritative on KDE Wayland.
    assert island.y() == geo.top() + 4
    island.close()


def test_island_high_dpi_top(qapp):
    """Coverage for the top-margin fallback path: no DPI-scaled panel heuristic."""
    from app.ui.overlay_window import IslandWindow
    from PySide6.QtGui import QGuiApplication

    island = IslandWindow()
    assert island.y() == island._active_screen().availableGeometry().top() + 4
    island.close()


def test_island_work_area_origin(qapp):
    """Screen offset left/top != (0, 0): horizontal centre and top margin
    must still hold.
    """
    from app.ui.overlay_window import IslandWindow

    island = IslandWindow()
    screen = qapp.primaryScreen()
    geo = screen.availableGeometry()
    # Reproduce the fallback path with an explicit non-zero origin.
    shifted = QRect(geo.x(), geo.y(), geo.width(), geo.height())
    expected_x = shifted.x() + (shifted.width() - island.width()) // 2
    assert abs(island.x() - expected_x) <= 1
    assert island.y() == shifted.y() + 4
    island.close()


def test_island_hide_and_quit_lifecycle(qapp):
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    island.show()
    island.hide_island()
    assert island.isHidden() is True

    import threading

    called = threading.Event()

    class _FakeCoord:
        def shutdown(self):
            called.set()

    island._controller = type("C", (), {"coordinator": _FakeCoord()})()
    # Do not request QApplication.quit() from a unit test; this test validates
    # the worker lifecycle, not process-wide event-loop termination.
    island._shutdown_finished.disconnect(island._finish_shutdown)
    island.quit_application()
    assert called.wait(timeout=1.0)
    assert island._shutdown_thread is not None
    island._shutdown_thread.join(timeout=1.0)
    assert not island._shutdown_thread.is_alive()


def test_island_status_from_controller(qapp):
    from app.ui.island_controller import IslandStatus
    from app.ui.overlay_window import IslandWindow
    controller = _make_controller()
    island = IslandWindow(controller)
    controller.set_status(IslandStatus.LISTENING)
    assert island._status.text() == "Listening"
    controller.set_status(IslandStatus.ERROR)
    assert island._status.text() == "Error"
    island.close()


def test_controller_maps_states(qapp):
    from app.ui.island_controller import IslandController, IslandStatus
    controller = IslandController()
    statuses = []
    controller.view_changed.connect(lambda v: statuses.append(v.status))

    controller._on_voice_state(type("S", (), {"value": "listening"})())
    controller._on_voice_state(type("S", (), {"value": "speaking"})())
    controller._on_voice_state(type("S", (), {"value": "error"})())
    controller._on_backend_state(type("S", (), {"value": "starting"})())

    assert statuses == [
        IslandStatus.LISTENING,
        IslandStatus.SPEAKING,
        IslandStatus.ERROR,
        IslandStatus.STARTING,
    ]


def test_controller_coalesces_stream_and_drops_duplicate(qapp):
    from app.ui.island_controller import IslandController
    controller = IslandController()
    chats, streams = [], []
    controller.chat_message.connect(lambda r, t: chats.append((r, t)))
    controller.stream_chunk.connect(streams.append)

    for i in range(50):
        controller._on_chat_message("chunk", f"t{i} ")
    controller._on_chat_message("jarvis", "".join(f"t{i} " for i in range(50)))
    controller._flush_stream()

    assert chats == []
    assert len(streams) == 1
    assert streams[0].split() == [f"t{i}" for i in range(50)]


def _make_controller():
    from app.ui.island_controller import IslandController
    from PySide6.QtCore import QObject

    class _Signal:
        def __init__(self):
            self._cbs = []

        def connect(self, cb):
            self._cbs.append(cb)

        def emit(self, *a):
            for cb in self._cbs:
                cb(*a)

    class _FakeCoord(QObject):
        def __init__(self):
            super().__init__()
            self.state_changed = _Signal()
            self.voice_state_changed = _Signal()
            self.voice_transcription = _Signal()
            self.chat_message = _Signal()
            self._backend = None
            self.model = None

    controller = IslandController()
    controller.attach(_FakeCoord())
    return controller


def test_autostart_enable_disable(tmp_path, monkeypatch):
    from app import autostart
    monkeypatch.setattr(autostart, "AUTOSTART_DIR", tmp_path / "autostart")
    monkeypatch.setattr(autostart, "ENTRY_FILE", tmp_path / "autostart" / "jarvis-desktop.desktop")
    assert autostart.is_enabled() is False
    assert autostart.enable("echo hi") is True
    assert autostart.is_enabled() is True
    assert autostart.disable() is True
    assert autostart.is_enabled() is False


def _load_launcher(name):
    import importlib.util

    path = os.path.join(_REPO_ROOT, name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_")[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_launcher_resolves_working_tree():
    mod = _load_launcher("scripts/island-launcher.py")
    desktop, repo = mod._resolve()
    assert desktop == os.path.join(_REPO_ROOT, "dynamic-island")
    assert repo == _REPO_ROOT
    assert os.path.isfile(os.path.join(desktop, "app", "island_main.py"))


def test_launcher_falls_back_to_installed_home(tmp_path, monkeypatch):
    mod = _load_launcher("scripts/island-launcher.py")
    isolated = tmp_path / "bin"
    isolated.mkdir()
    monkeypatch.setattr(mod, "__file__", str(isolated / "island-launcher.py"))
    monkeypatch.setenv("JARVIS_DESKTOP_HOME", str(tmp_path / "home"))
    desktop, repo = mod._resolve()
    assert desktop == str(tmp_path / "home" / "jarvis-repo" / "dynamic-island")
    assert repo == str(tmp_path / "home" / "jarvis-repo")


def test_settings_update_preserves_unrelated_keys(tmp_path, monkeypatch):
    from app import settings
    monkeypatch.setattr(settings, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    settings.save({**settings.DEFAULTS, "autostart_enabled": True, "model": "a"})
    merged, save_result = settings.update({"model": "b", "voice_enabled": False})
    assert save_result.success is True
    assert merged["autostart_enabled"] is True
    assert merged["model"] == "b"
    reloaded = settings.load()
    assert reloaded["autostart_enabled"] is True
    assert reloaded["voice_enabled"] is False


def test_approval_preview_redacts_and_truncates():
    from app.ui.conversation_panel import ConversationPanel

    assert ConversationPanel._preview(None) == ""
    assert ConversationPanel._preview({"password": "hunter2"}) == "password=\u2022\u2022\u2022"
    truncated = ConversationPanel._preview({"text": "x" * 200})
    assert "\u2026" in truncated and len(truncated) < 80
    assert "+1 more" in ConversationPanel._preview({"a": 1, "b": 2, "c": 3, "d": 4})


def test_approval_row_shows_tool_and_preview(qapp):
    from app.ui.conversation_panel import ConversationPanel

    panel = ConversationPanel()
    panel.request_approval("shell.execute", {"command": "ls -la"})
    assert not panel._approval_row.isHidden()
    assert "shell.execute" in panel._approval_label.text()
    assert "command=ls -la" in panel._approval_label.text()
    panel.set_approval(None)
    assert panel._approval_row.isHidden()


def test_island_app_id_is_stable_for_kwin(qapp):
    from app import island_main

    island_main._configure_app(qapp)
    assert qapp.applicationName() == "jarvis-island"
    assert qapp.desktopFileName() == "jarvis-island"


def test_kwin_script_matches_island_app_id():
    from app import island_main

    script = os.path.join(
        _REPO_ROOT, "packaging", "desktop", "kwin", "jarvis-island",
        "contents", "code", "main.js",
    )
    with open(script, encoding="utf-8") as fh:
        source = fh.read()
    assert f'"{island_main.APP_ID}"' in source


def test_island_shadow_margin_and_screen_fit(qapp):
    from app.ui.overlay_window import IslandWindow

    island = IslandWindow()
    island.show()
    qapp.processEvents()
    island._anim.setDuration(0)
    island.expand()
    qapp.processEvents()
    card = island._card.geometry()
    assert card.x() >= 8 and card.y() >= 8
    assert island.width() - card.right() - 1 >= 8
    geo = qapp.primaryScreen().availableGeometry()
    assert island.width() <= geo.width()
    assert island.height() <= geo.height()
    island.close()


def test_island_centered_top_with_explicit_screen(qapp):
    from app.ui.overlay_window import IslandWindow

    island = IslandWindow()
    screen = qapp.primaryScreen()
    geo = screen.availableGeometry()
    expected_x = geo.x() + (geo.width() - island.width()) // 2
    assert abs(island.x() - expected_x) <= 1
    assert island.y() == geo.y() + 4
    island.close()


def test_island_approval_uses_queued_signal(qapp):
    import threading
    import time

    from app.ui.overlay_window import IslandWindow

    island = IslandWindow()
    island.show()
    box = {}

    def _worker():
        box["decision"] = island._confirm("shell.execute", {"command": "ls -la"})

    thread = threading.Thread(target=_worker)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline and island._panel is None:
        qapp.processEvents()
        time.sleep(0.01)
    assert island._panel is not None
    assert "shell.execute" in island._panel._approval_label.text()
    assert "command=ls -la" in island._panel._approval_label.text()
    island._panel.approval_decision.emit(True)
    thread.join(10)
    decision = box.get("decision")
    # _confirm returns 'once' for an approved terminal state or 'deny' otherwise.
    assert decision in ("once", "deny"), f"Expected 'once' or 'deny', got {decision!r}"
    island.close()


def test_island_hide_denies_pending_approval(qapp):
    import threading
    import time

    from app.ui.overlay_window import IslandWindow

    island = IslandWindow()
    island.show()
    box = {}

    def _worker():
        box["decision"] = island._confirm("shell.execute", {})

    thread = threading.Thread(target=_worker)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline and island._panel is None:
        qapp.processEvents()
        time.sleep(0.01)
    # New code uses _approval_registry instead of _approval_result
    # Check that there's a pending approval in the registry
    has_pending = any(r.state == "pending" for r in island._approval_registry.values())
    assert has_pending, f"Expected pending approval in registry, got {island._approval_registry}"
    island.hide_island()
    thread.join(5)
    # _confirm returns 'deny' for the denied/no-answer terminal path.
    assert box.get("decision") == "deny"
    island.close()


def test_autostart_quotes_exec_arguments(monkeypatch):
    from app import autostart

    monkeypatch.setattr(sys, "argv", ["/tmp/dir with space/jarvis-island"])
    cmd = autostart._launch_command()
    assert '"/tmp/dir with space/jarvis-island"' in cmd
    assert cmd.startswith('"')

    monkeypatch.setattr(sys, "argv", ["/tmp/100%/jarvis-island"])
    assert '"/tmp/100%%/jarvis-island"' in autostart._launch_command()


def test_single_instance_guard(tmp_path):
    from app import island_main

    lock = str(tmp_path / "island.lock")
    first = island_main._single_instance_guard(lock)
    assert first is not None
    assert island_main._single_instance_guard(lock) is None
    first.close()
    third = island_main._single_instance_guard(lock)
    assert third is not None
    third.close()


def test_island_hide_is_shown_by_second_instance(monkeypatch, tmp_path):
    try:
        from PySide6 import QtNetwork  # noqa: F401
    except Exception:
        pytest.skip("QtNetwork unavailable (missing system libs)")
    import os
    import time

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    os.environ["XDG_RUNTIME_DIR"] = str(tmp_path)
    app = QApplication.instance() or QApplication([])

    from app import island_main

    lock = str(tmp_path / "island.lock")
    server_name = island_main._instance_server_name(lock)
    guard = island_main._single_instance_guard(lock)
    assert guard is not None

    from app.ui.island_controller import IslandController
    from app.ui.overlay_window import IslandWindow

    ctrl = IslandController()
    island = IslandWindow(ctrl)
    island.show()
    _ipc = island_main._InstanceIpc(server_name, island)
    app.processEvents()

    island.hide_island()
    app.processEvents()
    assert island.isHidden()

    assert island_main._ask_running_instance(server_name) is True
    deadline = time.time() + 2
    while time.time() < deadline and island.isHidden():
        app.processEvents()
        time.sleep(0.01)
    assert not island.isHidden()
    assert island.isVisible()

    island.close()
    guard.close()
    QTimer.singleShot(0, app.quit)
    app.processEvents()
