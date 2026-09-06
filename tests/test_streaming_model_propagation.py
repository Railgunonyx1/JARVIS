"""Regression tests for request-scoped model propagation on the streaming path.

The Gateway selects a model (e.g. ``qwen2.5:3b``); the router must forward that
selection to Ollama's ``complete_stream`` and record it as ``_last_model``
instead of silently using the provider's config default. Cloud providers
(Ollama excluded) must NOT receive a forced model.
"""
import asyncio
from collections.abc import AsyncIterator

from providers.router import ProviderRouter
from providers.types import LLMResponse


class _RecordingProvider:
    """Ollama-like provider that records the model it was asked to stream with."""

    captures_stream_tool_calls = True
    config = {"model": "qwen2.5:1.5b"}
    is_available = True

    def __init__(self):
        self.streamed_model = None
        self.completed_model = None
        self._stream_tool_calls = {}

    @property
    def model(self) -> str:
        return self.config.get("model", "unknown")

    async def complete(self, messages, system_prompt=None, max_tokens=None,
                       temperature=None, tools=None, model=None, **_):
        self.completed_model = model
        return LLMResponse(text="", model=model, provider="ollama",
                           tokens_used=1, latency_ms=1, finish_reason="stop")

    async def complete_stream(self, messages, system_prompt=None, max_tokens=None,
                              temperature=None, tools=None, model=None) -> AsyncIterator[str]:
        self.streamed_model = model
        yield "streamed"

    def _init_stream_tool_calls(self):
        self._stream_tool_calls = {}

    def _stream_tool_call_results(self):
        return []

    def record_rate_limit(self):
        pass

    def record_success(self, latency_ms):
        pass

    def record_failure(self, error):
        pass


def _router_with(provider) -> ProviderRouter:
    router = ProviderRouter(config={}, api_keys={})
    router._providers = {"ollama": provider}
    router._chain = ["ollama"]
    router._available_chain = ["ollama"]
    return router


def test_complete_stream_forwards_request_model_to_ollama():
    provider = _RecordingProvider()
    router = _router_with(provider)

    async def _run():
        chunks = []
        async for chunk in router.complete_stream(
            [{"role": "user", "content": "hi"}], preferred_model="qwen2.5:3b",
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_run())
    assert provider.streamed_model == "qwen2.5:3b"
    assert chunks == ["streamed"]


def test_complete_stream_records_request_scoped_last_model():
    provider = _RecordingProvider()
    router = _router_with(provider)

    async def _run():
        async for _ in router.complete_stream(
            [{"role": "user", "content": "hi"}], preferred_model="qwen2.5:3b",
        ):
            pass

    asyncio.run(_run())
    assert router._last_model == "qwen2.5:3b"
    assert router._last_provider == "ollama"


def test_complete_stream_typed_forwards_request_model():
    provider = _RecordingProvider()
    router = _router_with(provider)

    async def _run():
        async for _ in router.complete_stream_typed(
            [{"role": "user", "content": "hi"}], preferred_model="qwen2.5:3b",
        ):
            pass

    asyncio.run(_run())
    assert provider.streamed_model == "qwen2.5:3b"
    assert router._last_model == "qwen2.5:3b"


def test_complete_stream_defaults_to_provider_model_when_no_preferred():
    provider = _RecordingProvider()
    router = _router_with(provider)

    async def _run():
        async for _ in router.complete_stream([{"role": "user", "content": "hi"}]):
            pass

    asyncio.run(_run())
    assert provider.streamed_model is None
    assert router._last_model == "qwen2.5:1.5b"