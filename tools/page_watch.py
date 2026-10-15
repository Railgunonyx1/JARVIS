"""Page-watch — watch a URL (or browser page) for content changes.

Derived from dgtlmoon/changedetection.io: the agent can arm a watch on any
page, and a follow-up check reports a line-level diff when content changes.
State is persisted under the project root so watches survive restarts.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.page_watch")

MAX_OUTPUT = 6000
MAX_DIFF_LINES = 40
MAX_TEXT = 200_000  # stored per watch
_MAX_WATCHES = 100


def _state_path() -> Path:
    from core.project import ProjectContext
    return ProjectContext.discover().root_path / "memory" / "page_watch_state.json"


def _load() -> dict[str, dict[str, Any]]:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(state: dict[str, dict[str, Any]]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1), encoding="utf-8")


def _fetch_text(url: str, timeout: float) -> str | None:
    """Fetch page text via the shared pooled HTTP client."""
    try:
        from core.http_pool import fetch
    except Exception:  # noqa: BLE001
        return None
    html = fetch(url, timeout=timeout)
    if not html:
        return None
    return _html_to_text(str(html))


def _html_to_text(html: str) -> str:
    """Cheap, dependency-free HTML -> text (good enough for diffing)."""
    import re

    text = re.sub(r"(?is)<(script|style|noscript|template|svg)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|section|article|blockquote)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ").replace("&amp;", "&")
        .replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&#39;", "'")
    )
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    # Collapse runs of blank-ish lines; keep order for meaningful diffs.
    out: list[str] = []
    for ln in lines:
        if out and out[-1] == ln:
            continue
        out.append(ln)
    return "\n".join(out)[:MAX_TEXT]


def page_watch(args: dict[str, Any]) -> ToolResult:
    """Arm a watch, or re-check an armed watch and diff against last seen.

    First call records a baseline. Later calls fetch again and return a diff
    if the content changed ('changed': true) or report 'unchanged'.
    """
    url = str(args.get("url", "")).strip()
    if not url:
        return ToolResult(success=False, error="url is required")
    if not url.lower().startswith(("http://", "https://")):
        return ToolResult(success=False, error="Only http(s) URLs can be watched.")
    action = str(args.get("action", "check")).lower()
    timeout = min(float(args.get("timeout", 15.0)), 30.0)
    selector = str(args.get("selector", "")).strip()  # informational only (text mode)

    state = _load()
    key = hashlib.sha256(url.encode()).hexdigest()[:16]

    if action == "remove":
        if key in state:
            del state[key]
            _save(state)
            return ToolResult(success=True, output=f"Watch removed: {url}")
        return ToolResult(success=False, error=f"No watch armed for {url}")

    if action == "list":
        if not state:
            return ToolResult(success=True, output="No watches armed.")
        lines = []
        for k, w in state.items():
            age = time.time() - w.get("last_check", 0)
            lines.append(
                f"- {w.get('url')}  (last check {age / 60:.0f}m ago, "
                f"checks={w.get('checks', 0)}, changes={w.get('changes', 0)})"
            )
        return ToolResult(success=True, output="\n".join(lines), metadata={"count": len(state)})

    if len(state) >= _MAX_WATCHES and key not in state:
        return ToolResult(success=False, error=f"Watch limit reached ({_MAX_WATCHES}). Remove some first.")

    text = _fetch_text(url, timeout)
    if text is None:
        return ToolResult(success=False, error=f"Fetch failed for {url} (network or blocked).")

    now = time.time()
    entry = state.get(key)

    if action == "arm":
        state[key] = {
            "url": url,
            "baseline": text,
            "baseline_hash": hashlib.sha256(text.encode()).hexdigest(),
            "armed_at": now,
            "last_check": now,
            "checks": 0,
            "changes": 0,
            "last_text": text,
            "selector": selector,
        }
        _save(state)
        return ToolResult(
            success=True,
            output=f"Watch armed for {url} (baseline {len(text)} chars). Call page.watch again later to diff.",
            metadata={"key": key},
        )

    # default: check
    if not entry:
        # Auto-arm on first check for convenience.
        state[key] = {
            "url": url, "baseline": text,
            "baseline_hash": hashlib.sha256(text.encode()).hexdigest(),
            "armed_at": now, "last_check": now,
            "checks": 1, "changes": 0, "last_text": text, "selector": selector,
        }
        _save(state)
        return ToolResult(
            success=True,
            output=f"First sighting recorded for {url} ({len(text)} chars). Check again later to diff.",
            metadata={"key": key, "first": True},
        )

    prev = entry.get("last_text") or ""
    entry["checks"] = int(entry.get("checks", 0)) + 1
    entry["last_check"] = now
    if text == prev:
        _save(state)
        return ToolResult(
            success=True,
            output=f"Unchanged: {url} ({entry['checks']} checks, {entry.get('changes', 0)} changes so far).",
            metadata={"changed": False, "checks": entry["checks"]},
        )

    # Changed -> produce a compact unified diff against the previous snapshot.
    diff = list(difflib.unified_diff(
        prev.splitlines(), text.splitlines(),
        fromfile="previous", tofile="current", lineterm="", n=1,
    ))
    body = diff[2:] if len(diff) > 2 else diff  # skip ---/+++ headers
    shown = body[:MAX_DIFF_LINES]
    more = len(body) - len(shown)
    diff_text = "\n".join(shown) + (f"\n... (+{more} more lines)" if more > 0 else "")
    entry["changes"] = int(entry.get("changes", 0)) + 1
    entry["last_text"] = text
    _save(state)
    added = sum(1 for l in body if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in body if l.startswith("-") and not l.startswith("---"))
    return ToolResult(
        success=True,
        output=truncate(f"CHANGED ({added}+ / {removed}-):\n{diff_text}", MAX_OUTPUT),
        metadata={"changed": True, "added": added, "removed": removed, "url": url},
    )


__all__ = ["page_watch"]
