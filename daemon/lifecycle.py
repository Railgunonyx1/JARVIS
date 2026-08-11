"""Process-level daemon lifecycle control (client side, synchronous).

The CLI uses these helpers to discover a matching daemon, spawn one detached,
stop one, or report status. All network I/O is blocking-with-timeout so the
terminal bootstrap never hangs.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from daemon.project import project_id
from daemon.state import PROTOCOL_VERSION, list_entries, load_entry, remove_entry
from runtime.transport.protocol import decode_line, encode_line

# Full path to powershell.exe to avoid PATH-order hijack of the WMI spawner.
_WINDOWS_POWERSHELL = (
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    if os.name == "nt" else "powershell"
)

__all__ = [
    "entry_healthy",
    "find_matching",
    "start_daemon",
    "stop_daemon",
    "restart_daemon",
    "daemon_status",
    "list_daemons",
    "sweep_stale_entries",
]

ROOT = Path(__file__).resolve().parents[1]

logger = logging.getLogger("jarvis.lifecycle")

# DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW — no console,
# survives parent exit, and never flashes a window even if DETACHED_PROCESS is
# ignored for a GUI-subsystem child.
_WIN_DETACH_FLAGS = 0x00000008 | 0x00000200 | 0x08000000
# CREATE_BREAKAWAY_FROM_JOB — escape an inherited Job object so the daemon is
# not killed when the spawning shell's job closes (common under terminals that
# put commands in a kill-on-close job). Fails with ERROR_ACCESS_DENIED when the
# current job forbids breakaway; fall back to a WMI-spawn (see _spawn_wmi).
_WIN_BREAKAWAY_FLAG = 0x01000000


def _env(type_: str, payload: dict | None = None,
         id_: str = "lifecycle") -> dict:
    return {
        "version": PROTOCOL_VERSION,
        "id": id_,
        "type": type_,
        "timestamp": time.time(),
        "payload": payload or {},
    }


def _readline(sock: socket.socket) -> bytes:
    buffer = b""
    while b"\n" not in buffer:
        try:
            chunk = sock.recv(4096)
        except OSError:
            return buffer
        if not chunk:
            return buffer
        buffer += chunk
        if len(buffer) > (1 << 20):
            break
    return buffer


def _round_trip(entry: dict, message: dict, timeout: float = 2.0) -> object | None:
    """One authenticated request/response. Returns the decoded response or None."""
    try:
        sock = socket.create_connection(("127.0.0.1", entry["port"]), timeout=timeout)
    except OSError:
        return None
    try:
        sock.settimeout(timeout)
        sock.sendall(encode_line(_env("auth", {"token": entry.get("token", "")})))
        line = _readline(sock)
        if not line or decode_line(line).type != "ok":
            return None
        sock.sendall(encode_line(message))
        line = _readline(sock)
        if not line:
            return None
        return decode_line(line)
    except OSError:
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        return True  # cannot verify — let the ping decide


def entry_healthy(entry: dict) -> bool:
    if not _pid_alive(int(entry.get("pid", -1))):
        return False
    response = _round_trip(entry, _env("ping"))
    return response is not None and response.type == "pong"


def find_matching(project_dir: str) -> dict | None:
    """Return a healthy daemon entry for this project, else None."""
    pid = project_id(Path(project_dir))
    entry = load_entry(pid)
    if entry is None:
        return None
    if entry_healthy(entry):
        return entry
    remove_entry(pid)
    return None


def start_daemon(project_dir: str, port: int | None = None,
                 log_path: str | None = None, timeout: float = 30.0) -> dict | None:
    """Start (or reuse) a detached daemon for the project and wait until ready."""
    project_dir = str(Path(project_dir).resolve())
    pid = project_id(Path(project_dir))
    existing = load_entry(pid)
    if existing and entry_healthy(existing):
        return existing
    if existing:
        remove_entry(pid)

    command = [sys.executable, "-m", "daemon.server", "start",
               "--project-dir", project_dir]
    if port:
        command += ["--port", str(port)]
    if log_path:
        command += ["--log", log_path]

    try:
        _spawn(command, cwd=str(ROOT))
    except OSError as exc:
        raise RuntimeError(f"failed to spawn daemon: {exc}") from exc

    deadline = time.time() + timeout
    while time.time() < deadline:
        entry = load_entry(pid)
        if entry and entry_healthy(entry):
            return entry
        time.sleep(0.1)
    return None


def _spawn(command: list, cwd: str) -> None:
    """Start the detached daemon, escaping any inherited Job object.

    Terminal harnesses place commands inside a kill-on-close Job object, so a
    plain ``CreateProcess`` child dies when the spawning command's job closes
    — even with ``CREATE_BREAKAWAY_FROM_JOB``, which can silently fail to
    actually escape. On Windows we therefore spawn through the WMI provider
    first: ``Win32_Process.Create`` creates the process as a child of
    ``WmiPrvSE.exe``, outside the caller's job entirely. ``CreateProcess``
    (with breakaway) remains the fallback for machines where WMI/PowerShell
    is unavailable.
    """
    if os.name == "nt":
        if _spawn_wmi(command, cwd):
            logger.info("spawn: ok strategy=wmi cmd=%s cwd=%s", command, cwd)
            return
        logger.warning("spawn: wmi failed, trying breakaway cmd=%s", command)
        try:
            subprocess.Popen(
                command,
                cwd=cwd,
                creationflags=_WIN_DETACH_FLAGS | _WIN_BREAKAWAY_FLAG,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            logger.info("spawn: ok strategy=breakaway cmd=%s", command)
            return
        except OSError as exc:
            # Job forbids breakaway — fall through to the plain detach below.
            logger.warning("spawn: breakaway failed (%s), falling back to "
                           "plain detach cmd=%s", exc, command)
    logger.info("spawn: ok strategy=detached cmd=%s", command)
    subprocess.Popen(
        command,
        cwd=cwd,
        creationflags=_WIN_DETACH_FLAGS if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )


def _spawn_wmi(command: list, cwd: str) -> bool:
    """Spawn ``command`` outside the caller's Job via Win32_Process.Create.

    The created process is a child of the WMI provider (``WmiPrvSE.exe``), so
    it inherits the user's machine environment instead of the caller's. API
    keys live in ``config/.env`` on disk, so the daemon still finds them.
    """
    cmdline = subprocess.list2cmdline(command)
    cwd_escaped = str(Path(cwd)).replace("'", "''")
    script = (
        "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
        "-Arguments @{ CommandLine = '" + cmdline.replace("'", "''") + "'; "
        "CurrentDirectory = '" + cwd_escaped + "' }; "
        "if ($r.ReturnValue -ne 0) { exit 1 }"
    )
    logger.info("spawn: wmi attempting create cmd=%s", cmdline)
    try:
        result = subprocess.run(
            [_WINDOWS_POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30.0,
            check=False,
        )
        if result.returncode != 0:
            logger.warning("spawn: wmi failed returncode=%s cmd=%s",
                           result.returncode, cmdline)
        return result.returncode == 0
    except Exception as exc:
        logger.warning("spawn: wmi raised %r cmd=%s", exc, cmdline)
        return False


def _kill(entry: dict) -> None:
    try:
        import psutil

        psutil.Process(int(entry["pid"])).terminate()
    except Exception:
        pass


def stop_daemon(project_dir: str) -> bool:
    """Stop the daemon for a project. Returns True when none is running."""
    pid = project_id(Path(project_dir))
    entry = load_entry(pid)
    if entry is None:
        return True
    response = _round_trip(entry, _env("shutdown"))
    if response is None:
        _kill(entry)
    deadline = time.time() + 5.0
    while time.time() < deadline and load_entry(pid):
        time.sleep(0.05)
    return load_entry(pid) is None


def restart_daemon(project_dir: str, port: int | None = None,
                   timeout: float = 30.0) -> dict | None:
    stop_daemon(project_dir)
    return start_daemon(project_dir, port=port, timeout=timeout)


def daemon_status(project_dir: str) -> dict | None:
    """Status dict for the project daemon, or None when not running."""
    pid = project_id(Path(project_dir))
    entry = load_entry(pid)
    if entry is None:
        return None
    if not _pid_alive(int(entry.get("pid", -1))):
        remove_entry(pid)
        return None
    response = _round_trip(entry, _env("ping"))
    if response is None:
        return None
    return {
        **entry,
        "uptime": round(time.time() - float(entry.get("started_at", time.time())), 1),
        "ping": response.payload,
    }


def list_daemons() -> list[dict]:
    out = []
    for entry in list_entries():
        healthy = (
            _pid_alive(int(entry.get("pid", -1)))
            and _round_trip(entry, _env("ping")) is not None
        )
        out.append({**entry, "healthy": healthy})
    return out


def sweep_stale_entries(base_dir=None, ping_retries: int = 2) -> list[dict]:
    """Remove registry entries whose daemon is dead or unreachable.

    An entry is stale when its PID is gone, or it fails ``ping`` across a few
    quick attempts (guarding against transient blips on a busy daemon). Healthy
    entries are left untouched. Returns the removed entries.
    """
    removed = []
    for entry in list_entries(base_dir):
        if not _pid_alive(int(entry.get("pid", -1))):
            remove_entry(entry["project_id"], base_dir)
            removed.append(entry)
            continue
        response = None
        for _ in range(max(1, ping_retries)):
            response = _round_trip(entry, _env("ping"), timeout=1.0)
            if response is not None and response.type == "pong":
                break
            time.sleep(0.2)
        if response is None or response.type != "pong":
            remove_entry(entry["project_id"], base_dir)
            removed.append(entry)
    return removed
