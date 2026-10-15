"""Web archive — content-hash-deduplicated page snapshots.

Derived from ArchiveBox's core thesis: without active preservation, pages
disappear or degrade — and an assistant that watched a page last month
cannot answer questions about what it said. Each ``web.archive`` call fetches
the URL, extracts readable text, and stores a snapshot only when its content
hash differs from the newest stored one. Snapshots accumulate under
``memory/archive/<slug>/`` with a small manifest, so history is browsable and
``doc.search`` sees the text automatically.

Not ArchiveBox's full engine (no WARC/screenshot/media): the snapshot format
is plain text + JSON manifest — the parts the assistant can actually reason
over later.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

from tools.schema import ToolResult

logger = logging.getLogger(__name__)

_MAX_SNAPSHOTS_PER_URL = 12
_MAX_TEXT_CHARS = 200_000


def _archive_root():
    from core.project import ProjectContext

    return ProjectContext.discover().root_path / "memory" / "archive"


def _manifest_path(url_slug: str):
    return _archive_root() / url_slug / "manifest.json"


def _slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", url.lower().replace("https://", "").replace("http://", ""))[:80].strip("_")


def _extract_text(html: str) -> tuple[str, str]:
    """(title, readable text) — same cheap pipeline as the reading list."""
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
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in text.splitlines()]
    paragraphs = [p for p in paragraphs if len(p) >= 40]
    return title, "\n\n".join(paragraphs)[:_MAX_TEXT_CHARS]


def _fetch_html(url: str, timeout: float) -> str | None:
    try:
        from core.http_pool import fetch
    except Exception:
        return None
    try:
        html = fetch(url, timeout=timeout)
        return str(html) if html else None
    except Exception as exc:
        logger.debug("web.archive: fetch failed for %s: %s", url, exc)
        return None


def web_archive(args: dict[str, Any]) -> ToolResult:
    """Snapshot a page's readable text; store only on content change."""
    url = str(args.get("url") or "").strip()
    if not re.match(r"^https?://", url):
        return ToolResult(success=False, error="url is required — an http(s) page to snapshot")
    force = bool(args.get("force", False))

    html = _fetch_html(url, timeout=float(args.get("timeout") or 20))
    if not html:
        return ToolResult(success=False, error=f"could not fetch page: {url}")
    title, text = _extract_text(html)
    content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]

    slug = _slug(url)
    manifest_path = _manifest_path(slug)
    manifest: dict[str, Any] = {"url": url, "title": title, "snapshots": []}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # rebuild the manifest

    snapshots = manifest.setdefault("snapshots", [])
    if snapshots and snapshots[-1].get("hash") == content_hash and not force:
        last = snapshots[-1]
        return ToolResult(
            success=True,
            output=f"Unchanged since {last.get('at', '?')} (hash {content_hash}). No new snapshot.",
        )

    stamp = time.strftime("%Y%m%d-%H%M%S")
    entry = {
        "hash": content_hash,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "file": f"{stamp}-{content_hash}.txt",  # hash suffix: same-second snapshots can't clobber each other
        "chars": len(text),
    }
    snapshots.append(entry)
    # Cap history: keep the newest N snapshots.
    dropped = snapshots[:-_MAX_SNAPSHOTS_PER_URL]
    manifest["snapshots"] = snapshots[-_MAX_SNAPSHOTS_PER_URL:]
    manifest["title"] = title or manifest.get("title", "")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (_archive_root() / slug / entry["file"]).write_text(f"{url}\n\n{text}", encoding="utf-8")

    n = len(manifest["snapshots"])
    note = f" ({len(dropped)} oldest pruned)" if dropped else ""
    return ToolResult(
        success=True,
        output=f"Archived: {title or url}\nhash {content_hash} · {len(text)} chars · snapshot {n}/{_MAX_SNAPSHOTS_PER_URL}{note}",
    )


def web_archive_list(args: dict[str, Any]) -> ToolResult:
    """List archived URLs and their snapshot counts."""
    root = _archive_root()
    if not root.exists():
        return ToolResult(success=True, output="Archive is empty. Snapshot one with web.archive + url.")
    lines = []
    for slug_dir in sorted(root.iterdir()):
        manifest_path = slug_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        title = manifest.get("title") or manifest.get("url", slug_dir.name)
        lines.append(f"- {title} — {len(manifest.get('snapshots', []))} snapshot(s)")
    if not lines:
        return ToolResult(success=True, output="Archive is empty.")
    return ToolResult(success=True, output="Archived pages:\n" + "\n".join(lines))


def web_archive_read(args: dict[str, Any]) -> ToolResult:
    """Read a stored snapshot: newest by default, or by index (-1 = newest)."""
    url = str(args.get("url") or "").strip()
    slug = _slug(url)
    manifest_path = _manifest_path(slug)
    if not manifest_path.exists():
        return ToolResult(success=False, error=f"no snapshots for: {url}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ToolResult(success=False, error="manifest unreadable — re-snapshot the page")
    snapshots = manifest.get("snapshots", [])
    if not snapshots:
        return ToolResult(success=False, error="no snapshots recorded")
    try:
        idx = int(args.get("index", -1))
    except (TypeError, ValueError):
        return ToolResult(success=False, error="index must be an integer")
    try:
        entry = snapshots[idx]
    except IndexError:
        return ToolResult(success=False, error=f"index out of range (0..{len(snapshots) - 1}, or -1 for newest)")
    file_path = _archive_root() / slug / entry["file"]
    try:
        body = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ToolResult(success=False, error="snapshot file missing")
    header = f"[{entry['at']}] hash {entry['hash']} — {url}"
    return ToolResult(success=True, output=header + "\n\n" + body[:8000])


__all__ = ["web_archive", "web_archive_list", "web_archive_read"]
