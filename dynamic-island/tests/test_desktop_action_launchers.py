"""Portable desktop application launcher tests."""

from __future__ import annotations

import subprocess

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
