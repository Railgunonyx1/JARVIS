"""Feed reading — RSS/Atom/JSON Feed ingestion with tracker hygiene.

Derived from miniflux/v2: an assistant that follows feeds should bring the
reading habits of a minimalist feed reader — parse every common format,
strip tracking parameters before URLs ever leave the machine, and keep state
bounded. No server, no database: just the parser, the pooled HTTP client,
and a small seen-file under ``memory/``.

Supported: RSS 2.0 (item/title/link/description/pubDate), Atom 1.0
(entry/title/link href/content/updated), JSON Feed 1.x (items/title/url/
summary/date_published). Tracking params stripped per Miniflux's list.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

from tools.schema import ToolResult

logger = logging.getLogger(__name__)

_MAX_FEED_BYTES = 2 * 1024 * 1024
_MAX_ITEMS = 100

# Miniflux's tracking-parameter list (the common offenders).
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_cid", "utm_reader", "utm_social",
    "utm_social-type", "utm_ve", "fbclid", "gclid", "dclid", "msclkid",
    "mc_eid", "mc_cid", "_hsenc", "_hsmi", "vero_id", "wickedid", "yclid",
    "igshid", "ttclid", "ref", "ref_src", "ref_url", "ref_tag",
}

# XML namespaces that matter for Atom.
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_JSONFEED_HINT = re.compile(r"^\s*\{\s*\"version\"\s*:\s*\"https?://jsonfeed\.org", re.IGNORECASE)

# Real-world feeds frequently contain bare '&' (invalid XML). Miniflux tolerates
# this; so do we — escape bare ampersands before handing the text to the parser.
_BARE_AMP_RE = re.compile(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)")


def _strip_tracking(url: str) -> str:
    """Remove tracking parameters from a URL query string."""
    if "?" not in url:
        return url
    base, _, query = url.partition("?")

    def tracked(key: str) -> bool:
        key = key.lower()
        return key in _TRACKING_PARAMS or key.startswith("utm_")  # any utm_* variant

    kept = [kv for kv in query.split("&") if kv and not tracked(kv.partition("=")[0])]
    return f"{base}?{'&'.join(kept)}" if kept else base


def _fetch_feed(url: str, timeout: float) -> str | None:
    try:
        from core.http_pool import fetch
    except Exception:
        return None
    try:
        text = fetch(url, timeout=timeout)
        return str(text)[:_MAX_FEED_BYTES] if text else None
    except Exception as exc:
        logger.debug("feed.read: fetch failed for %s: %s", url, exc)
        return None


def _txt(node: Any) -> str:
    return (node.text or "").strip() if node is not None else ""


def _parse_rss(root: ET.Element) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in root.iter("item"):
        entries: dict[str, str] = {}
        for field in ("title", "link", "description", "pubDate", "guid"):
            el = item.find(field)
            if el is not None:
                entries[field] = _txt(el)
        items.append({
            "title": entries.get("title") or "(untitled)",
            "url": _strip_tracking(entries.get("link") or entries.get("guid") or ""),
            "summary": entries.get("description", "")[:300],
            "date": entries.get("pubDate", ""),
        })
    return items


def _parse_atom(root: ET.Element) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for entry in root.iter(f"{_ATOM_NS}entry"):
        title = _txt(entry.find(f"{_ATOM_NS}title"))
        link = ""
        link_el = entry.find(f"{_ATOM_NS}link")
        if link_el is not None:
            link = link_el.get("href", "")
        summary = _txt(entry.find(f"{_ATOM_NS}summary")) or _txt(entry.find(f"{_ATOM_NS}content"))
        updated = _txt(entry.find(f"{_ATOM_NS}updated")) or _txt(entry.find(f"{_ATOM_NS}published"))
        items.append({
            "title": title or "(untitled)",
            "url": _strip_tracking(link),
            "summary": summary[:300],
            "date": updated,
        })
    return items


def _parse_jsonfeed(data: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for entry in data.get("items", [])[:_MAX_ITEMS]:
        items.append({
            "title": str(entry.get("title") or "(untitled)"),
            "url": _strip_tracking(str(entry.get("url") or entry.get("external_url") or "")),
            "summary": str(entry.get("summary") or entry.get("content_text") or entry.get("content_html", ""))[:300],
            "date": str(entry.get("date_published") or entry.get("date_modified") or ""),
        })
    return items


def _parse_feed(text: str) -> list[dict[str, str]]:
    """Format auto-detection: JSON Feed, RSS, or Atom."""
    if _JSONFEED_HINT.match(text):
        try:
            return _parse_jsonfeed(json.loads(text))
        except json.JSONDecodeError:
            return []
    try:
        root = ET.fromstring(_BARE_AMP_RE.sub("&amp;", text))
    except ET.ParseError as exc:
        logger.debug("feed.read: XML parse failed: %s", exc)
        return []
    tag = root.tag.rsplit("}", 1)[-1].lower()
    if tag == "rss":
        return _parse_rss(root)
    if tag == "feed":
        return _parse_atom(root)
    # RDF (RSS 1.0) stores items in the default namespace; fall through to iter.
    items = _parse_rss(root)
    return items or _parse_atom(root)


def _seen_path():
    from core.project import ProjectContext

    return ProjectContext.discover().root_path / "memory" / "feed_seen.json"


def _load_seen() -> dict[str, list[str]]:
    try:
        data = json.loads(_seen_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_seen(seen: dict[str, list[str]]) -> None:
    path = _seen_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seen, indent=2), encoding="utf-8")


def feed_read(args: dict[str, Any]) -> ToolResult:
    """Fetch a feed and list its latest items, newest first, tracking-stripped."""
    url = str(args.get("url") or "").strip()
    if not re.match(r"^https?://", url):
        return ToolResult(success=False, error="url is required — an http(s) RSS/Atom/JSON Feed URL")
    try:
        limit = min(int(args.get("limit") or 10), 50)
    except (TypeError, ValueError):
        return ToolResult(success=False, error="limit must be an integer")
    mark_seen = bool(args.get("mark_seen", False))

    text = _fetch_feed(url, timeout=float(args.get("timeout") or 15))
    if not text:
        return ToolResult(success=False, error=f"could not fetch feed: {url}")
    items = _parse_feed(text)
    if not items:
        return ToolResult(success=False, error="feed fetched but no items parsed — is it RSS/Atom/JSON Feed?")

    unseen_only = bool(args.get("unseen_only", False))
    if unseen_only or mark_seen:
        seen = _load_seen()
        seen_urls = set(seen.get(url, []))
        if unseen_only:
            fresh = [it for it in items if it["url"] and it["url"] not in seen_urls]
            shown = fresh
        else:
            shown = items
        if mark_seen:
            merged = list(dict.fromkeys(seen.get(url, []) + [it["url"] for it in items if it["url"]]))
            seen[url] = merged[-200:]  # cap memory
            _save_seen(seen)
    else:
        shown = items

    if not shown:
        return ToolResult(success=True, output="No new items since last check.")
    lines = []
    for i, item in enumerate(shown[:limit], 1):
        title = item["title"]
        url_part = f"\n   {item['url']}" if item["url"] else ""
        date_part = f"  ({item['date']})" if item["date"] else ""
        summary = f"\n   {item['summary']}" if item["summary"] else ""
        lines.append(f"{i}. {title}{date_part}{url_part}{summary}")
    header = f"{url} — {len(shown)} item(s):"
    return ToolResult(success=True, output=header + "\n" + "\n".join(lines))


__all__ = ["feed_read"]
