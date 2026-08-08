"""Daemon registry, auth tokens, and port allocation.

Every JARVIS daemon registers itself in ``~/.jarvis/daemons/daemon-<project_id>.json``:

    {
        "project_id": "<16-hex fingerprint>",
        "project": "C:/path/to/project",
        "port": 47113,
        "pid": 1234,
        "token": "<secrets token>",
        "version": 1,
        "started_at": 123.0,
        "last_active": 123.0,
        "mode": "agent"
    }

The token is the daemon's own auth secret — clients read it from the registry
and present it in the ``auth`` handshake so unrelated local processes cannot
drive the kernel.

All registry functions accept an optional ``base_dir`` so tests can isolate
against a temp directory instead of the user's real ``~/.jarvis``.
"""

from __future__ import annotations

import json
import secrets
import socket
import time
from pathlib import Path
from typing import Dict, List, Optional

__all__ = [
    "DEFAULT_PORT",
    "PROTOCOL_VERSION",
    "LOG_PATH",
    "STATE_DIR",
    "DAEMONS_DIR",
    "registry_path",
    "load_entry",
    "save_entry",
    "remove_entry",
    "list_entries",
    "generate_token",
    "pick_port",
    "touch_entry",
]

DEFAULT_PORT = 47113
PROTOCOL_VERSION = 1

_HOME = Path.home() / ".jarvis"
DAEMONS_DIR = _HOME / "daemons"
STATE_DIR = _HOME / "state"
LOG_PATH = _HOME / "daemon.log"


def registry_path(project_id: str, base_dir: Optional[Path] = None) -> Path:
    return (base_dir or DAEMONS_DIR) / f"daemon-{project_id}.json"


def load_entry(project_id: str, base_dir: Optional[Path] = None) -> Optional[Dict]:
    """Read a daemon registry entry, or ``None`` when missing/corrupt."""
    path = registry_path(project_id, base_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    data["_path"] = str(path)
    return data


def save_entry(entry: Dict, base_dir: Optional[Path] = None) -> None:
    (base_dir or DAEMONS_DIR).mkdir(parents=True, exist_ok=True)
    data = dict(entry)
    data.pop("_path", None)
    path = registry_path(str(data.get("project_id", "")), base_dir)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def remove_entry(project_id: str, base_dir: Optional[Path] = None) -> None:
    try:
        registry_path(project_id, base_dir).unlink(missing_ok=True)
    except OSError:
        pass


def list_entries(base_dir: Optional[Path] = None) -> List[Dict]:
    base = base_dir or DAEMONS_DIR
    entries = []
    if not base.exists():
        return entries
    for path in sorted(base.glob("daemon-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_path"] = str(path)
            entries.append(data)
        except (OSError, ValueError):
            continue
    return entries


def touch_entry(project_id: str, base_dir: Optional[Path] = None) -> None:
    """Refresh ``last_active`` on an existing entry."""
    entry = load_entry(project_id, base_dir)
    if entry:
        entry["last_active"] = time.time()
        save_entry(entry, base_dir)


def generate_token() -> str:
    return secrets.token_hex(32)


def pick_port(preferred: Optional[int] = None) -> int:
    """Return ``preferred`` if free, otherwise any free localhost port."""
    candidates = [preferred] if preferred else []
    candidates.append(DEFAULT_PORT)
    for port in candidates:
        if port and _port_free(port):
            return port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _port_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.2)
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()
