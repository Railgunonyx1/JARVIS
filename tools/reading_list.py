"""Reading list — save-for-later with content extraction.

Derived from wallabag: click, save, read it when you want. The assistant
stores the article's extracted text alongside the metadata, so "what did that
article say about X" works later even if the page changes or disappears —
the reading list doubles as a tiny personal archive, and saved items are
automatically visible to ``doc.search`` (they live under ``memory/reading/``).

State: one JSON file under ``memory/`` for the index, one .txt per saved
article for the extracted content. Bounded: 200 items, 300 KB of text each.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from tools.schema import ToolResult

logger = logging.getLogger(__name__)

_MAX_ITEMS = 200
_MAX_TEXT_CHARS = 300_000


def _state_path():
    from core.project import ProjectContext

    return ProjectContext.discover().root_path / "memory" / "reading_list.json"


def _reading_dir():
    from core.project import ProjectContext

    return ProjectContext.discover().root_path / "memory" / "reading"


def _load() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save(state: dict[str, dict[str, Any]]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", url.lower().replace("https://", "").replace("http://", ""))[:80].strip("_")


def _fetch_html(url: str, timeout: float) -> str | None:
    try:
        from core.http_pool import fetch
    except Exception:
        return None
    try:
        html = fetch(url, timeout=timeout)
        return str(html) if html else None
    except Exception as exc:
        logger.debug("reading.list: fetch failed for %s: %s", url, exc)
        return None


def _extract_article_text(html: str) -> tuple[str, str]:
    """Cheap readability: drop scripts/styles/nav, keep paragraphs. Returns (title, text)."""
    title = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()[:200]

    text = re.sub(r"(?is)<(script|style|noscript|template|svg|nav|footer|header|aside)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|section|article|blockquote)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ").replace("&amp;", "&")
        .replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&#39;", "'")
    )
    paragraphs = []
    for para in (ln.strip() for ln in text.splitlines()):
        para = re.sub(r"\s+", " ", para).strip()
        if len(para) >= 40:  # skip nav crumbs and one-word lines
            paragraphs.append(para)
    return title, "\n\n".join(paragraphs)[:_MAX_TEXT_CHARS]


def reading_list(args: dict[str, Any]) -> ToolResult:
    """Save, list, read, or remove articles for later."""
    action = str(args.get("action") or "list").strip().lower()
    url = str(args.get("url") or "").strip()

    state = _load()

    if action == "save":
        if not re.match(r"^https?://", url):
            return ToolResult(success=False, error="url is required — an http(s) article link")
        if url in state:
            return ToolResult(success=False, error="already saved — use action='read' to see it")
        if len(state) >= _MAX_ITEMS:
            return ToolResult(success=False, error=f"reading list is full ({_MAX_ITEMS}); remove something first")
        timeout = float(args.get("timeout") or 15)
        html = _fetch_html(url, timeout)
        title, text = ("", "")
        if html:
            title, text = _extract_article_text(html)
        if not text:
            text = "(content could not be extracted — URL saved, try again later)"
        entry = {
            "url": url,
            "title": title or url,
            "saved_at": time.strftime("%Y-%m-%d %H:%M"),
            "chars": len(text),
        }
        state[url] = entry
        _save(state)
        rdir = _reading_dir()
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / f"{_slug(url)}.txt").write_text(f"{url}\n\n{text}", encoding="utf-8")
        return ToolResult(
            success=True,
            output=f"Saved for later: {entry['title']}\n{len(text)} chars extracted — visible to doc.search.",
        )

    if action == "list":
        if not state:
            return ToolResult(success=True, output="Reading list is empty. Save one with action='save' + url.")
        lines = []
        for i, entry in enumerate(sorted(state.values(), key=lambda e: e.get("saved_at", "")), 1):
            lines.append(f"{i}. {entry.get('title', entry['url'])}  [{entry.get('saved_at', '?')}]")
            lines.append(f"   {entry['url']}")
        return ToolResult(success=True, output=f"{len(state)} saved item(s):\n" + "\n".join(lines))

    if action == "read":
        entry = state.get(url)
        if not entry:
            return ToolResult(success=False, error="not on the reading list — save it first")
        text_file = _reading_dir() / f"{_slug(url)}.txt"
        try:
            body = text_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            body = "(stored text missing — re-save to re-extract)"
        return ToolResult(success=True, output=body[:8000])

    if action == "remove":
        entry = state.pop(url, None)
        if not entry:
            return ToolResult(success=False, error=f"not on the reading list: {url}")
        _save(state)
        try:
            (_reading_dir() / f"{_slug(url)}.txt").unlink(missing_ok=True)
        except OSError:
            pass
        return ToolResult(success=True, output=f"Removed: {entry.get('title', url)}")

    return ToolResult(success=False, error=f"unknown action: {action} (save/list/read/remove)")


__all__ = ["reading_list"]
