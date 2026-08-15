"""Phase 8 — provider rate-limit retry/backoff in the router."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from providers.router import ProviderRouter


class FlakyProvider:
    """Fails once with a 429-style error, then succeeds."""

    captures_stream_tool_calls = True
    model = "flaky"
    is_available = True

    def __init__(self, fail_count: int = 1):
        self.fail_count = fail_count
        self._calls = 0

    async def complete(self, *args, **kwargs):
        self._calls += 1
        if self._calls <= self.fail_count:
            raise RuntimeError("Error code: 429 - rate limit, please try again in 1s")
        from providers.base import LLMResponse
        return LLMResponse(text="ok", model=self.model, provider="flaky",
                           tokens_used=1, latency_ms=1, finish_reason="stop")

    async def complete_stream(self, *args, **kwargs) -> AsyncIterator[str]:
        self._calls += 1
        if self._calls <= self.fail_count:
            raise RuntimeError("Error code: 429 - rate limit, please try again in 1s")
        yield "hello"

    def _init_stream_tool_calls(self):
        pass

    def _stream_tool_call_results(self):
        return []


def _router_with(provider) -> ProviderRouter:
    router = ProviderRouter(config={}, api_keys={})
    router._providers["flaky"] = provider
    router._chain = ["flaky"]
    router._available_chain = ["flaky"]
    return router


def test_complete_retries_on_rate_limit():
    provider = FlakyProvider(fail_count=1)
    router = _router_with(provider)

    result = asyncio.run(router.complete([{"role": "user", "content": "hi"}], "sys"))
    assert result.text == "ok"
    assert provider._calls == 2


def test_stream_retries_on_rate_limit_before_first_chunk():
    provider = FlakyProvider(fail_count=1)
    router = _router_with(provider)

    async def go():
        parts = []
        async for chunk in router.complete_stream([{"role": "user", "content": "hi"}], "sys"):
            parts.append(chunk)
        return parts

    assert asyncio.run(go()) == ["hello"]
    assert provider._calls == 2


def test_stream_typed_retries_on_rate_limit():
    provider = FlakyProvider(fail_count=1)
    router = _router_with(provider)

    async def go():
        out = []
        async for chunk, calls in router.complete_stream_typed(
            [{"role": "user", "content": "hi"}], "sys",
        ):
            out.append(chunk)
        return out

    assert asyncio.run(go()) == ["hello", None]
    assert provider._calls == 2


def test_exhausts_retries_then_raises():
    provider = FlakyProvider(fail_count=99)
    router = _router_with(provider)

    with __import__("pytest").raises(RuntimeError, match="All providers failed"):
        asyncio.run(router.complete([{"role": "user", "content": "hi"}], "sys"))


def test_rate_limit_helpers():
    router = ProviderRouter(config={}, api_keys={})
    exc = RuntimeError("429 - tokens per minute exceeded, please try again in 17.44s")
    assert router._is_rate_limit(exc) is True
    assert router._rate_limit_delay(exc) == 17.44
    assert router._rate_limit_delay(exc, cap=10.0) == 10.0
    assert router._rate_limit_delay(RuntimeError("network error")) == 8.0
