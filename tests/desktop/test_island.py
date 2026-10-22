"""Tests for the JARVIS Desktop Dynamic Island overlay."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "jarvis-desktop")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

os.environ.setdefault("JARVIS_DESKTOP_HOME", "/tmp/jarvis-island-test")

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_island_constructs_idle(qapp):
    from app.ui.overlay_window import IslandState, IslandWindow
    island = IslandWindow()
    island.show()
    qapp.processEvents()
    assert island._state is IslandState.IDLE
    assert island._card.width() == 180
    island.close()


def test_island_expand_collapse(qapp):
    from app.ui.overlay_window import IslandState, IslandWindow
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
    assert island.y() == geo.top() + 8
    island.close()


def test_island_hide_and_quit_lifecycle(qapp):
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    island.show()
    island.hide_island()
    assert island.isHidden() is True

    called = []

    class _FakeCoord:
        def shutdown(self):
            called.append(True)

    island._controller = type("C", (), {"coordinator": _FakeCoord()})()
    island.quit_application()
    assert called == [True]


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
    mod = _load_launcher("jarvis-desktop-island-launcher.py")
    desktop, repo = mod._resolve()
    assert desktop == os.path.join(_REPO_ROOT, "jarvis-desktop")
    assert repo == _REPO_ROOT
    assert os.path.isfile(os.path.join(desktop, "app", "island_main.py"))


def test_launcher_falls_back_to_installed_home(tmp_path, monkeypatch):
    mod = _load_launcher("jarvis-desktop-island-launcher.py")
    isolated = tmp_path / "bin"
    isolated.mkdir()
    monkeypatch.setattr(mod, "__file__", str(isolated / "jarvis-desktop-island-launcher.py"))
    monkeypatch.setenv("JARVIS_DESKTOP_HOME", str(tmp_path / "home"))
    desktop, repo = mod._resolve()
    assert desktop == str(tmp_path / "home" / "jarvis-repo" / "jarvis-desktop")
    assert repo == str(tmp_path / "home" / "jarvis-repo")


def test_settings_update_preserves_unrelated_keys(tmp_path, monkeypatch):
    from app import settings
    monkeypatch.setattr(settings, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    settings.save({**settings.DEFAULTS, "autostart_enabled": True, "model": "a"})
    merged = settings.update({"model": "b", "voice_enabled": False})
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
    thread.join(5)
    assert box.get("decision") == "once"
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
    assert island._approval_result is not None
    island.hide_island()
    thread.join(5)
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
