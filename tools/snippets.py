"""Snippets — espanso-style text expansion.

Derived from federico-terzi/espanso: typing ``:sig`` should become a full
signature, everywhere. For JARVIS the expansion point is ``browser.type`` —
text the assistant (or the user via it) enters into pages is scanned for
``:trigger`` tokens and expanded from a small local store before it is
typed. The store lives under ``memory/snippets.json``; triggers are
lowercase words, expansions are bounded, and ``:trigger`` tokens that match
nothing are left untouched so normal prose with colons is safe.
"""

from __future__ import annotations

import json
import re
from typing import Any

from tools.schema import ToolResult

_MAX_SNIPPETS = 100
_MAX_EXPANSION = 2000
_TOKEN_RE = re.compile(r":([a-z0-9][a-z0-9_+-]*)")


def _state_path():
    from core.project import ProjectContext

    return ProjectContext.discover().root_path / "memory" / "snippets.json"


def _load() -> dict[str, str]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save(state: dict[str, str]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def expand_text(text: str) -> tuple[str, list[str]]:
    """Expand ``:trigger`` tokens. Returns (new_text, expanded_triggers)."""
    if not text or ":" not in text:
        return text, []
    state = _load()
    if not state:
        return text, []
    expanded: list[str] = []

    def repl(match: re.Match[str]) -> str:
        trigger = match.group(1)
        expansion = state.get(trigger)
        if expansion is None:
            return match.group(0)
        expanded.append(trigger)
        return expansion

    return _TOKEN_RE.sub(repl, text), expanded


def snippet_add(args: dict[str, Any]) -> ToolResult:
    trigger = str(args.get("trigger") or "").strip().lower()
    text = str(args.get("text") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_+-]{0,30}", trigger):
        return ToolResult(success=False, error="trigger must be a short lowercase word (letters/digits/_/+/-)")
    if not text.strip():
        return ToolResult(success=False, error="text is required — what should :trigger expand to?")
    if len(text) > _MAX_EXPANSION:
        return ToolResult(success=False, error=f"expansion too long (max {_MAX_EXPANSION} chars)")
    state = _load()
    if trigger not in state and len(state) >= _MAX_SNIPPETS:
        return ToolResult(success=False, error=f"snippet store is full ({_MAX_SNIPPETS})")
    existed = trigger in state
    state[trigger] = text
    _save(state)
    verb = "Updated" if existed else "Added"
    return ToolResult(success=True, output=f"{verb} snippet :{trigger} → {len(text)} chars")


def snippet_remove(args: dict[str, Any]) -> ToolResult:
    trigger = str(args.get("trigger") or "").strip().lower()
    state = _load()
    if trigger not in state:
        return ToolResult(success=False, error=f"no snippet named :{trigger}")
    state.pop(trigger)
    _save(state)
    return ToolResult(success=True, output=f"Removed :{trigger}")


def snippet_list(args: dict[str, Any]) -> ToolResult:
    state = _load()
    if not state:
        return ToolResult(success=True, output="No snippets. Add one with action='add', trigger='sig', text='...'.")
    lines = [f":{t} → {body[:60]}{'…' if len(body) > 60 else ''}" for t, body in sorted(state.items())]
    return ToolResult(success=True, output=f"{len(state)} snippet(s):\n" + "\n".join(lines))


def snippet_expand(args: dict[str, Any]) -> ToolResult:
    text = str(args.get("text") or "")
    new_text, expanded = expand_text(text)
    if not expanded:
        return ToolResult(success=True, output="(no snippets matched)" if text else "(empty text)")
    return ToolResult(success=True, output=f"{new_text}\n\n[expanded: {', '.join(':' + t for t in expanded)}]")


def snippet_handler(args: dict[str, Any]) -> ToolResult:
    action = str(args.get("action") or "list").strip().lower()
    if action == "add":
        return snippet_add(args)
    if action == "remove":
        return snippet_remove(args)
    if action == "expand":
        return snippet_expand(args)
    return snippet_list(args)


__all__ = ["snippet_handler", "expand_text"]
