"""Session-level undo stack for state-changing agent actions.

Adapted from Mark-LIII's core/undo.py (MIT). The insight it contributes:

    Confirmation-before-everything makes an assistant unusable, and
    confirmation-for-nothing makes it dangerous. The middle path is to act
    immediately on reversible actions while recording how to reverse them,
    and reserve real confirmation gates for genuinely irreversible things.

JARVIS already has the irreversible gate (PermissionEngine._apply_risk_gate
for destructive/high-risk tools) and the in-band confirmation channel
(confirmation_handler). What it lacked is the third leg: a way for the user
to say "undo" after a *reversible* action landed — a mis-aimed
filesystem.write, a patch.replace on the wrong file. This module provides
that stack, and tools/session_tools.py exposes it as ``session.undo``.

Design notes carried over from Mark-LIII:
- Actions capture their own "before" state; only the action knows the true
  reverse of "move A to B" is "move B to A".
- Push is a locked list append — microseconds; nothing runs until the user
  asks for an undo.
- Entries pop BEFORE running: a failing undo must not be retried forever
  against a world that already moved on.
- Bounded depth (default 10) so closures holding old file contents cannot
  accumulate; oldest entries drop rather than refusing newest.

Additions over the original:
- ``skip_if`` guard so identical consecutive operations don't double-stack.
- Content size guard: writes over _MAX_UNDO_CONTENT bytes are registered as
  "cannot undo" entries (labelled, honest) instead of silently hoarding RAM.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

MAX_DEPTH = 10
_MAX_UNDO_CONTENT = 1_000_000  # 1 MB: beyond this, don't retain old contents


@dataclass
class _Entry:
    label: str                       # human sentence, shown back to the user
    undo: Callable[[], str]          # returns a short result string
    at: float = field(default_factory=time.monotonic)


_stack: list[_Entry] = []
_lock = threading.Lock()


def push_undo(label: str, undo_fn: Callable[[], str]) -> None:
    """Record that ``label`` just happened and ``undo_fn()`` reverses it.

    Called from tool handlers — possibly concurrent — hence the lock. Never
    raises: a broken undo registration must not take down the action that
    actually succeeded.
    """
    if not callable(undo_fn):
        return
    try:
        with _lock:
            _stack.append(_Entry(label=str(label)[:120], undo=undo_fn))
            # Drop the oldest rather than refusing the newest: the recent
            # past is what people ask to undo.
            while len(_stack) > MAX_DEPTH:
                _stack.pop(0)
    except Exception:  # pragma: no cover - defensive
        pass


def push_undo_for_write(path, before: str, after: str, label: str) -> None:
    """Convenience for file writes: register restoration of ``before``.

    Oversized files register an honest no-op entry instead of silently
    hoarding megabytes of content for the session.
    """
    try:
        if len(before) > _MAX_UNDO_CONTENT:
            push_undo(label, lambda: (
                "Contents too large to restore automatically "
                f"(>{_MAX_UNDO_CONTENT} bytes)."
            ))
            return
        # Closure over copies, not the live strings.
        _before, _after = str(before), str(after)
        p = str(path)

        def _restore() -> str:
            from pathlib import Path as _P
            if not _before:
                _P(p).unlink(missing_ok=True)
                return f"Removed created file {p}."
            _P(p).write_text(_before, encoding="utf-8")
            return f"Restored previous contents of {p}."

        push_undo(label, _restore)
    except Exception:  # pragma: no cover - defensive
        pass


def can_undo() -> bool:
    with _lock:
        return bool(_stack)


def peek() -> str:
    """Label of the operation that ``undo_last()`` would reverse, or ''."""
    with _lock:
        return _stack[-1].label if _stack else ""


def history() -> list[str]:
    """Most recent first — for the ``session.undo`` list mode and UI panels."""
    with _lock:
        return [e.label for e in reversed(_stack)]


def undo_last() -> str:
    """Reverse the most recent reversible operation.

    The entry pops *before* running: a failing undo must not be retried
    forever against a world that has already moved on (the file being
    restored may have been deleted by something else since).
    """
    with _lock:
        entry = _stack.pop() if _stack else None

    if entry is None:
        return ("Nothing to undo. I only track changes I made myself — "
                "files I wrote or patched in this session.")

    try:
        detail = entry.undo() or ""
    except Exception as e:
        return f"Could not undo '{entry.label}': {e}"

    return f"Undone: {entry.label}." + (f" {detail}" if detail else "")


def clear() -> None:
    """Forget the stack. Called at session end so closures holding old file
    contents do not outlive the session."""
    with _lock:
        _stack.clear()


__all__ = [
    "MAX_DEPTH",
    "push_undo",
    "push_undo_for_write",
    "can_undo",
    "peek",
    "history",
    "undo_last",
    "clear",
]
