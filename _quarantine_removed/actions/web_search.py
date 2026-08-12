"""Web search — Gemini (with key) → DuckDuckGo fallback. Supports search, news, research, compare."""

import logging
import os

logger = logging.getLogger("jarvis.actions.web_search")

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None


def _gemini_search(query: str, api_key: str) -> str:
    from google import genai
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash", contents=query,
        config={"tools": [{"google_search": {}}]},
    )
    text = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, "text") and p.text).strip()
    if not text:
        raise ValueError("Gemini returned empty response.")
    return text


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    if not DDGS:
        return []
    return [{"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
            for r in DDGS().text(query, max_results=max_results)]


def _ddg_news(query: str, max_results: int = 8) -> list[dict]:
    if not DDGS:
        return []
    try:
        return [{"title": r.get("title", ""), "snippet": r.get("body", ""),
                 "url": r.get("url", ""), "source": r.get("source", "")}
                for r in DDGS().news(query, max_results=max_results)]
    except Exception:
        return _ddg_search(query, max_results)


def _fmt_results(query: str, results: list[dict]) -> str:
    if not results:
        return f"No results found for: {query}"
    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):
            lines.append(f"{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("url"):
            lines.append(f"   Source: {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def _fmt_news(query: str, results: list[dict]) -> str:
    if not results:
        return f"No news found for: {query}"
    lines = [f"Latest news: {query}\n"]
    for i, r in enumerate(results, 1):
        if not r.get("title"):
            continue
        src = f"  [{r['source']}]" if r.get("source") else ""
        lines.extend([f"{i}. {r['title']}{src}", f"   {r.get('snippet', '')[:140]}", f"   {r.get('url', '')}", ""])
    return "\n".join(lines).strip()


def _search(query: str, api_key: str) -> str:
    if api_key:
        try:
            return _gemini_search(query, api_key)
        except Exception as e:
            logger.warning("Gemini failed (%s) — DDG fallback", e)
    return _fmt_results(query, _ddg_search(query))


def _news(query: str, api_key: str) -> str:
    if api_key:
        try:
            return _gemini_search(f"latest news today: {query}" if query else "top world news today", api_key)
        except Exception as e:
            logger.warning("Gemini news failed: %s", e)
    q = query or "world news today"
    return _fmt_news(q, _ddg_news(q))


def _research(query: str, api_key: str) -> str:
    if api_key:
        try:
            return _gemini_search(f"Comprehensive explanation of: {query}. Include context, facts, nuances.", api_key)
        except Exception:
            pass
    return _fmt_results(query, _ddg_search(query, max_results=10))


def _compare(items: list[str], aspect: str, api_key: str) -> str:
    query = f"Compare {', '.join(items)} in terms of {aspect}. Give specific facts."
    if api_key:
        try:
            return _gemini_search(query, api_key)
        except Exception:
            pass
    lines = [f"Comparison — {aspect.upper()}", "-" * 40]
    for item in items:
        lines.append(f"\n> {item}")
        for r in _ddg_search(f"{item} {aspect}", max_results=2):
            if r.get("snippet"):
                lines.append(f"  * {r['snippet']}")
    return "\n".join(lines)


def web_search(parameters: dict, **kwargs) -> str:
    params = parameters or {}
    query = params.get("query", "").strip()
    mode = params.get("mode", "search").lower()
    items = params.get("items", [])
    aspect = params.get("aspect", "general")
    api_key = params.get("api_key") or os.environ.get("GEMINI_API_KEY", "")

    if not query and not items:
        return "Please provide a search query."
    if items:
        mode = "compare"

    try:
        if mode == "compare" and items:
            return _compare(items, aspect, api_key)
        if mode == "news":
            return _news(query, api_key)
        if mode == "research":
            return _research(query, api_key)
        return _search(query, api_key)
    except Exception as e:
        return f"Search failed: {e}"
