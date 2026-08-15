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
    assert "No results found" in result.output


def test_formats_ddg_results(monkeypatch):
    monkeypatch.setattr(
        ws,
        "_ddg_search",
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
        "_ddg_news",
        lambda query, max_results=8: [
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
