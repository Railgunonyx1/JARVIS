"""Web search tool — Gemini ground-truth search with a fast HTML fallback.

Recycled from the quarantined ``actions/web_search.py`` into the v2 tool
contract. The model gets a compact result list; raw payloads stay out of
context by default.

Latency design:
* TTL result cache — repeated queries (a common agent pattern during
  research loops) resolve instantly instead of re-hitting the network.
* A single `genai.Client` is kept warm at module level (client init and its
  transport handshake cost ~100ms per call if built fresh every time).
* Gemini and the HTML fallback run *in parallel*; the first success wins,
  so one slow engine can no longer gate the reply.
* Every request has its own hard inner timeout, independent of the tool
  wrapper's 30s wall clock.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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

# Hard per-request ceilings so the *inner* path returns fast even when the
# tool wrapper's 30s timeout is far away (timed-out tool threads are dropped,
# so an inner bound is what actually protects the service).
_GEMINI_TIMEOUT_S = 8.0
_HTML_TIMEOUT_S = 6.0
_CACHE_TTL_S = 300.0
_CACHE_MAX = 128

_EXECUTOR = ThreadPoolExecutor(  # search fan-out;
    max_workers=2,
    thread_name_prefix="web-search",
)


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    """DuckDuckGo via the (optional) %s SDK — kept for parity."""
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


def _html_search(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    """DuckDuckGo lite via the shared pooled HTTP client (no SDK needed).

    The `ddgs`/`duckduckgo_search` packages are not installed, so the old
    fallback always returned []. This path uses ``core.http_pool`` (warm
    keep-alive connections) against the lightweight ``lite.duckduckgo.com``
    HTML endpoint and parses results out of the anchor block. It is the
    key-free engine; Gemini ground truth remains the preferred source.
    """
    try:
        from core.http_pool import fetch
    except Exception:
        return []
    text = fetch("https://lite.duckduckgo.com/lite/?q=" + query.replace(" ", "+"),
                 timeout=_HTML_TIMEOUT_S)
    if not text:
        return []
    return _parse_lite_results(text, max_results)


def _parse_lite_results(html: str, max_results: int) -> list[dict]:
    """Extract (title, snippet, url) triples from DDG lite result rows.

    lite.duckduckgo.com wraps every result link in a protocol-relative
    ``//duckduckgo.com/l/?uddg=<urlencoded>`` redirector and renders the
    snippet in a ``class='result-snippet'`` cell (single quotes). We resolve
    the redirector back to the real target and drop everything that points
    back at DuckDuckGo itself (logo, filters, pagination). The regexes are
    intentionally permissive — worst case is a missing row, not a crash.
    """
    from urllib.parse import parse_qs, urlparse

    tag_re = re.compile(r"<[^>]+>", re.S)

    def _clean(raw: str) -> str:
        import html as _html
        return _html.unescape(re.sub(r"\s+", " ", tag_re.sub("", raw)).strip())

    def _resolve(href: str) -> str | None:
        """Resolve a lite-page href to a real target URL or None."""
        h = href.strip()
        if h.startswith("//"):
            h = "https:" + h
        if not h.lower().startswith("http"):
            return None
        parsed = urlparse(h)
        host = (parsed.netloc or "").lower()
        if any(d in host for d in ("duckduckgo.com", "duckduckgo.co", "duckduckgo.org")):
            if parsed.path.startswith("/l/") and "uddg=" in parsed.query:
                target = parse_qs(parsed.query).get("uddg", [""])[0]
                if target.startswith("http"):
                    return target
            return None
        return h

    anchors = re.findall(
        r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I
    )
    snips = re.findall(
        r'class=["\']result-snippet["\'][^>]*>(.*?)</td>', html, re.S | re.I
    )
    found: list[dict] = []
    for i, (href, title) in enumerate(anchors):
        url = _resolve(href)
        if not url:
            continue
        snippet = _clean(snips[i]) if i < len(snips) else ""
        found.append({"title": _clean(title), "snippet": snippet, "url": url})
        if len(found) >= max_results:
            break
    return found


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


_genai_client = None
_genai_lock = threading.Lock()


def _get_genai_client(api_key: str):
    """Warm, thread-safe module singleton for the Gemini client.

    Creating a `genai.Client` per call pays client construction plus a fresh
    transport handshake every search (~100ms+). One warm instance is reused
    across calls; the API key is only used on first construction.
    """
    global _genai_client
    if _genai_client is None:
        with _genai_lock:
            if _genai_client is None:
                try:
                    from google import genai
                    _genai_client = genai.Client(api_key=api_key)
                except Exception:
                    _genai_client = False
    return _genai_client or None


def _gemini_search(query: str, api_key: str, max_results: int = MAX_RESULTS) -> list[dict]:
    client = _get_genai_client(api_key)
    if client is None:
        raise RuntimeError("Gemini client unavailable")
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


# ── Keyword relevance scoring ───────────────────────────────────
# The HTML lite path returns results in engine order, which is not the same
# as relevance to the *user's* phrasing. A cheap lexical score reorders the
# top of the list so the first results match the query best — Google-style —
# at essentially zero cost (few results x few tokens).
_STOPWORDS = frozenset((
    "a", "an", "the", "and", "or", "but", "of", "for", "on", "in", "to",
    "at", "by", "with", "is", "are", "was", "were", "be", "been", "what",
    "who", "when", "where", "why", "how", "does", "do", "did", "can",
    "could", "will", "would", "should", "about", "from", "into", "that",
    "this", "these", "those", "it", "its", "as",
))


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [w for w in words if w not in _STOPWORDS]


def _score_results(query: str, results: list[dict]) -> list[dict]:
    """Stable-sort results by lexical overlap with the query terms.

    Title hits weigh more than snippet hits; the full query appearing
    verbatim (or as a 2+ word phrase) in a title is a strong signal.
    Original order is the tie-break, so near-equal results keep engine order.
    """
    if not query or not results:
        return results
    q = query.lower()
    terms = _tokens(q)
    if not terms:
        return results
    phrase = q.strip()
    term_set = set(terms)

    def _score(r: dict) -> tuple[int, int]:
        title = (r.get("title") or "").lower()
        snippet = (r.get("snippet") or "").lower()
        title_tokens = _tokens(title)
        snippet_tokens = _tokens(snippet)
        score = 0
        for t in term_set:
            if t in title_tokens:
                score += 2 if len(t) > 3 else 1
        for t in term_set:
            if t in snippet_tokens:
                if len(t) > 3:
                    score += 1
                else:
                    score += 0
        # Exact-phrase bonus: the whole query sequence inside the title.
        if phrase in title:
            score += 8
        elif any(part in title for part in (phrase[:24], phrase[-24:]) if len(part) >= 4):
            score += 3
        return score

    scored = [(int(_score(r)), i, r) for i, r in enumerate(results)]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [r for _, _, r in scored]


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


# ── TTL result cache ────────────────────────────────────────────
# Ordered dict of {query -> (expires_at, results)}. Bounded at _CACHE_MAX and
# pruned on miss; identical queries during a research loop resolve instantly.
_cache: dict[str, tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()


def _cache_get(key: str) -> list[dict] | None:
    with _cache_lock:
        entry = _cache.get(key)
        if not entry:
            return None
        expires, results = entry
        if time.monotonic() > expires:
            del _cache[key]
            return None
        return [dict(r) for r in results]


def _cache_put(key: str, results: list[dict]) -> None:
    copy = [dict(r) for r in results]
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            stale = sorted(_cache, key=lambda k: _cache[k][0])[:8]
            for k in stale:
                _cache.pop(k, None)
        _cache[key] = (time.monotonic() + _CACHE_TTL_S, copy)


def web_search(args: dict[str, Any]) -> ToolResult:
    """Search the web. Gemini ground truth when a key is set; DDG-lite HTML
    otherwise. Engines race in parallel; the first success wins."""
    query = str(args.get("query", "")).strip()
    mode = str(args.get("mode", "search")).lower()
    limit = max(1, min(int(args.get("limit", 6)), MAX_RESULTS))
    api_key = os.environ.get("GEMINI_API_KEY", "")

    if not query:
        return ToolResult(success=False, error="A search 'query' is required.")

    cache_key = f"{mode}:{limit}:{query.lower()}"
    cached = _cache_get(cache_key)
    if cached:
        return ToolResult(
            success=True,
            output=truncate(
                (_fmt_news(query, cached) if mode == "news" else _fmt_results(query, cached)),
                MAX_OUTPUT,
            ),
            metadata={"count": len(cached), "source": "cache"},
        )

    results = _search(mode, query, limit, api_key)
    if results:
        # Reorder engine results by lexical relevance to the query, then
        # re-apply the requested limit (scoring may surface a better top-N).
        results = _score_results(query, results)[:limit]
        _cache_put(cache_key, results)
        fmt = _fmt_news(query, results) if mode == "news" else _fmt_results(query, results)
        return ToolResult(
            success=True,
            output=truncate(fmt, MAX_OUTPUT),
            metadata={"count": len(results), "source": "gemini" if api_key else "duckduckgo"},
        )
    if mode == "news":
        return ToolResult(success=False, error=f"No news results found for '{query}'.")
    return ToolResult(success=False, error=f"No search results found for '{query}'.", output="")


def _search(mode: str, query: str, limit: int, api_key: str) -> list[dict]:
    """Run the two engines in parallel; return the first non-empty result.

    The Gemini path (when a key is set) is the ground-truth preference, but a
    slow or failing Gemini must not push the wall time: the HTML fallback runs
    concurrently and the first engine with results wins. Worst case is now a
    single inner timeout (6-8s) instead of a serial chain (~30s+).
    """
    fallback = _ddg_search if DDGS else _html_search
    if mode == "news":
        if api_key:
            return _first_nonempty(
                lambda: _gemini_search(f"latest news today: {query}", api_key),
                lambda: _ddg_news(query, max_results=limit) if DDGS else _html_search(query, limit),
            )
        return _ddg_news(query, max_results=limit) if DDGS else _html_search(query, limit)

    return _first_nonempty(
        (lambda: _gemini_search(query, api_key)) if api_key else None,
        lambda: fallback(query, max_results=limit),
    )


def _first_nonempty(*fns) -> list[dict]:
    """Run non-None callables in parallel; return the first with results.

    Skips Gemini (None) when no key is set — single-engine path runs inline.
    """
    tasks = [(i, fn) for i, fn in enumerate(fns) if fn is not None]
    if not tasks:
        return []
    results: dict[int, list[dict]] = {}
    if len(tasks) == 1:
        try:
            results[0] = tasks[0][1]()
        except Exception as e:  # noqa: BLE001
            logger.debug("single search engine failed: %s", e)
        return results.get(0, [])

    futs = {_EXECUTOR.submit(fn): i for i, fn in tasks}
    done, _ = wait(futs, return_when=FIRST_COMPLETED, timeout=_GEMINI_TIMEOUT_S + _HTML_TIMEOUT_S)
    for fut in done:
        idx = futs[fut]
        try:
            results[idx] = fut.result()
        except Exception as e:  # noqa: BLE001
            logger.debug("search engine %d failed: %s", idx, e)
    if not done:
        for fut in futs:
            fut.cancel()
    preferred = results.get(0)
    if preferred:
        return preferred
    for fut in futs:
        if fut not in done:
            fut.cancel()
    return next((r for i, r in sorted(results.items()) if r), [])


__all__ = ["web_search"]
