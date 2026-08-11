"""Persistent REPL command history for the JARVIS MK-X terminal.

Stored as one command per line at ``~/.jarvis/history``. Load is lazy and
tolerant (missing / corrupt files yield an empty history); saves are atomic
(temp file + ``os.replace``) and never raise into the REPL.

History hygiene:
    * consecutive duplicates are dropped
    * empty lines are dropped
    * sensitive-looking commands are never persisted (a simple heuristic —
      the filter is defense-in-depth, not a boundary)
    * the store is capped at ``MAX_ENTRIES``
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

logger = logging.getLogger("jarvis.cli.history")

MAX_ENTRIES = 1000

# Commands that look like they carry secrets (API keys, tokens, passwords).
# Deliberately conservative: better to skip a benign line than persist a secret.
_SENSITIVE = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|bearer|authorization|credential)"
    r"(\s*[=:]\s*|\s+)",
    re.IGNORECASE,
)


def default_history_path() -> Path:
    """Location of the persisted command history."""
    return Path.home() / ".jarvis" / "history"


class HistoryStore:
    """In-memory command history with atomic, fault-tolerant persistence."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else default_history_path()
        self._entries: list[str] = []
        self._loaded = False

    # ── access ─────────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    def __iter__(self):
        self.load()
        return iter(self._entries)

    def __len__(self) -> int:
        self.load()
        return len(self._entries)

    def to_list(self) -> list[str]:
        self.load()
        return list(self._entries)

    def __getitem__(self, index: int) -> str:
        self.load()
        return self._entries[index]

    # ── lifecycle ──────────────────────────────────────────────────────────

    def load(self) -> None:
        """Read persisted history once. Never raises — corrupt/missing files
        degrade to an empty history."""
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        try:
            text = self._path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("cannot read command history %s: %s", self._path, exc)
            return
        for raw in text.splitlines():
            line = raw.strip()
            if line and line.isprintable() and line not in self._entries:
                self._entries.append(line)
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self._entries[-MAX_ENTRIES:]

    def add(self, command: str) -> None:
        """Record one command (dedup, cap, sensitivity filter). In-memory only;
        call ``save()`` to persist."""
        line = (command or "").strip()
        if not line or _SENSITIVE.search(line):
            return
        if self._entries and self._entries[-1] == line:
            return
        self._entries.append(line)
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self._entries[-MAX_ENTRIES:]

    def save(self) -> None:
        """Atomically persist history. Never raises into the REPL."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".jarvis-history-", dir=str(self._path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write("\n".join(self._entries))
                    if self._entries:
                        handle.write("\n")
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            os.replace(tmp, self._path)
        except OSError as exc:
            logger.warning("cannot persist command history %s: %s", self._path, exc)
