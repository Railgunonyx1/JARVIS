"""Daemon spawn survival tests (Block 0 — Daemon Spawn Survival).

Proves the P0: a daemon spawned via ``daemon.lifecycle._spawn`` keeps running
after the process that spawned it (the terminal/caller) terminates. On Windows
this depends on escaping the console's kill-on-close Job object — via WMI
reparenting, breakaway, or plain detach — and on POSIX on ``setsid``.

The harness starts a short-lived *caller* subprocess that runs the real
``_spawn`` path to launch a tiny marker "daemon" (a child that reports its PID
and parent PID, then idles until a stop file appears). The caller exits; the
test then asserts the marker is still alive and has been reparented away from
it. No full kernel is started and the real ``~/.jarvis`` registry is never
touched.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daemon.lifecycle import _spawn  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Marker "daemon": report pid + parent pid, then idle until the stop file
# appears (or a hard deadline). Written as a file so the caller can pass it
# to a real child interpreter without quoting pain.
_MARKER = """\
import json, os, sys, time
import psutil
out_path, stop_path = sys.argv[1], sys.argv[2]
max_seconds = float(sys.argv[3])
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({"pid": os.getpid(), "parent_pid": psutil.Process().ppid()}, f)
deadline = time.monotonic() + max_seconds
while time.monotonic() < deadline:
    if os.path.exists(stop_path):
        break
    time.sleep(0.1)
"""

# Caller: exercises the real spawn path and exits immediately, simulating the
# terminal closing right after `jarvis daemon start`.
_CALLER = """\
import sys
sys.path.insert(0, {root!r})
from daemon.lifecycle import _spawn
_spawn([sys.executable, {marker!r}, {out!r}, {stop!r}, {max_seconds!r}],
       cwd={root!r})
"""


def _launch_caller(tmp_path, max_seconds=90):
    """Spawn the short-lived caller, wait for it to exit, return its pid."""
    marker = tmp_path / "marker_daemon.py"
    out = tmp_path / "alive.json"
    stop = tmp_path / "stop.flag"
    caller = tmp_path / "caller.py"
    marker.write_text(_MARKER, encoding="utf-8")
    caller.write_text(
        _CALLER.format(root=str(ROOT), marker=str(marker), out=str(out),
                       stop=str(stop), max_seconds=str(max_seconds)),
        encoding="utf-8",
    )
    proc = subprocess.Popen([sys.executable, str(caller)], cwd=str(ROOT))
    proc.wait(timeout=120)
    assert proc.returncode == 0, f"caller exited with {proc.returncode}"
    return proc.pid, out, stop


def _wait_for_report(out_path, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if out_path.exists():
                return json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    raise AssertionError(f"marker daemon never reported its pid: {out_path}")


def _wait_dead(pid, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and psutil.pid_exists(pid):
        time.sleep(0.1)
    return not psutil.pid_exists(pid)


def _wait_alive(pid, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not psutil.pid_exists(pid):
        time.sleep(0.1)
    return psutil.pid_exists(pid)


@pytest.mark.skipif(
    not hasattr(_spawn, "__call__"),
    reason="spawn path unavailable in this environment",
)
def test_spawned_daemon_survives_caller_exit(tmp_path):
    """The daemon must outlive the process that spawned it."""
    caller_pid, out, stop = _launch_caller(tmp_path)

    info = _wait_for_report(out)
    daemon_pid = int(info["pid"])
    assert daemon_pid != caller_pid
    assert daemon_pid != os.getpid()

    # The caller (terminal harness) has already exited — now confirm the
    # daemon both stays alive and was reparented away from the dead caller.
    assert not psutil.pid_exists(caller_pid), "caller should be gone"
    assert _wait_alive(daemon_pid), "daemon died with its caller"
    time.sleep(1.0)
    assert psutil.pid_exists(daemon_pid), "daemon did not survive the caller"
    assert psutil.Process(daemon_pid).ppid() != caller_pid, (
        "daemon still reports the dead caller as parent (not reparented)")

    try:
        stop.write_text("stop", encoding="utf-8")
        assert _wait_dead(daemon_pid), "marker daemon ignored its stop file"
    finally:
        if psutil.pid_exists(daemon_pid):
            psutil.Process(daemon_pid).kill()


def test_spawn_wmi_used_first_on_windows(monkeypatch):
    """On Windows the WMI reparent strategy is tried before the fallback."""
    if os.name != "nt":
        pytest.skip("WMI spawn is Windows-only")

    calls = {"wmi": 0, "popen": 0}
    from daemon import lifecycle

    def fake_wmi(command, cwd):
        calls["wmi"] += 1
        return False  # simulate WMI being unavailable

    real_popen = lifecycle.subprocess.Popen

    def fake_popen(*args, **kwargs):
        calls["popen"] += 1
        flags = kwargs.get("creationflags", 0)
        assert flags & 0x08000000, "CREATE_NO_WINDOW missing on fallback"
        assert flags & 0x00000008, "DETACHED_PROCESS missing on fallback"
        assert flags & 0x00000200, "CREATE_NEW_PROCESS_GROUP missing on fallback"

        class _FakeProc:
            def __init__(self):
                pass

        return _FakeProc()

    monkeypatch.setattr(lifecycle, "_spawn_wmi", fake_wmi)
    monkeypatch.setattr(lifecycle.subprocess, "Popen", fake_popen)
    lifecycle._spawn([sys.executable, "-c", "pass"], cwd=str(ROOT))

    assert calls["wmi"] == 1, "WMI must be attempted first"
    assert calls["popen"] == 1, "fallback must launch the process"
    monkeypatch.setattr(lifecycle.subprocess, "Popen", real_popen)


def test_spawn_falls_back_through_all_strategies_on_windows(monkeypatch):
    """When WMI and breakaway both fail, the plain-detach fallback still runs."""
    if os.name != "nt":
        pytest.skip("Windows-only spawn fallback chain")

    calls = {"popen": 0}
    from daemon import lifecycle

    monkeypatch.setattr(lifecycle, "_spawn_wmi", lambda command, cwd: False)

    real_popen = lifecycle.subprocess.Popen

    def fake_popen(*args, **kwargs):
        calls["popen"] += 1
        if calls["popen"] == 1:
            raise OSError("job forbids breakaway")
        flags = kwargs.get("creationflags", 0)
        assert flags & 0x08000000, "CREATE_NO_WINDOW missing on detach fallback"

        class _FakeProc:
            pass

        return _FakeProc()

    monkeypatch.setattr(lifecycle.subprocess, "Popen", fake_popen)
    lifecycle._spawn([sys.executable, "-c", "pass"], cwd=str(ROOT))
    assert calls["popen"] == 2, "breakaway + detach fallback both attempted"
    monkeypatch.setattr(lifecycle.subprocess, "Popen", real_popen)
