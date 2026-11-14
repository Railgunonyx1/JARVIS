"""Regression tests for packaging/desktop/install-kwin-rule.sh.

The helper used to pass a bare ``--file kwinrc`` to ``kwriteconfig6``/``kwriteconfig5``.
Those tools resolve a relative file name against ``$XDG_CONFIG_HOME`` (falling back
to ``$HOME/.config``) rather than the working directory, so the native backends wrote
a different file than the ``python3`` branch and than ``KWINRC_PATH`` -- while the
helper still reported ``Enabled in: $KWINRC``.

These tests pin the corrected contract: every backend receives one absolute path,
that path honours ``KWINRC_PATH`` and then ``XDG_CONFIG_HOME``, and the parent
directory is created when missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "packaging" / "desktop" / "install-kwin-rule.sh"
PAYLOAD = REPO_ROOT / "packaging" / "desktop" / "kwin" / "jarvis-island"

FAKE_BACKEND = """#!/bin/sh
log=${KWIN_ARGV_LOG:?}
printf '%s\\n' "backend=__NAME__" >> "$log"
printf '%s\\n' "$@" >> "$log"
printf '%s\\n' '---' >> "$log"
file=
key=
value=
prev=
for a in "$@"; do
    case "$prev" in
        --file) file=$a ;;
        --key) key=$a ;;
    esac
    prev=$a
    value=$a
done
if [ -n "$file" ]; then
    {
        printf '[Plugins]\\n'
        printf '%s=%s\\n' "$key" "$value"
    } > "$file"
fi
exit 0
"""

QDBUS_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "${KWIN_QDBUS_LOG:-/dev/null}"
exit 0
"""


def _write_executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _fake_backend_bin(tmp_path: Path, *, name: str = "kwriteconfig6") -> tuple[Path, Path]:
    """Fake KDE config writer that mirrors the real tool's absolute-path handling."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    _write_executable(bin_dir / name, FAKE_BACKEND.replace("__NAME__", name))
    # The helper probes kwriteconfig6 before kwriteconfig5, so the other native
    # tool must be absent from PATH (not merely failing) for a clean selection.
    other = "kwriteconfig5" if name == "kwriteconfig6" else "kwriteconfig6"
    assert not (bin_dir / other).exists()
    for tool in ("dirname", "mkdir", "rm", "cp", "cat", "python3"):
        real = shutil.which(tool)
        if real is not None and not (bin_dir / tool).exists():
            (bin_dir / tool).symlink_to(real)
    _write_executable(bin_dir / "qdbus6", QDBUS_STUB)
    _write_executable(bin_dir / "qdbus", QDBUS_STUB)
    return bin_dir, tmp_path / "argv.log"


def _restricted_bin(tmp_path: Path) -> Path:
    """PATH containing the utilities the helper needs but no kwriteconfig6/5."""
    bin_dir = tmp_path / "restricted-bin"
    bin_dir.mkdir(exist_ok=True)
    for tool in ("dirname", "mkdir", "rm", "cp", "cat", "python3"):
        real = shutil.which(tool)
        if real is not None:
            link = bin_dir / tool
            if not link.exists():
                link.symlink_to(real)
    return bin_dir


def _run(
    tmp_path: Path,
    *,
    path_dir: Path,
    kwinrc_path: str | None,
    xdg_config_home: Path | None,
    argv_log: Path | None = None,
    args: tuple[str, ...] = (),
    cwd: Path | None = None,
    include_system_path: bool = False,
) -> subprocess.CompletedProcess[str]:
    workdir = tmp_path / "cwd"
    workdir.mkdir(exist_ok=True)
    search = [str(path_dir)]
    if include_system_path:
        search += ["/usr/bin", "/bin"]
    env = {
        "PATH": os.pathsep.join(search),
        "HOME": str(tmp_path / "fake-home"),
        "XDG_CURRENT_DESKTOP": "KDE",
        "KWIN_SCRIPT_DIR": str(tmp_path / "kwin-scripts"),
        "KWIN_QDBUS_LOG": str(tmp_path / "qdbus.log"),
    }
    if xdg_config_home is not None:
        env["XDG_CONFIG_HOME"] = str(xdg_config_home)
    if kwinrc_path is not None:
        env["KWINRC_PATH"] = kwinrc_path
    if argv_log is not None:
        env["KWIN_ARGV_LOG"] = str(argv_log)
    (tmp_path / "fake-home").mkdir(exist_ok=True)
    return subprocess.run(
        ["/bin/sh", str(HELPER), *args],
        cwd=str(cwd or workdir),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _argv_log_entries(log: Path) -> list[list[str]]:
    entries: list[list[str]] = []
    current: list[str] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if line == "---":
            entries.append(current)
            current = []
        else:
            current.append(line)
    return entries


def test_kwrite6_receives_absolute_kwinrc_not_bare_name(tmp_path: Path) -> None:
    bin_dir, argv_log = _fake_backend_bin(tmp_path)
    target = tmp_path / "kwinrc-path" / "kwinrc"
    xdg = tmp_path / "xdg"

    result = _run(
        tmp_path,
        path_dir=bin_dir,
        kwinrc_path=str(target),
        xdg_config_home=xdg,
        argv_log=argv_log,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    entry = _argv_log_entries(argv_log)[0]
    assert entry[0] == "backend=kwriteconfig6"
    file_value = entry[entry.index("--file") + 1]
    assert file_value == str(target)
    assert file_value.startswith("/")
    assert file_value != "kwinrc"
    assert target.read_text(encoding="utf-8").splitlines()[-1] == "jarvis-islandEnabled=true"
    # The divergence is gone: nothing was written where kwriteconfig6 alone would have.
    assert not (xdg / "kwinrc").exists()
    assert f"Enabled in: {target}" in result.stdout


def test_kwrite5_receives_absolute_kwinrc(tmp_path: Path) -> None:
    bin_dir, argv_log = _fake_backend_bin(tmp_path, name="kwriteconfig5")
    target = tmp_path / "kwinrc-path" / "kwinrc"

    result = _run(
        tmp_path,
        path_dir=bin_dir,
        kwinrc_path=str(target),
        xdg_config_home=tmp_path / "xdg",
        argv_log=argv_log,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    entry = _argv_log_entries(argv_log)[0]
    assert entry[0] == "backend=kwriteconfig5"
    assert entry[entry.index("--file") + 1] == str(target)
    assert target.read_text(encoding="utf-8").splitlines()[-1] == "jarvis-islandEnabled=true"


def test_default_kwinrc_follows_xdg_config_home(tmp_path: Path) -> None:
    bin_dir, argv_log = _fake_backend_bin(tmp_path)
    xdg = tmp_path / "xdg"

    result = _run(
        tmp_path,
        path_dir=bin_dir,
        kwinrc_path=None,
        xdg_config_home=xdg,
        argv_log=argv_log,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected = xdg / "kwinrc"
    entry = _argv_log_entries(argv_log)[0]
    assert entry[entry.index("--file") + 1] == str(expected)
    assert expected.is_file()
    assert not (tmp_path / "fake-home" / ".config" / "kwinrc").exists()


def test_relative_kwinrc_path_is_absolutised_against_cwd(tmp_path: Path) -> None:
    bin_dir, argv_log = _fake_backend_bin(tmp_path)
    workdir = tmp_path / "cwd"

    result = _run(
        tmp_path,
        path_dir=bin_dir,
        kwinrc_path="rel/kwinrc",
        xdg_config_home=tmp_path / "xdg",
        argv_log=argv_log,
        cwd=workdir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected = workdir / "rel" / "kwinrc"
    entry = _argv_log_entries(argv_log)[0]
    assert entry[entry.index("--file") + 1] == str(expected)
    assert expected.is_file()


def test_python_fallback_writes_the_kwinrc_path(tmp_path: Path) -> None:
    bin_dir = _restricted_bin(tmp_path)
    target = tmp_path / "kwinrc-path" / "kwinrc"
    xdg = tmp_path / "xdg"

    result = _run(
        tmp_path,
        path_dir=bin_dir,
        kwinrc_path=str(target),
        xdg_config_home=xdg,
        include_system_path=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert target.read_text(encoding="utf-8").splitlines()[-1] == "jarvis-islandEnabled=true"
    assert not (xdg / "kwinrc").exists()


def test_python_fallback_creates_missing_parent_directory(tmp_path: Path) -> None:
    """Regression: the fallback used to abort with FileNotFoundError after staging."""
    bin_dir = _restricted_bin(tmp_path)
    target = tmp_path / "does" / "not" / "exist" / "kwinrc"

    result = _run(
        tmp_path,
        path_dir=bin_dir,
        kwinrc_path=str(target),
        xdg_config_home=None,
        include_system_path=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "FileNotFoundError" not in result.stderr
    assert target.is_file()
    assert target.read_text(encoding="utf-8").splitlines()[-1] == "jarvis-islandEnabled=true"


def test_uninstall_clears_the_same_file_and_removes_payload(tmp_path: Path) -> None:
    bin_dir, argv_log = _fake_backend_bin(tmp_path)
    target = tmp_path / "kwinrc-path" / "kwinrc"
    scripts_dir = tmp_path / "kwin-scripts"

    installed = _run(
        tmp_path,
        path_dir=bin_dir,
        kwinrc_path=str(target),
        xdg_config_home=tmp_path / "xdg",
        argv_log=argv_log,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert (scripts_dir / "jarvis-island" / "metadata.json").is_file()
    assert (scripts_dir / "jarvis-island" / "contents" / "code" / "main.js").is_file()

    removed = _run(
        tmp_path,
        path_dir=bin_dir,
        kwinrc_path=str(target),
        xdg_config_home=tmp_path / "xdg",
        argv_log=argv_log,
        args=("--uninstall",),
    )

    assert removed.returncode == 0, removed.stdout + removed.stderr
    last = _argv_log_entries(argv_log)[-1]
    assert last[last.index("--file") + 1] == str(target)
    assert last[-1] == "false"
    assert target.read_text(encoding="utf-8").splitlines()[-1] == "jarvis-islandEnabled=false"
    assert not (scripts_dir / "jarvis-island").exists()
    # reconfigure goes through the stub, never the live session bus
    assert (tmp_path / "qdbus.log").is_file()


@pytest.mark.skipif(
    shutil.which("kwriteconfig6") is None,
    reason="kwriteconfig6 is not installed on this host",
)
def test_real_kwriteconfig6_writes_the_helper_target(tmp_path: Path) -> None:
    """The real tool must write exactly the path the helper advertises."""
    real_dir = Path(shutil.which("kwriteconfig6") or "").parent
    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()
    _write_executable(stub_dir / "qdbus6", QDBUS_STUB)
    _write_executable(stub_dir / "qdbus", QDBUS_STUB)
    path_dir = tmp_path / "path-bin"
    path_dir.mkdir()
    # Stub first so reconfigure cannot reach the running compositor.
    env_path = f"{stub_dir}:{path_dir}:{real_dir}:/usr/bin:/bin"

    target = tmp_path / "kwinrc-path" / "kwinrc"
    xdg = tmp_path / "xdg"
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    (tmp_path / "fake-home").mkdir()

    env = {
        "PATH": env_path,
        "HOME": str(tmp_path / "fake-home"),
        "XDG_CONFIG_HOME": str(xdg),
        "XDG_CURRENT_DESKTOP": "KDE",
        "KWIN_SCRIPT_DIR": str(tmp_path / "kwin-scripts"),
        "KWINRC_PATH": str(target),
        "KWIN_QDBUS_LOG": str(tmp_path / "qdbus.log"),
    }
    result = subprocess.run(
        ["/bin/sh", str(HELPER)],
        cwd=str(workdir),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert target.read_text(encoding="utf-8").splitlines()[-1] == "jarvis-islandEnabled=true"
    assert not (xdg / "kwinrc").exists(), "real kwriteconfig6 wrote outside KWINRC_PATH"
    assert str(target) in result.stdout
    assert PAYLOAD.is_dir()
    assert os.access(target, os.W_OK)
