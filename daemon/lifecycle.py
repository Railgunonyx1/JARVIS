"""Process-level daemon lifecycle control (client side, synchronous).

The CLI uses these helpers to discover a matching daemon, spawn one detached,
stop one, or report status. All network I/O is blocking-with-timeout so the
terminal bootstrap never hangs.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from daemon.project import project_id
from daemon.state import PROTOCOL_VERSION, list_entries, load_entry, remove_entry
from runtime.transport.protocol import decode_line, encode_line

__all__ = [
    "entry_healthy",
    "find_matching",
    "start_daemon",
    "stop_daemon",
    "restart_daemon",
    "daemon_status",
    "list_daemons",
]

ROOT = Path(__file__).resolve().parents[1]

# DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP — no console, survives parent exit.
_WIN_DETACH_FLAGS = 0x00000008 | 0x00000200
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

    Windows terminal harnesses often place commands inside a kill-on-close Job
    object. ``CREATE_BREAKAWAY_FROM_JOB`` escapes it when the job allows
    breakaway; when denied (``OSError``), spawn via the WMI provider instead,
    which creates the process outside the caller's job entirely.
    """
    if os.name == "nt":
        try:
            subprocess.Popen(
                command,
                cwd=cwd,
                creationflags=_WIN_DETACH_FLAGS | _WIN_BREAKAWAY_FLAG,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            return
        except OSError:
            pass  # job forbids breakaway — try the WMI provider
        if _spawn_wmi(command, cwd):
            return
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
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30.0,
            check=False,
        )
        return result.returncode == 0
    except Exception:
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
