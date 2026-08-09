"""Clipboard Manager — read, write, and manage clipboard for JARVIS MK-X."""

import logging
from typing import Optional

logger = logging.getLogger("jarvis.actions.clipboard_manager")


def clipboard_action(action: str, parameters: dict, **kwargs) -> str:
    """Dispatch clipboard operations."""
    handlers = {
        "read": _read_clipboard,
        "write": _write_clipboard,
        "clear": _clear_clipboard,
        "append": _append_clipboard,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown clipboard action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Clipboard action '%s' failed: %s", action, e)
        return f"Clipboard operation failed: {e}"


def _read_clipboard(params: dict) -> str:
    """Read current clipboard content."""
    import pyperclip
    text = pyperclip.paste()
    if text:
        if len(text) > 2000:
            return f"Clipboard ({len(text)} chars):\n{text[:2000]}..."
        return f"Clipboard:\n{text}"
    return "Clipboard is empty"


def _write_clipboard(params: dict) -> str:
    """Write text to clipboard."""
    import pyperclip
    text = params.get("text", "")
    if not text:
        return "No text to copy"
    pyperclip.copy(text)
    return f"Copied to clipboard ({len(text)} chars)"


def _clear_clipboard(params: dict) -> str:
    """Clear the clipboard."""
    import pyperclip
    pyperclip.copy("")
    return "Clipboard cleared"


def _append_clipboard(params: dict) -> str:
    """Append text to clipboard."""
    import pyperclip
    text = params.get("text", "")
    if not text:
        return "No text to append"
    current = pyperclip.paste() or ""
    pyperclip.copy(current + text)
    return f"Appended to clipboard ({len(current + text)} chars total)"
