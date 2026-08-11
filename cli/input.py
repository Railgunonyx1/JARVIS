"""Minimal dependency-free REPL input reader for the JARVIS MK-X terminal.

On Windows it uses ``msvcrt`` for raw key handling: cursor movement
(←/→/Home/End), Backspace/Delete, ↑/↓ command recall, Enter, Ctrl+C and
Ctrl+Z. It deliberately implements *command recall*, not a full line editor —
JARVIS needs reliable history, not a second prompt_toolkit.

Off-Windows it falls back to ``input()`` (with stdlib ``readline`` history
when available), so the rest of the CLI keeps working untouched.

Testability: ``read_line`` accepts an injectable ``key_source`` callable that
returns the next key code (default: ``msvcrt.getwch``). All buffer editing and
history navigation logic lives in the pure ``_Buffer``/key-mapping path, so it
can be driven headlessly in tests.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

KeySource = Callable[[], str]

# Keys returned by msvcrt for the function keys we care about.
_ESC = "\x1b"
_ENTER = "\r"
_CTRL_C = "\x03"
_CTRL_Z = "\x1a"
_BACKSPACE = "\x08"
_DELETE = "\x7f"
_TAB = "\t"

# Prefix + second byte for extended keys (arrows etc.) under msvcrt.
_EXT = {"\x00", "\xe0"}
_EXT_UP = "H"
_EXT_DOWN = "P"
_EXT_RIGHT = "M"
_EXT_LEFT = "K"
_EXT_HOME = "G"
_EXT_END = "O"
_EXT_DELETE = "S"


def _msvcrt_key_source() -> KeySource:
    import msvcrt

    def _next() -> str:
        ch = msvcrt.getwch()
        if ch in _EXT:
            ch = ch + msvcrt.getwch()
        return ch

    return _next


class Buffer:
    """A single editable command line (text + cursor), pure and testable."""

    __slots__ = ("text", "cursor")

    def __init__(self, text: str = "", cursor: int | None = None) -> None:
        self.text = text
        self.cursor = len(text) if cursor is None else cursor

    def insert(self, char: str) -> None:
        self.text = self.text[: self.cursor] + char + self.text[self.cursor :]
        self.cursor += len(char)

    def delete_left(self) -> None:
        if self.cursor > 0:
            self.text = self.text[: self.cursor - 1] + self.text[self.cursor :]
            self.cursor -= 1

    def delete_right(self) -> None:
        if self.cursor < len(self.text):
            self.text = self.text[: self.cursor] + self.text[self.cursor + 1 :]

    def cursor_left(self) -> None:
        self.cursor = max(0, self.cursor - 1)

    def cursor_right(self) -> None:
        self.cursor = min(len(self.text), self.cursor + 1)

    def cursor_home(self) -> None:
        self.cursor = 0

    def cursor_end(self) -> None:
        self.cursor = len(self.text)


def _redraw(write: Callable[[str], None], prompt: str, buf: Buffer) -> None:
    """Repaint prompt + buffer + cursor using the ANSI carriage-return trick."""
    text = prompt + buf.text
    pad = " " * max(0, len(text) - (len(prompt) + len(buf.text)))
    cursor_line = " " * (len(prompt) + buf.cursor)
    write(f"\r{text}{pad}\r{cursor_line}")


class InputReader:
    """Raw-key REPL input with editing and history recall."""

    def __init__(self, write: Callable[[str], None] | None = None, key_source: KeySource | None = None) -> None:
        self._write = write or sys.stdout.write
        self._key_source = key_source or (_msvcrt_key_source if sys.platform == "win32" else _fallback_key_source)
        self._history: list[str] = []
        self._index = 0
        self._draft = ""

    def set_history(self, entries: list[str]) -> None:
        """Seed history for ↑/↓ recall (caller owns persistence)."""
        self._history = list(entries)
        self._index = len(self._history)

    def read_line(self, prompt: str = "JARVIS> ") -> str:
        """Read one command line with editing + history. Raises
        ``KeyboardInterrupt`` on Ctrl+C and ``EOFError`` on Ctrl+Z/EOF."""
        if sys.platform != "win32":
            return self._read_fallback(prompt)
        return self._read_raw(prompt)

    # ── history navigation ─────────────────────────────────────────────────

    def _history_previous(self, buf: Buffer) -> None:
        if not self._history:
            return
        if self._index == len(self._history):
            self._draft = buf.text
        if self._index > 0:
            self._index -= 1
            buf.text = self._history[self._index]
            buf.cursor = len(buf.text)

    def _history_next(self, buf: Buffer) -> None:
        if not self._history:
            return
        if self._index < len(self._history) - 1:
            self._index += 1
            buf.text = self._history[self._index]
            buf.cursor = len(buf.text)
        else:
            self._index = len(self._history)
            buf.text = self._draft
            buf.cursor = len(buf.text)

    # ── raw (Windows / msvcrt) path ────────────────────────────────────────

    def _read_raw(self, prompt: str) -> str:
        keys = self._key_source()
        buf = Buffer()
        self._index = len(self._history)
        self._draft = ""
        _redraw(self._write, prompt, buf)
        try:
            while True:
                ch = keys()
                if ch == _ENTER:
                    self._write("\n")
                    return buf.text
                if ch == _CTRL_C:
                    self._write("\n")
                    raise KeyboardInterrupt
                if ch == _CTRL_Z:
                    self._write("\n")
                    raise EOFError
                if len(ch) == 2:  # extended key (arrow / Home / End / Delete)
                    self._extended_key(ch[1], buf)
                elif ch == _BACKSPACE:
                    buf.delete_left()
                elif ch == _DELETE:
                    buf.delete_right()
                elif ch == _TAB:
                    buf.insert("\t")
                elif ch.isprintable():
                    buf.insert(ch)
                else:
                    continue
                _redraw(self._write, prompt, buf)
        except KeyboardInterrupt:
            raise
        except EOFError:
            raise

    def _extended_key(self, code: str, buf: Buffer) -> None:
        if code == _EXT_UP:
            self._history_previous(buf)
        elif code == _EXT_DOWN:
            self._history_next(buf)
        elif code == _EXT_LEFT:
            buf.cursor_left()
        elif code == _EXT_RIGHT:
            buf.cursor_right()
        elif code == _EXT_HOME:
            buf.cursor_home()
        elif code == _EXT_END:
            buf.cursor_end()
        elif code == _EXT_DELETE:
            buf.delete_right()

    # ── non-Windows fallback ───────────────────────────────────────────────

    def _read_fallback(self, prompt: str) -> str:
        try:
            import readline  # noqa: F401  (stdlib, POSIX)
        except ImportError:
            return input(prompt)
        # readline gives us Up/Down history for free on POSIX.
        try:
            import builtins

            for entry in self._history:
                readline.add_history(entry)
            return builtins.input(prompt)
        except (EOFError, KeyboardInterrupt):
            raise


def _fallback_key_source() -> KeySource:
    def _next() -> str:
        return input("")

    return _next
