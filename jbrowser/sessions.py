"""J-Browser — browser sessions.

A J-Browser session is a distinct browser identity with its own cookies,
storage and (optionally) persistent user-data directory. Session identity is
independent from the JARVIS agent session but linked by ``session_id`` so one
agent task can own one (or several) isolated browsing sessions.

Persistent sessions reuse a user-data directory across runs, which lets
J-Browser operate inside an already authenticated session without ever
handling passwords (Strawberry/WebView2-model: browser owns auth).
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path


def new_session_id() -> str:
    """Generate a short stable session id."""
    return "jbs_" + uuid.uuid4().hex[:8]


def profile_dir(root: Path, session_id: str) -> Path:
    """Return the on-disk profile directory for a session id."""
    return root / "config" / "browser_profiles" / session_id


class BrowserSession:
    """A named browser session with an optional persistent profile."""

    def __init__(self, session_id: str = "", *, persistent: bool = False,
                 profile_root: Path | None = None) -> None:
        self.session_id = session_id or new_session_id()
        self.persistent = persistent
        self.profile_root = profile_root or Path(".")
        self.user_data_dir: Path | None = None
        if persistent:
            self.user_data_dir = profile_dir(self.profile_root, self.session_id)
            self.user_data_dir.mkdir(parents=True, exist_ok=True)

    def describe(self) -> dict:
        return {
            "session_id": self.session_id,
            "persistent": self.persistent,
            "profile_dir": str(self.user_data_dir) if self.user_data_dir else None,
        }


class SessionManager:
    """Thread-safe registry of browser sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str = "", *, persistent: bool = False,
                      profile_root: Path | None = None) -> BrowserSession:
        sid = session_id or new_session_id()
        with self._lock:
            existing = self._sessions.get(sid)
            if existing is not None:
                return existing
            session = BrowserSession(sid, persistent=persistent, profile_root=profile_root)
            self._sessions[sid] = session
            return session

    def get(self, session_id: str) -> BrowserSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def remove(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def list(self) -> list[BrowserSession]:
        with self._lock:
            return list(self._sessions.values())
