"""Portable desktop application launcher tests."""

from __future__ import annotations

from types import SimpleNamespace

from app.desktop.actions import DesktopActionLayer


def test_kde_terminal_prefers_konsole(monkeypatch):
    calls = []
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setattr(
        "app.desktop.actions.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"konsole", "foot"} else None,
    )
    monkeypatch.setattr(
        "app.desktop.actions.subprocess.Popen",
        lambda args, **kwargs: calls.append((args, kwargs)),
    )

    assert DesktopActionLayer._launch_terminal() is True
    assert calls[0][0] == ["/usr/bin/konsole"]


def test_terminal_falls_back_to_available_candidate(monkeypatch):
    calls = []
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setattr(
        "app.desktop.actions.shutil.which",
        lambda name: "/usr/bin/kitty" if name == "kitty" else None,
    )
    monkeypatch.setattr(
        "app.desktop.actions.subprocess.Popen",
        lambda args, **kwargs: calls.append(args),
    )

    assert DesktopActionLayer._launch_terminal() is True
    assert calls == [["/usr/bin/kitty"]]


def test_terminal_returns_false_when_no_candidate_exists(monkeypatch):
    monkeypatch.setattr("app.desktop.actions.shutil.which", lambda _name: None)

    assert DesktopActionLayer._launch_terminal() is False


def test_browser_uses_system_default(monkeypatch):
    calls = []

    def fake_open(url, new=0):
        calls.append((url, new))
        return True

    monkeypatch.setattr("app.desktop.actions.webbrowser.open", fake_open)

    assert DesktopActionLayer._launch_browser() is True
    assert calls == [("about:blank", 2)]



def test_window_maximize_uses_wmctrl_state_syntax(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.desktop.actions.subprocess.run", fake_run)
    layer = DesktopActionLayer()

    assert layer.execute("window_maximize") is True
    assert calls[0][0] == [
        "wmctrl", "-r", ":ACTIVE:", "-b", "add,maximized_vert,maximized_horz"
    ]


def test_window_minimize_uses_wmctrl_state_syntax(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.desktop.actions.subprocess.run", fake_run)
    layer = DesktopActionLayer()

    assert layer.execute("window_minimize") is True
    assert calls[0][0] == ["wmctrl", "-r", ":ACTIVE:", "-b", "add,hidden"]


def test_window_close_still_requires_confirmation(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.desktop.actions.subprocess.run", fake_run)
    layer = DesktopActionLayer()

    assert layer.execute("window_close") is False
    assert calls == []
    assert layer.execute("window_close", confirmed=True) is True
    assert calls[0][0] == ["wmctrl", "-c", ":ACTIVE:"]
