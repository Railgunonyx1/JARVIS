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

from cli.theme import PROMPT_TEXT

KeySource = Callable[[], str]


class PaletteRequest(Exception):
    """Raised when Ctrl+K opens the command palette mid-prompt.

    The REPL catches this, renders the palette, and re-prompts — the typed
    draft is discarded (matching a true Ctrl+K palette, not a hotkey-inline
    insert).
    """

# ANSI control codes (stdlib-only: the fast CLI path must not import rich).
_ANSI_RESET = "\x1b[0m"
_ANSI_BOLD_CYAN = "\x1b[1;36m"

# Keys returned by msvcrt for the function keys we care about.
_ENTER = "\r"
_CTRL_C = "\x03"
_CTRL_Z = "\x1a"
_CTRL_K = "\x0b"
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


def _styled_prompt(prompt: str) -> str:
    """Prompt with a leading reset and bold-cyan branding, matching the old
    ``console.input(Text("JARVIS", style="bold cyan"))`` look. The trailing
    reset restores the default attribute so typed text renders normally."""
    return f"{_ANSI_RESET}{_ANSI_BOLD_CYAN}{prompt}{_ANSI_RESET}"


def _redraw(write: Callable[[str], None], prompt: str, buf: Buffer,
            styled_prompt: str | None = None) -> None:
    """Repaint prompt + buffer + cursor using ANSI.

    ``styled_prompt`` is the display form of the prompt (with ANSI codes);
    ``prompt`` stays plain so the cursor column counts real glyphs. The line
    is painted once and the cursor repositioned with absolute-column CSI —
    never by writing spaces, which would erase the text it just drew (the
    original "input renders black/blank" bug).
    """
    shown = styled_prompt if styled_prompt is not None else prompt
    cursor_col = len(prompt) + buf.cursor
    write(f"\r{shown}{buf.text}\x1b[K\x1b[{cursor_col}G")


class InputReader:
    """Raw-key REPL input with editing and history recall."""

    def __init__(self, write: Callable[[str], None] | None = None,
                 flush: Callable[[], None] | None = None,
                 key_source: KeySource | None = None) -> None:
        self._write = write or sys.stdout.write
        self._flush = flush or (sys.stdout.flush if hasattr(sys.stdout, "flush")
                                else lambda: None)
        self._key_source = key_source or (_msvcrt_key_source if sys.platform == "win32" else _fallback_key_source)
        self._raw_key_source = key_source is not None
        self._history: list[str] = []
        self._index = 0
        self._draft = ""
        self._fallback_seeded = False

    def set_history(self, entries: list[str]) -> None:
        """Seed history for ↑/↓ recall (caller owns persistence)."""
        self._history = list(entries)
        self._index = len(self._history)

    def read_line(self, prompt: str = PROMPT_TEXT) -> str:
        """Read one command line with editing + history. Raises
        ``KeyboardInterrupt`` on Ctrl+C and ``EOFError`` on Ctrl+Z/EOF."""
        if sys.platform != "win32":
            return self._read_fallback(prompt)
        if self._raw_key_source or _stdin_is_tty():
            return self._read_raw(prompt)
        return self._read_plain(prompt)

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
        styled = _styled_prompt(prompt)
        _redraw(self._write, prompt, buf, styled_prompt=styled)
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
            if ch == _CTRL_K:
                self._write("\n")
                raise PaletteRequest
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
            _redraw(self._write, prompt, buf, styled_prompt=styled)

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

    def _read_plain(self, prompt: str) -> str:
        """Line-at-a-time read from a non-interactive stdin (pipe/file).

        The ``msvcrt`` path reads the real console device, which ignores a
        redirected ``sys.stdin``; when stdin is not a TTY we read it directly
        instead. Raises ``EOFError`` at end-of-input, matching ``input()``.
        """
        self._write(prompt)
        line = sys.stdin.readline()
        if not line:
            raise EOFError
        return line.rstrip("\r\n")

    def _read_fallback(self, prompt: str) -> str:
        try:
            import readline
        except ImportError:
            return input(prompt)
        # readline gives us Up/Down history for free on POSIX — seed once so a
        # multi-prompt session doesn't duplicate entries.
        if not self._fallback_seeded:
            for entry in self._history:
                readline.add_history(entry)
            self._fallback_seeded = True
        try:
            import builtins

            return builtins.input(prompt)
        except (EOFError, KeyboardInterrupt):
            raise


def _fallback_key_source() -> KeySource:
    def _next() -> str:
        return input("")

    return _next


def _stdin_is_tty() -> bool:
    try:
        return bool(sys.stdin.isatty())
    except (AttributeError, ValueError):
        return False
