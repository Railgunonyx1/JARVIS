"""Tests for the World Monitor tool adapter (mocked transport, no network).

Covers the six curated handlers, schema registration, caching, and the
graceful degradation paths (unreachable instance, missing event id).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.world_monitor as wm  # noqa: E402
from tools import build_default_registry  # noqa: E402
from tools.schema import ToolResult  # noqa: E402

TOOL_NAMES = {
    "world_monitor.search",
    "world_monitor.get_alerts",
    "world_monitor.get_region",
    "world_monitor.get_event",
    "world_monitor.get_sources",
    "world_monitor.world_brief",
}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(wm, "_CACHE", {})
    monkeypatch.setattr(wm, "_base_url", lambda: "http://127.0.0.1:3000")
    monkeypatch.setattr(wm, "_variant", lambda: "full")


@pytest.fixture
def fake_fetch(monkeypatch):
    calls = []

    def install(payload):
        def _fake(url, timeout, api_key):
            calls.append(url)
            return {"data": payload, "_url": url, "_rpc": "test"}

        monkeypatch.setattr(wm, "_http_get", _fake)
        return calls

    return install


def test_all_world_tools_registered():
    registry = build_default_registry()
    names = {t.name for t in registry.list()}
    assert TOOL_NAMES.issubset(names)
    for name in TOOL_NAMES:
        tool = registry.get(name)
        assert tool.category == "world"
        assert tool.permission == "world_monitor.read"
        assert tool.handler is not None
        assert "required" in tool.parameters


def test_search_returns_content(fake_fetch):
    calls = fake_fetch([{"title": "Red Sea shipping attacks", "region": "Middle East"}])
    result = wm.world_monitor_search({"query": "shipping"})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert "Red Sea shipping attacks" in result.output
    assert result.metadata["count"] == 1
    assert calls[0].startswith("http://127.0.0.1:3000/api/full/v1/getNewsIntelligence")


def test_get_region(fake_fetch):
    fake_fetch({"country": "SG", "risk": "low"})
    result = wm.world_monitor_get_region({"country": "SG"})
    assert result.success is True
    assert result.metadata["endpoint"] == "getCountryBrief"


def test_get_event_requires_id():
    result = wm.world_monitor_get_event({})
    assert result.success is False
    assert "event_id" in result.error


def test_get_event_ok(fake_fetch):
    fake_fetch({"event_id": "evt-1", "detail": "power grid disruption"})
    result = wm.world_monitor_get_event({"event_id": "evt-1"})
    assert result.success is True


def test_get_sources_public_no_key(fake_fetch):
    fake_fetch([{"name": "ACLED", "category": "conflict"}])
    result = wm.world_monitor_get_sources({})
    assert result.success is True
    assert "ACLED" in result.output


def test_unreachable_instance_degrades(monkeypatch):
    monkeypatch.setattr(wm, "_http_get", lambda url, timeout, api_key: None)
    result = wm.world_monitor_world_brief({})
    assert result.success is False
    assert "unreachable" in result.error
    assert "127.0.0.1:3000" in result.error


def test_cache_hits_single_fetch(fake_fetch):
    calls = fake_fetch([{"title": "a"}, {"title": "b"}])
    wm.world_monitor_search({"query": "cache me"})
    wm.world_monitor_search({"query": "cache me"})
    assert len(calls) == 1


def test_cache_respects_params(fake_fetch):
    calls = fake_fetch([{"title": "x"}])
    wm.world_monitor_search({"query": "alpha"})
    wm.world_monitor_search({"query": "beta"})
    assert len(calls) == 2
