"""Regression tests for installed autostart and uninstall behaviour."""

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


def _run_uninstaller(
    tmp_path: Path, *, kwin_marker: bool, mime_cache: str | None = None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    repo_root = Path(__file__).resolve().parents[2]
    install_dir = tmp_path / "install"
    repo_dir = install_dir / "jarvis-repo"
    helper_dir = repo_dir / "packaging" / "desktop"
    helper_dir.mkdir(parents=True)
    helper = helper_dir / "install-kwin-rule.sh"
    helper.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$1\" >> \"$KWIN_CALL_LOG\"\n",
        encoding="utf-8",
    )
    helper.chmod(0o755)

    marker = repo_dir / ".kwin-helper-installed"
    if kwin_marker:
        marker.touch()

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    autostart = bin_dir / "jarvis-autostart"
    autostart.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    autostart.chmod(0o755)

    desktop_dir = tmp_path / "applications"
    icon_dir = tmp_path / "icons"
    config_home = tmp_path / "config"
    for path in (desktop_dir, icon_dir, config_home / "autostart"):
        path.mkdir(parents=True, exist_ok=True)

    if mime_cache is not None:
        (desktop_dir / "mimeinfo.cache").write_text(mime_cache, encoding="utf-8")

    # Stub update-desktop-database: it rewrites mimeinfo.cache from the real
    # desktop entries, which would replace the fixture and hide the behaviour
    # under test (our own cache cleanup, not the database tool's).
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    stub = stub_dir / "update-desktop-database"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)

    call_log = tmp_path / "kwin-calls.log"
    env = os.environ.copy()
    env.update(
        {
            "INSTALL_DIR": str(install_dir),
            "BIN_DIR": str(bin_dir),
            "DESKTOP_DIR": str(desktop_dir),
            "ICON_DIR": str(icon_dir),
            "XDG_CONFIG_HOME": str(config_home),
            "KWIN_CALL_LOG": str(call_log),
            "PATH": f"{stub_dir}{os.pathsep}{env.get('PATH', '')}",
        }
    )
    result = subprocess.run(
        ["bash", str(repo_root / "packaging" / "desktop" / "uninstall.sh")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, call_log


def test_uninstaller_preserves_unowned_kwin_integration(tmp_path: Path) -> None:
    result, call_log = _run_uninstaller(tmp_path, kwin_marker=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not call_log.exists()


def test_uninstaller_removes_owned_kwin_integration(tmp_path: Path) -> None:
    result, call_log = _run_uninstaller(tmp_path, kwin_marker=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert call_log.read_text(encoding="utf-8").strip() == "--uninstall"


def test_uninstaller_removes_header_only_mime_cache(tmp_path: Path) -> None:
    result, _ = _run_uninstaller(tmp_path, kwin_marker=False, mime_cache="[MIME Cache]\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "applications" / "mimeinfo.cache").exists()
    assert (tmp_path / "applications").is_dir()


def test_uninstaller_keeps_mime_cache_with_foreign_entries(tmp_path: Path) -> None:
    cache = "[MIME Cache]\nimage/png=another-app.desktop;\n"
    result, _ = _run_uninstaller(tmp_path, kwin_marker=False, mime_cache=cache)
    assert result.returncode == 0, result.stdout + result.stderr
    kept = tmp_path / "applications" / "mimeinfo.cache"
    assert kept.is_file()
    assert kept.read_text(encoding="utf-8") == cache
