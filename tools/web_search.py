"""Web search tool — optional Gemini ground-truth search with DuckDuckGo fallback.

Recycled from the quarantined ``actions/web_search.py`` into the v2 tool
contract. The model gets a compact result list; raw payloads stay out of
context by default.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.web_search")

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

MAX_RESULTS = 8
MAX_OUTPUT = 4000


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    if not DDGS:
        return []
    try:
        return [
            {"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
            for r in DDGS().text(query, max_results=max_results)
        ]
    except Exception as e:
        logger.warning("DuckDuckGo search failed: %s", e)
        return []


def _ddg_news(query: str, max_results: int = 8) -> list[dict]:
    if not DDGS:
        return []
    try:
        return [
            {"title": r.get("title", ""), "snippet": r.get("body", ""),
             "url": r.get("url", ""), "source": r.get("source", "")}
            for r in DDGS().news(query, max_results=max_results)
        ]
    except Exception as e:
        logger.warning("DuckDuckGo news failed (%s) — falling back to search", e)
        return _ddg_search(query, max_results)


def _gemini_search(query: str, api_key: str, max_results: int = MAX_RESULTS) -> list[dict]:
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash", contents=query,
        config={"tools": [{"google_search": {}}]},
    )
    text = "".join(
        p.text for p in response.candidates[0].content.parts
        if hasattr(p, "text") and p.text
    ).strip()
    if not text:
        raise ValueError("Gemini returned empty response")
    return [{"title": "Gemini ground-truth search", "snippet": text[:600], "url": ""}]


def _fmt_results(query: str, results: list[dict]) -> str:
    if not results:
        return f"No results found for: {query}"
    lines = [f"Search results for: {query}"]
    for i, r in enumerate(results, 1):
        if not r.get("title"):
            continue
        lines.append(f"{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet'][:180]}")
        if r.get("url"):
            lines.append(f"   Source: {r['url']}")
    return "\n".join(lines)


def _fmt_news(query: str, results: list[dict]) -> str:
    if not results:
        return f"No news found for: {query}"
    lines = [f"Latest news: {query}"]
    for i, r in enumerate(results, 1):
        if not r.get("title"):
            continue
        src = f"  [{r['source']}]" if r.get("source") else ""
        lines.append(f"{i}. {r['title']}{src}")
        lines.append(f"   {r.get('snippet', '')[:140]}")
        if r.get("url"):
            lines.append(f"   {r['url']}")
    return "\n".join(lines)


def web_search(args: dict[str, Any]) -> ToolResult:
    """Search the web (Gemini ground truth when a key is set, DDG otherwise)."""
    query = str(args.get("query", "")).strip()
    mode = str(args.get("mode", "search")).lower()
    limit = max(1, min(int(args.get("limit", 6)), MAX_RESULTS))
    api_key = os.environ.get("GEMINI_API_KEY", "")

    if not query:
        return ToolResult(success=False, error="A search 'query' is required.")

    results: list[dict] = []
    if mode == "news":
        q = query or "top world news today"
        if api_key:
            try:
                results = _gemini_search(f"latest news today: {q}", api_key)
            except Exception as e:
                logger.warning("Gemini news failed (%s) — DDG fallback", e)
        if not results:
            results = _ddg_news(q, max_results=limit)
        return ToolResult(
            success=bool(results),
            output=truncate(_fmt_news(q, results), MAX_OUTPUT),
            metadata={"count": len(results), "source": "gemini" if results and api_key else "duckduckgo"},
        )

    if api_key:
        try:
            results = _gemini_search(query, api_key)
        except Exception as e:
            logger.warning("Gemini search failed (%s) — DDG fallback", e)
    if not results:
        results = _ddg_search(query, max_results=limit)
    return ToolResult(
        success=bool(results),
        output=truncate(_fmt_results(query, results), MAX_OUTPUT),
        metadata={"count": len(results), "source": "gemini" if results and api_key else "duckduckgo"},
    )
