"""Regression tests for the installed-layout autostart command."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_installed_autostart_enable_status_disable(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    staged_root = tmp_path / "jarvis-repo"
    scripts_dir = staged_root / "scripts"
    app_dir = staged_root / "dynamic-island" / "app"
    scripts_dir.mkdir(parents=True)
    app_dir.mkdir(parents=True)

    shutil.copy2(repo_root / "scripts" / "jarvis-autostart", scripts_dir / "jarvis-autostart")
    shutil.copy2(repo_root / "dynamic-island" / "app" / "__init__.py", app_dir / "__init__.py")
    shutil.copy2(repo_root / "dynamic-island" / "app" / "autostart.py", app_dir / "autostart.py")

    config_home = tmp_path / "config"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["XDG_CONFIG_HOME"] = str(config_home)
    command = [sys.executable, str(scripts_dir / "jarvis-autostart")]

    launcher = tmp_path / "bin" / "jarvis-desktop-island"
    enabled = subprocess.run(
        [*command, "enable", "--run", str(launcher)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert enabled.returncode == 0, enabled.stdout + enabled.stderr
    assert "Autostart enabled" in enabled.stdout

    entry = config_home / "autostart" / "jarvis-desktop.desktop"
    assert entry.is_file()
    assert f"Exec={str(launcher)}" in entry.read_text(encoding="utf-8")

    status = subprocess.run(
        [*command, "status"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert status.returncode == 0, status.stdout + status.stderr
    assert "autostart enabled" in status.stdout

    disabled = subprocess.run(
        [*command, "disable"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert disabled.returncode == 0, disabled.stdout + disabled.stderr
    assert "Autostart disabled" in disabled.stdout
    assert not entry.exists()
