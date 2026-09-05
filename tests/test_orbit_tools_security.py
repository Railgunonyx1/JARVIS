"""G5 — Orbit browser tool hardening (hermetic, no browser needed).

Covers the locked tool-catalog guarantees:
  - declarative retry semantics (READ / IDEMPOTENT / CONDITIONALLY / NON)
    and concurrency labels (parallel / serialized) on every orbit tool;
  - sensitive-site consent gate in the central PermissionEngine (fail closed);
  - RESOURCE_LOCKED surfaced as a structured ToolResult (never a raw throw).
"""

from __future__ import annotations

import asyncio

import pytest

from core.agent.permissions import PermissionEngine
from core.decision_logger import DecisionLogger
from core.locks import ResourceLockedError
from orbit import tools as orbit_tools
from orbit.tools import build_orbit_tools
from security.sensitive_sites import SENSITIVE_SITES, SensitiveSitePolicy
from tools.schema import ToolResult

RETRY_SET = {"READ", "IDEMPOTENT", "CONDITIONALLY", "NON", "non_idempotent"}
CONCURRENCY_SET = {"parallel", "serialized"}

_READ_TOOLS = {
    "orbit.read", "orbit.list_tabs", "orbit.status", "orbit.extract",
    "orbit.permissions",
}
_IDEMPOTENT_TOOLS = {"orbit.close_tab", "orbit.activate_tab"}
_CONDITIONAL_TOOLS = {"orbit.navigate", "orbit.back", "orbit.forward",
                      "orbit.reload", "orbit.scroll", "orbit.screenshot"}
_NON_TOOLS = {
    "orbit.new_tab", "orbit.click", "orbit.type", "orbit.execute_script",
}


def _catalog() -> dict[str, object]:
    return {t.name: t for t in build_orbit_tools()}


class TestDeclaredMetadata:
    def test_every_orbit_tool_carries_retry_and_concurrency(self):
        for tool in build_orbit_tools():
            assert tool.retry_semantics in RETRY_SET, tool.name
            assert tool.concurrency in CONCURRENCY_SET, tool.name
            assert tool.risk in ("safe", "low", "medium", "high", "critical")

    def test_high_risk_mutations_are_serialized(self):
        for tool in build_orbit_tools():
            if tool.risk in ("high", "critical"):
                assert tool.concurrency == "serialized", tool.name

    def test_pure_reads_are_parallel(self):
        for name in ("orbit.read", "orbit.list_tabs", "orbit.status",
                     "orbit.extract", "orbit.permissions"):
            tool = _catalog()[name]
            assert tool.concurrency == "parallel"
            assert tool.retry_semantics == "READ"

    def test_retry_matrix(self):
        cat = _catalog()
        for name in _READ_TOOLS:
            assert cat[name].retry_semantics == "READ", name
        for name in _IDEMPOTENT_TOOLS:
            assert cat[name].retry_semantics == "IDEMPOTENT", name
        for name in _CONDITIONAL_TOOLS:
            assert cat[name].retry_semantics in ("CONDITIONALLY", "NON"), name
        for name in _NON_TOOLS:
            assert cat[name].retry_semantics == "NON", name

    def test_click_type_script_highest_risk_and_destructive(self):
        for name in ("orbit.click", "orbit.type", "orbit.execute_script"):
            tool = _catalog()[name]
            assert tool.risk == "high"
            assert tool.is_destructive
            assert tool.concurrency == "serialized"
            assert tool.retry_semantics == "NON"

    def test_navigation_is_low_risk_non_destructive_with_network_egress(self):
        tool = _catalog()["orbit.navigate"]
        assert tool.risk == "low"
        assert not tool.is_destructive
        assert "network_egress" in tool.side_effects
        assert tool.timeout_seconds == 60.0

    def test_permission_strings_are_consistent(self):
        cat = _catalog()
        assert cat["orbit.navigate"].permission == "orbit.browser.open"
        assert cat["orbit.click"].permission == "orbit.browser.act"
        assert cat["orbit.type"].permission == "orbit.browser.act"
        assert cat["orbit.execute_script"].permission == "orbit.browser.script"


class TestSensitiveSitePolicy:
    def test_matches_bare_and_subdomains(self):
        assert SENSITIVE_SITES.match("https://chase.com/login")
        assert SENSITIVE_SITES.match("https://idp.chase.com/sso")
        assert SENSITIVE_SITES.match("http://www.gmail.com")
        assert SENSITIVE_SITES.match("https://github.com/org/repo")

    def test_does_not_match_public_or_loopback(self):
        assert not SENSITIVE_SITES.match("https://example.com/docs")
        assert not SENSITIVE_SITES.match("http://127.0.0.1:8080/app")
        assert not SENSITIVE_SITES.match("")
        assert not SENSITIVE_SITES.match("not a url")

    def test_homograph_care(self):
        assert not SensitiveSitePolicy(frozenset({"chase.com"})).match(
            "https://chase.com.evil.example/login")


class TestSensitiveSiteGate:
    def _engine(self, handler=None):
        return PermissionEngine(
            DecisionLogger(),
            mode="agent",
            confirmation_handler=handler,
        )

    def test_sensitive_navigation_denied_without_consent_channel(self):
        engine = self._engine(None)
        tool = _catalog()["orbit.navigate"]
        allowed, reason = asyncio.run(engine.check(
            tool, {"url": "https://chase.com/account"},
            trace_id="t1", session_id="s1",
        ))
        assert allowed is False
        assert "sensitive" in reason.lower()

    @pytest.mark.parametrize("decision,expected", [
        ("deny", False), ("run", True), ("once", True),
    ])
    def test_sensitive_navigation_follows_consent_decision(self, decision, expected):
        recorded = []

        def handler(tool_name, args):
            recorded.append((tool_name, args))
            return decision

        engine = self._engine(handler)
        tool = _catalog()["orbit.navigate"]
        allowed, _ = asyncio.run(engine.check(
            tool, {"url": "https://paypal.com/checkout"},
            trace_id="t2", session_id="s2",
        ))
        assert allowed is expected
        assert recorded and recorded[0][0] == "orbit.navigate"

    def test_public_navigation_not_gated(self):
        engine = self._engine(None)
        tool = _catalog()["orbit.navigate"]
        allowed, _ = asyncio.run(engine.check(
            tool, {"url": "https://example.com/articles/1"},
            trace_id="t3", session_id="s3",
        ))
        assert allowed is True

    def test_non_navigation_open_tool_not_gated_by_url(self):
        # A research/open tool that is not a .open permission is never gated.
        engine = self._engine(None)
        from tools.schema import Tool

        async def noop(args):
            return ToolResult(success=True)

        tool = Tool(name="orbit.status", description="d",
                    parameters={}, permission="orbit.browser",
                    handler=noop, category="orbit")
        allowed, _ = asyncio.run(engine.check(
            tool, {"url": "https://chase.com/x"},
            trace_id="t4", session_id="s4",
        ))
        assert allowed is True


class TestResourceLockedSurfacing:
    def test_ownership_contest_returns_structured_result(self, monkeypatch):
        calls = []

        class FakeController:
            def click(self, handle, tab_id=None):
                calls.append((handle, tab_id))
                raise ResourceLockedError("tab_abc", "USER")

        monkeypatch.setattr(orbit_tools, "get_orbit_controller",
                            lambda *a, **k: FakeController())
        tool = _catalog()["orbit.click"]
        result = tool.handler({"handle": "[el0]"})
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert result.metadata["reason"] == "RESOURCE_LOCKED"
        assert result.metadata["owner"] == "USER"
        assert result.metadata["key"] == "tab_abc"
        assert "RESOURCE_LOCKED" in result.error
        assert calls == [("[el0]", None)]

    def test_respected_tool_still_works(self, monkeypatch):
        class FakeController:
            def status(self):
                return {"backend": "cdp", "available": True, "launched": True,
                        "headless": True, "tabs": 0}

        monkeypatch.setattr(orbit_tools, "get_orbit_controller",
                            lambda *a, **k: FakeController())
        tool = _catalog()["orbit.status"]
        result = tool.handler({})
        assert result.success is True


class TestSensitiveSitePolicyUnit:
    def test_stable_singleton(self):
        assert SENSITIVE_SITES.hosts
        assert "chase.com" in SENSITIVE_SITES.hosts
        assert "example.com" not in SENSITIVE_SITES.hosts