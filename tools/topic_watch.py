"""Topic watch — concept-level monitoring via news headlines.

Derived from FatihMakes/Mark-LIV ``actions/background_monitor.py``: the user
names a *topic* (not a URL) and JARVIS checks the news for it at most once per
day, alerting only when the top headline actually changes (md5 title hash).
Complements ``page_watch`` (exact-URL diffs) and ``world_monitor`` (curated
situational feeds).

Two Mark-LIV behaviors are adopted verbatim in spirit:

* **Values guardrail** — a blocklist of crypto/finance terms that is never
  monitored, regardless of phrasing or language. Mark refuses; so do we.
* **Dedup by title hash** — a repeat check with the same top headline is
  silence, not an alert. Alerts are scarce by design.

State persists under ``memory/`` like every other watcher.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from tools.schema import ToolResult

logger = logging.getLogger(__name__)

# ── Blocked categories (Mark-LIV guardrail: never monitored, any language) ──
_BLOCKED = {
    # asset names
    "bitcoin", "ethereum", "dogecoin", "solana", "binance",
    "nft", "blockchain", "defi", "altcoin", "memecoin", "coin", "token",
    # "crypto" root spellings across languages
    "crypto", "kripto", "cripto", "krypto", "крипто", "仮想通貨", "暗号資産",
    "cryptocurrency",
}

_MAX_TOPICS = 24  # bounded state


def _is_blocked(topic: str) -> bool:
    t = topic.lower()
    return any(word in t for word in _BLOCKED)


def _slug(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", topic.lower().strip())[:40].strip("_")


def _title_hash(title: str) -> str:
    return hashlib.md5(title.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _state_path() -> Path:
    from core.project import ProjectContext

    return ProjectContext.discover().root_path / "memory" / "topic_watch_state.json"


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


def _today() -> str:
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d")


def _news_for(topic: str, max_results: int) -> list[dict[str, Any]]:
    """Fresh news results for a topic — isolated here so tests can patch it."""
    from tools.web_search import _ddg_news

    return _ddg_news(topic, max_results=max_results)


def add_topic(args: dict[str, Any]) -> ToolResult:
    topic = (args.get("topic") or "").strip()
    if not topic:
        return ToolResult(success=False, error="topic is required — what should I watch?")
    if _is_blocked(topic):
        return ToolResult(
            success=False,
            error="I don't monitor crypto or financial topics.",
        )
    state = _load()
    slug = _slug(topic)
    if slug in state:
        return ToolResult(
            success=False,
            error=f"Already monitoring: {state[slug].get('topic', slug)}",
        )
    if len(state) >= _MAX_TOPICS:
        return ToolResult(
            success=False,
            error=f"Topic list is full ({_MAX_TOPICS}). Remove one first with action='remove'.",
        )
    state[slug] = {
        "topic": topic,
        "added": _today(),
        "last_check": "",
        "last_hash": "",
    }
    _save(state)
    return ToolResult(success=True, output=f"Now monitoring: {topic}")


def remove_topic(args: dict[str, Any]) -> ToolResult:
    topic = (args.get("topic") or "").strip().lower()
    if not topic:
        return ToolResult(success=False, error="topic is required")
    state = _load()
    slug = _slug(topic)
    if slug in state:  # exact
        label = state.pop(slug)["topic"]
        _save(state)
        return ToolResult(success=True, output=f"Stopped monitoring: {label}")
    for key, val in list(state.items()):  # partial
        if topic in val.get("topic", "").lower():
            label = state.pop(key)["topic"]
            _save(state)
            return ToolResult(success=True, output=f"Stopped monitoring: {label}")
    return ToolResult(success=False, error=f"Not found in monitored topics: {topic}")


def list_topics(args: dict[str, Any]) -> ToolResult:
    state = _load()
    if not state:
        return ToolResult(success=True, output="No topics monitored. Add one with topic_watch.add.")
    lines = [
        f"- {v.get('topic', k)} (since {v.get('added', '?')})" for k, v in state.items()
    ]
    return ToolResult(success=True, output="Monitored topics:\n" + "\n".join(lines))


def check_topics(args: dict[str, Any]) -> ToolResult:
    """Run pending daily checks; return alerts for changed headlines only."""
    state = _load()
    if not state:
        return ToolResult(success=True, output="No topics monitored.")
    today = _today()
    alerts: list[str] = []
    changed = False
    for slug, data in state.items():
        if data.get("last_check") == today:
            continue  # already checked today
        topic = data.get("topic", slug)
        try:
            results = _news_for(topic, max_results=5)
        except Exception as exc:  # network down — record attempt, keep going
            logger.warning("topic_watch check failed for %r: %s", topic, exc)
            data["last_check"] = today
            changed = True
            continue
        data["last_check"] = today
        changed = True
        top = results[0] if results else None
        title = (top or {}).get("title", "").strip()
        if not title:
            continue
        h = _title_hash(title)
        if h == data.get("last_hash"):
            continue  # same headline — silence, not an alert
        data["last_hash"] = h
        parts = [f"[TOPIC] {topic}", f"Headline: {title}"]
        snippet = (top or {}).get("snippet") or (top or {}).get("body") or ""
        if snippet:
            parts.append(snippet[:150])
        source = (top or {}).get("source", "")
        if source:
            parts.append(f"Source: {source}")
        alerts.append("\n".join(parts))
    if changed:
        _save(state)
    if not alerts:
        return ToolResult(success=True, output="No new headlines.")
    return ToolResult(success=True, output="\n\n".join(alerts))
