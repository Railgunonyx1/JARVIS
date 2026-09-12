"""Tests for the recycled web.search tool (mocked transport, no network)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.web_search as ws  # noqa: E402
from tools import build_default_registry  # noqa: E402
from tools.schema import ToolResult  # noqa: E402


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(ws, "DDGS", None)
    # The HTML fallback hits lite.duckduckgo.com via core.http_pool — stub it
    # so the suite stays hermetic; tests that need results patch it directly.
    monkeypatch.setattr(ws, "_html_search", lambda query, max_results=8: [])


def test_web_search_registered():
    registry = build_default_registry()
    tool = registry.get("web.search")
    assert tool is not None
    assert tool.category == "web"
    assert tool.permission == "web.search"
    assert tool.handler is not None
    assert "query" in tool.parameters.get("required", [])


def test_requires_query():
    result = ws.web_search({})
    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "query" in result.error


def test_no_results_without_transport():
    result = ws.web_search({"query": "anything", "limit": 3})
    assert isinstance(result, ToolResult)
    assert result.success is False
    # Error message is in result.error (not output) after the error-handling fix
    combined = result.output + result.error
    assert "No search results found" in combined or "No results found" in combined


def test_formats_ddg_results(monkeypatch):
    monkeypatch.setattr(
        ws,
        "_html_search",
        lambda query, max_results: [
            {"title": "Alpha", "snippet": "first hit", "url": "https://a.example"},
            {"title": "Beta", "snippet": "second hit", "url": "https://b.example"},
        ],
    )
    result = ws.web_search({"query": "test", "limit": 2})
    assert result.success is True
    assert "Alpha" in result.output
    assert "https://b.example" in result.output
    assert result.metadata["count"] == 2


def test_news_mode_uses_ddg_news(monkeypatch):
    monkeypatch.setattr(
        ws,
        "_html_search",
        lambda query, max_results: [
            {"title": "Headline", "snippet": "body", "url": "https://n.example", "source": "BBC"},
        ],
    )
    result = ws.web_search({"query": "markets", "mode": "news", "limit": 5})
    assert result.success is True
    assert "Headline" in result.output
    assert "BBC" in result.output
    assert result.metadata["source"] == "duckduckgo"


def test_gemini_source_flag(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        ws,
        "_gemini_search",
        lambda query, api_key, max_results=8: [
            {"title": "Gemini ground-truth search", "snippet": "grounded answer", "url": ""},
        ],
    )
    result = ws.web_search({"query": "facts", "limit": 3})
    assert result.success is True
    assert "grounded answer" in result.output
    assert result.metadata["source"] == "gemini"


def test_repeated_query_hits_cache(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(
        ws,
        "_html_search",
        lambda query, max_results: (
            calls.__setitem__("n", calls["n"] + 1)
            or [{"title": "Hit", "snippet": "s", "url": "https://c.example"}]
        ),
    )
    first = ws.web_search({"query": "cached query", "limit": 2})
    second = ws.web_search({"query": "cached query", "limit": 2})
    assert first.success is True and second.success is True
    assert calls["n"] == 1
    assert second.metadata["source"] == "cache"


def test_parse_lite_results():
    html = (
        "<a rel='nofollow' href='//duckduckgo.com/?q=python'>logo</a>"
        '<tr><td><a rel="nofollow" href="//duckduckgo.com/l/?'
        'uddg=https%3A%2F%2Fdocs.python.org%2F3%2Flibrary%2Fasyncio.html&amp;'
        'rut=abc" class=\'result-link\'>asyncio &#x27;API&#x27; docs</a></td></tr>'
        "<tr><td class='result-snippet'><b>asyncio</b> is a concurrency library.</td></tr>"
        '<tr><td><a rel="nofollow" '
        'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Frealpython.com%2Fasync-io-python%2F" '
        "class='result-link'>Real Python walkthrough</a></td></tr>"
        "<tr><td class='result-snippet'>Explore hands-on examples.</td></tr>"
        "<a href='//duckduckgo.com/lite/?q=python'>Next</a>"
    )
    results = ws._parse_lite_results(html, 8)
    assert len(results) == 2
    assert results[0]["url"] == "https://docs.python.org/3/library/asyncio.html"
    assert results[0]["title"] == "asyncio 'API' docs"
    assert results[0]["snippet"] == "asyncio is a concurrency library."
    assert results[1]["url"] == "https://realpython.com/async-io-python/"
    assert results[1]["title"] == "Real Python walkthrough"


def test_parse_lite_results_respects_limit():
    html = (
        '<a rel="nofollow" href="https://a.example">One</a>'
        '<a rel="nofollow" href="https://b.example">Two</a>'
        '<a rel="nofollow" href="https://c.example">Three</a>'
    )
    results = ws._parse_lite_results(html, 2)
    assert len(results) <= 2
