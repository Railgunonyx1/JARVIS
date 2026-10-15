"""Provider capability registry + capability-aware fallback chain tests."""

from __future__ import annotations

import pytest

from providers.capabilities import (
    PROVIDER_CAPABILITIES,
    ProviderCapability,
    capabilities_for,
    capability_matrix,
    provider_capability_report,
    providers_with,
)
from providers.router import _PROVIDER_CLASSES, ProviderRouter


class TestRegistry:
    def test_every_router_provider_is_declared(self):
        missing = set(_PROVIDER_CLASSES) - set(PROVIDER_CAPABILITIES)
        assert not missing, f"providers without a declared capability profile: {missing}"

    def test_all_providers_stream_and_use_tools(self):
        for name, pc in PROVIDER_CAPABILITIES.items():
            assert pc.has(ProviderCapability.STREAMING), name
            assert pc.has(ProviderCapability.TOOL_CALLS), name

    def test_stream_tool_call_capture_matches_code(self):
        # OpenAI-compatible integrations + Ollama capture streamed tool calls.
        assert capabilities_for("groq").has(ProviderCapability.STREAM_TOOL_CALLS)
        assert capabilities_for("ollama").has(ProviderCapability.STREAM_TOOL_CALLS)
        # Gemini implements LLMProvider directly — no streamed tool-call capture.
        assert not capabilities_for("gemini").has(ProviderCapability.STREAM_TOOL_CALLS)

    def test_local_and_keyless_flags(self):
        assert capabilities_for("ollama").has(ProviderCapability.LOCAL)
        assert capabilities_for("ollama").requires_key is False
        assert capabilities_for("llm7").requires_key is False
        assert capabilities_for("groq").requires_key is True

    def test_unknown_provider_is_conservative(self):
        pc = capabilities_for("not_a_provider")
        assert pc.has(ProviderCapability.STREAMING, ProviderCapability.TOOL_CALLS)
        assert not pc.has(ProviderCapability.STREAM_TOOL_CALLS)
        assert pc.requires_key is True

    def test_providers_with_filters_on_enforced_caps(self):
        stool = providers_with(ProviderCapability.STREAM_TOOL_CALLS)
        assert "groq" in stool and "ollama" in stool
        assert "gemini" not in stool

    def test_matrix_is_json_friendly(self):
        matrix = capability_matrix()
        assert matrix["groq"]["capabilities"]  # non-empty list
        assert isinstance(matrix["groq"]["advisory"], list)


class TestCapabilityReport:
    def test_merges_declared_and_runtime(self):
        status = {"groq": {"available": True, "model": "llama-3", "health": {"error_rate": 0.0}}}
        report = provider_capability_report(
            status=status, fallback_chain=["groq"], local_models=["qwen2.5:3b"],
        )
        assert report["providers"]["groq"]["configured"] is True
        assert report["providers"]["groq"]["available"] is True
        # Declared-but-unconfigured providers are still listed (catalog).
        assert report["providers"]["gemini"]["configured"] is False
        assert report["providers"]["gemini"]["available"] is None
        assert report["fallback_chain"] == ["groq"]
        assert report["local_models"] == ["qwen2.5:3b"]


class _FakeProvider:
    is_available = True
    model = "m"
    _package_ok = True
    _package_error = ""

    def __init__(self) -> None:
        from providers.base import ProviderHealth
        self.health = ProviderHealth()

    def consume_probe(self) -> None:
        pass


def _router_with(fake_providers, chain):
    r = ProviderRouter(config={}, api_keys={})
    r._providers = dict(fake_providers)
    r._chain = list(chain)
    r._invalidate_chain()
    return r


class TestCapabilityAwareChain:
    def test_select_chain_unfiltered(self):
        r = _router_with({"groq": _FakeProvider(), "gemini": _FakeProvider()}, ["groq", "gemini"])
        assert r.select_chain() == ["groq", "gemini"]

    def test_select_chain_excludes_incapable_provider(self):
        r = _router_with({"groq": _FakeProvider(), "gemini": _FakeProvider()}, ["gemini", "groq"])
        # gemini cannot capture streamed tool calls -> dropped, order preserved.
        assert r.select_chain({ProviderCapability.STREAM_TOOL_CALLS}) == ["groq"]

    def test_select_chain_keeps_capable_providers(self):
        r = _router_with({"groq": _FakeProvider(), "gemini": _FakeProvider()}, ["groq", "gemini"])
        assert r.select_chain({ProviderCapability.TOOL_CALLS}) == ["groq", "gemini"]

    def test_capability_report_from_router(self):
        r = _router_with({"groq": _FakeProvider()}, ["groq"])
        report = r.capability_report()
        assert report["providers"]["groq"]["configured"] is True
        assert report["fallback_chain"] == ["groq"]

    @pytest.mark.parametrize("method", ["complete", "complete_stream", "complete_stream_typed"])
    def test_request_methods_accept_required_capabilities(self, method):
        import inspect
        params = inspect.signature(getattr(ProviderRouter, method)).parameters
        assert "required_capabilities" in params
