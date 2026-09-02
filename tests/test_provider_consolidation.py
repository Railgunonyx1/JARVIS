"""Sprint 6 — Provider consolidation: structured errors, extra headers hook, fallback."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from providers.base import LLMResponse
from providers.openai_compat import OpenAICompatibleProvider
from providers.router import ProviderRouter
from providers.types import (
    ProviderAuthError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
    is_rate_limit_error,
)

# ── Fake providers for router-level tests ────────────────────────────────


class _FakeProvider:
    """Minimal provider stub for router tests."""

    captures_stream_tool_calls = True
    model = "fake"
    is_available = True

    def __init__(self, responses=None, stream_chunks=None, fail_with=None):
        self._responses = responses or []
        self._stream_chunks = stream_chunks or ["hello"]
        self._fail_with = fail_with
        self._calls = 0

    async def complete(self, *args, **kwargs):
        self._calls += 1
        if self._fail_with:
            raise self._fail_with
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(text="ok", model=self.model, provider="fake",
                           tokens_used=1, latency_ms=1, finish_reason="stop")

    async def complete_stream(self, *args, **kwargs) -> AsyncIterator[str]:
        self._calls += 1
        if self._fail_with:
            raise self._fail_with
        for chunk in self._stream_chunks:
            yield chunk

    def _init_stream_tool_calls(self):
        pass

    def _stream_tool_call_results(self):
        return []

    def record_rate_limit(self):
        pass

    def record_success(self, latency_ms):
        pass

    def record_failure(self, error):
        pass


def _router_with_providers(providers: dict) -> ProviderRouter:
    router = ProviderRouter(config={}, api_keys={})
    router._providers = providers
    router._chain = list(providers.keys())
    router._available_chain = list(providers.keys())
    return router


def _ok_response(text="ok"):
    return LLMResponse(text=text, model="test", provider="test",
                       tokens_used=1, latency_ms=1, finish_reason="stop")


# ── Error type tests ────────────────────────────────────────────────────


class TestErrorTypes:
    def test_provider_error_is_base(self):
        err = ProviderError("test", "msg")
        assert isinstance(err, Exception)
        assert err.provider == "test"
        assert err.retryable is False

    def test_rate_limit_error_is_retryable(self):
        err = RateLimitError("test")
        assert err.retryable is True
        assert isinstance(err, ProviderError)

    def test_timeout_error_is_retryable(self):
        err = ProviderTimeoutError("test", 5.0)
        assert err.retryable is True
        assert err.timeout_s == 5.0

    def test_auth_error_not_retryable(self):
        err = ProviderAuthError("test", "bad key")
        assert err.retryable is False

    def test_unavailable_error_is_retryable(self):
        from providers.types import ProviderUnavailableError
        err = ProviderUnavailableError("test")
        assert err.retryable is True

    def test_is_rate_limit_error_detection(self):
        assert is_rate_limit_error("Error code: 429 - rate limit") is True
        # 'quota exceeded' without daily/monthly context is ambiguous — treated as unknown
        assert is_rate_limit_error("quota exceeded") is False
        assert is_rate_limit_error("tokens per minute") is True
        # resource_exhausted without retry hint = quota_exhausted (not retryable)
        assert is_rate_limit_error("resource_exhausted") is False
        assert is_rate_limit_error("connection refused") is False
        # Daily quota is quota_exhausted (not retryable)
        assert is_rate_limit_error("daily quota exceeded") is False
        # Retry hint makes resource_exhausted retryable
        assert is_rate_limit_error("resource_exhausted, try again in 10s") is True


# ── _extra_headers() hook tests ─────────────────────────────────────────


class TestExtraHeadersHook:
    def test_default_returns_empty(self):
        class _TestProvider(OpenAICompatibleProvider):
            pass
        p = _TestProvider("test", {}, "key1")
        assert p._extra_headers() == {}

    def test_subclass_override(self):
        class _MyProvider(OpenAICompatibleProvider):
            def _extra_headers(self):
                return {"X-Custom": "value"}
        p = _MyProvider("test", {}, "key1")
        assert p._extra_headers() == {"X-Custom": "value"}

    def test_openrouter_provider_has_headers(self):
        from providers.openrouter_provider import OpenRouterProvider
        p = OpenRouterProvider({}, "key1")
        headers = p._extra_headers()
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers
        assert headers["X-Title"] == "JARVIS MK-X"


# ── Router fallback tests ───────────────────────────────────────────────


class TestRouterFallback:
    def test_fallback_on_provider_failure(self):
        fail_provider = _FakeProvider(fail_with=RuntimeError("boom"))
        ok_provider = _FakeProvider()
        router = _router_with_providers({"fail": fail_provider, "ok": ok_provider})

        result = asyncio.run(router.complete([{"role": "user", "content": "hi"}]))
        assert result.text == "ok"

    def test_all_providers_fail_raises(self):
        fail1 = _FakeProvider(fail_with=RuntimeError("boom1"))
        fail2 = _FakeProvider(fail_with=RuntimeError("boom2"))
        router = _router_with_providers({"a": fail1, "b": fail2})

        with pytest.raises(RuntimeError, match="All providers failed"):
            asyncio.run(router.complete([{"role": "user", "content": "hi"}]))

    def test_stream_fallback_on_failure(self):
        fail_provider = _FakeProvider(fail_with=RuntimeError("stream boom"))
        ok_provider = _FakeProvider(stream_chunks=["chunk1", "chunk2"])
        router = _router_with_providers({"fail": fail_provider, "ok": ok_provider})

        async def go():
            parts = []
            async for chunk in router.complete_stream([{"role": "user", "content": "hi"}]):
                parts.append(chunk)
            return parts

        assert asyncio.run(go()) == ["chunk1", "chunk2"]

    def test_stream_all_fail_raises(self):
        fail1 = _FakeProvider(fail_with=RuntimeError("boom"))
        fail2 = _FakeProvider(fail_with=RuntimeError("boom"))
        router = _router_with_providers({"a": fail1, "b": fail2})

        async def go():
            async for _ in router.complete_stream([{"role": "user", "content": "hi"}]):
                pass

        with pytest.raises(RuntimeError, match="All providers failed"):
            asyncio.run(go())


# ── Rate-limit retry tests ──────────────────────────────────────────────


class TestRateLimitRetry:
    def test_rate_limit_retry_then_succeed(self):
        provider = _FakeProvider(fail_with=RateLimitError("test"))
        # First call: rate limit → router retries → second call: success
        call_count = 0
        original_complete = provider.complete

        async def patched_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError("test")
            return _ok_response("retried")

        provider.complete = patched_complete
        router = _router_with_providers({"p": provider})
        result = asyncio.run(router.complete([{"role": "user", "content": "hi"}]))
        assert result.text == "retried"


# ── Error propagation tests ─────────────────────────────────────────────


class TestErrorPropagation:
    def test_structured_error_bubbles_through_router(self):
        """Provider raises ProviderAuthError → router catches and continues chain."""
        auth_fail = _FakeProvider(fail_with=ProviderAuthError("test", "bad key"))
        ok_provider = _FakeProvider()
        router = _router_with_providers({"auth_fail": auth_fail, "ok": ok_provider})

        result = asyncio.run(router.complete([{"role": "user", "content": "hi"}]))
        assert result.text == "ok"

    def test_provider_error_not_confused_with_rate_limit(self):
        """Non-retryable ProviderError should NOT trigger rate-limit retry."""
        non_retryable = ProviderError("test", "permanent failure", retryable=False)
        assert is_rate_limit_error(str(non_retryable)) is False


# ── Router _is_rate_limit integration ───────────────────────────────────


class TestRouterIsRateLimit:
    def test_structured_rate_limit_detected(self):
        router = ProviderRouter(config={}, api_keys={})
        assert router._is_rate_limit(RateLimitError("test")) is True

    def test_structured_non_retryable_not_rate_limit(self):
        router = ProviderRouter(config={}, api_keys={})
        assert router._is_rate_limit(ProviderError("test", "err", retryable=False)) is False

    def test_string_429_detected(self):
        router = ProviderRouter(config={}, api_keys={})
        assert router._is_rate_limit(RuntimeError("Error 429")) is True

    def test_normal_error_not_rate_limit(self):
        router = ProviderRouter(config={}, api_keys={})
        assert router._is_rate_limit(RuntimeError("connection reset")) is False


# ── classify_provider_error() tests ────────────────────────────────────


class TestClassifyProviderError:
    def test_429_status_code(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("any error", 429) == ErrorKind.RATE_LIMIT

    def test_429_daily_quota(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("daily quota exceeded", 429) == ErrorKind.QUOTA_EXHAUSTED

    def test_429_substring(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("Error code: 429 - rate limit") == ErrorKind.RATE_LIMIT

    def test_rate_limit_substrings(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("tokens per minute exceeded") == ErrorKind.RATE_LIMIT
        assert classify_provider_error("too many requests") == ErrorKind.RATE_LIMIT
        assert classify_provider_error("request limit reached, retry after 3s") == ErrorKind.RATE_LIMIT

    def test_quota_exhausted_no_retry(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("quota exhausted, credits depleted") == ErrorKind.QUOTA_EXHAUSTED
        assert classify_provider_error("daily quota exceeded") == ErrorKind.QUOTA_EXHAUSTED
        assert classify_provider_error("billing limit") == ErrorKind.QUOTA_EXHAUSTED

    def test_resource_exhausted_retryable(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("resource_exhausted, try again in 10s") == ErrorKind.RATE_LIMIT

    def test_resource_exhausted_permanent(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("resource_exhausted") == ErrorKind.QUOTA_EXHAUSTED

    def test_context_window_substrings(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error(
            "This model's maximum context length is 128000 tokens."
        ) == ErrorKind.CONTEXT_WINDOW
        assert classify_provider_error(
            "context_length_exceeded: reduce the length of the messages"
        ) == ErrorKind.CONTEXT_WINDOW
        assert classify_provider_error(
            "maximum context length exceeded", 400
        ) == ErrorKind.CONTEXT_WINDOW

    def test_auth_errors(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("unauthorized", 401) == ErrorKind.AUTH
        assert classify_provider_error("invalid key", 403) == ErrorKind.AUTH
        assert classify_provider_error("authentication failed") == ErrorKind.AUTH

    def test_timeout(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("request timed out", 504) == ErrorKind.TIMEOUT
        assert classify_provider_error("timeout after 30s") == ErrorKind.TIMEOUT

    def test_network(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("connection refused") == ErrorKind.NETWORK
        assert classify_provider_error("dns resolution failed") == ErrorKind.NETWORK

    def test_overloaded(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("service unavailable", 503) == ErrorKind.OVERLOADED
        assert classify_provider_error("server overloaded") == ErrorKind.OVERLOADED

    def test_unknown_falls_through(self):
        from providers.types import classify_provider_error, ErrorKind
        assert classify_provider_error("something weird happened") == ErrorKind.UNKNOWN


# ── parse_retry_after() tests ──────────────────────────────────────────


class TestParseRetryAfter:
    def test_try_again_in_seconds(self):
        from providers.types import parse_retry_after
        assert parse_retry_after("try again in 17.44s") == 17.44

    def test_retry_after_seconds(self):
        from providers.types import parse_retry_after
        assert parse_retry_after("retry after 2.5s") == 2.5

    def test_no_match(self):
        from providers.types import parse_retry_after
        assert parse_retry_after("connection refused") is None

    def test_malformed_number(self):
        from providers.types import parse_retry_after
        assert parse_retry_after("try again in abc seconds") is None


# ── record_rate_limit() does not count rejected requests ────────────────


class _StubProvider:
    """Minimal concrete provider for testing base-class methods."""
    def __init__(self):
        from providers.base import LLMProvider, ProviderHealth
        # Use a concrete subclass to avoid abstract method error
        class _Concrete(LLMProvider):
            async def complete(self, *a, **kw): pass
            async def complete_stream(self, *a, **kw): yield ''
        self._real = _Concrete('stub', {})
    def __getattr__(self, name):
        return getattr(self._real, name)


class TestRateLimitAccounting:
    def test_rate_limit_does_not_increment_counters(self):
        p = _StubProvider()
        p.record_rate_limit()
        assert p._requests_today == 0
        assert p._requests_this_minute == 0
        assert p._rate_limit_count == 1

    def test_rate_limit_progressive_cooldown(self):
        import time
        p = _StubProvider()
        now = time.time()
        p.record_rate_limit()
        first_cooldown = p.health.cooldown_until
        assert first_cooldown > now
        p.record_rate_limit()
        second_cooldown = p.health.cooldown_until
        assert second_cooldown >= first_cooldown


# ── is_provider detection in agent loop ─────────────────────────────────


class TestAgentLoopProviderDetection:
    def test_provider_error_detected(self):
        from providers.types import ProviderError
        e = ProviderError("test", "rate limit hit")
        error = str(e)
        is_provider = isinstance(e, (ProviderError, RuntimeError)) and (
            "provider" in error.lower() or "429" in error or "rate limit" in error.lower()
            or "quota" in error.lower() or "overloaded" in error.lower()
        )
        assert is_provider is True

    def test_rate_limit_string_detected(self):
        e = RuntimeError("Error code: 429 - rate limit, try again in 5s")
        error = str(e)
        is_provider = isinstance(e, (ProviderError, RuntimeError)) and (
            "provider" in error.lower() or "429" in error or "rate limit" in error.lower()
            or "quota" in error.lower() or "overloaded" in error.lower()
        )
        assert is_provider is True

    def test_tool_error_not_detected_as_provider(self):
        e = ValueError("shell.execute failed: permission denied")
        error = str(e)
        is_provider = isinstance(e, (ProviderError, RuntimeError)) and (
            "provider" in error.lower() or "429" in error or "rate limit" in error.lower()
            or "quota" in error.lower() or "overloaded" in error.lower()
        )
        assert is_provider is False
