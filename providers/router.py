"""Provider Router - Intelligent fallback chain with quota management."""

import logging
import time
from collections.abc import AsyncIterator

from reliability_engine.circuit_breaker import CircuitBreaker
from providers.base import LLMProvider, LLMResponse
from providers.gemini_provider import GeminiProvider
from providers.groq_provider import GroqProvider
from providers.ollama_provider import OllamaProvider
from providers.opencode_zen_provider import OpenCodeZenProvider
from providers.openrouter_provider import OpenRouterProvider

logger = logging.getLogger("jarvis.providers.router")


class ProviderRouter:
    """Routes LLM requests through a fallback chain of providers.

    Order: Groq (fastest) → Gemini (complex) → OpenRouter (free) → Ollama (offline)
    Falls back automatically on failure, rate limit, or cooldown.
    """

    def __init__(self, config: dict | None = None, api_keys: dict | None = None):
        self._providers: dict[str, LLMProvider] = {}
        self._chain: list[str] = []
        self._config = config or {}
        self._last_provider: str | None = None
        self._last_model: str | None = None
        self.preferred_provider: str | None = None
        self.preferred_model: str | None = None
        self._warmed = False
        self._available_chain: list[str] | None = None
        self._chain_checked_at: float = 0.0
        self._init_providers(self._config, api_keys or {})

    def _init_providers(self, config: dict, api_keys: dict):
        """Initialize all configured providers."""
        router_cfg = config.get("router", {})
        self._chain = router_cfg.get("fallback_chain", ["groq", "gemini", "openrouter", "ollama"])

        # Circuit breaker tracking per provider, persists across calls
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            "groq": CircuitBreaker(),
            "gemini": CircuitBreaker(),
            "openrouter": CircuitBreaker(),
            "ollama": CircuitBreaker(),
        }

        if "groq" in config and api_keys.get("groq"):
            extra_groq = [k for k in api_keys.get("groq_extra", []) if k]
            self._providers["groq"] = GroqProvider(config["groq"], api_keys["groq"], extra_keys=extra_groq)
        if "gemini" in config and api_keys.get("gemini"):
            self._providers["gemini"] = GeminiProvider(config["gemini"], api_keys["gemini"])
        if "openrouter" in config and api_keys.get("openrouter"):
            extra = [k for k in api_keys.get("openrouter_extra", []) if k]
            self._providers["openrouter"] = OpenRouterProvider(
                config["openrouter"], api_keys["openrouter"], extra_keys=extra,
            )
        if "opencode_zen" in config and api_keys.get("opencode_zen"):
            self._providers["opencode_zen"] = OpenCodeZenProvider(
                config["opencode_zen"], api_keys["opencode_zen"],
            )
        if "ollama" in config:
            self._providers["ollama"] = OllamaProvider(config["ollama"])

        available = [name for name in self._chain if name in self._providers]
        logger.info("Router initialized: %s", " → ".join(available))
        if not available:
            logger.error("No LLM providers available!")

    def warm(self) -> None:
        """Pre-import provider SDK packages in a background thread.

        The first request no longer pays the multi-second SDK import cost;
        the user can keep typing while packages load.
        """
        import threading

        if self._warmed:
            return
        self._warmed = True

        def _run() -> None:
            for provider in self._providers.values():
                try:
                    provider._warm()
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True, name="jarvis-provider-warmup").start()

    def _get_available_chain(self) -> list[str]:
        """Return providers in order, filtering to available ones.

        Results are cached for 1 second to avoid recomputing the chain on
        every request; provider availability rarely changes faster than that.
        """
        now = time.time()
        if self._available_chain is not None and now - self._chain_checked_at < 1.0:
            return self._available_chain
        chain = [name for name in self._chain if name in self._providers and self._providers[name].is_available]
        self._available_chain = chain
        self._chain_checked_at = now
        return chain

    def _invalidate_chain(self) -> None:
        """Force the next _get_available_chain call to recompute."""
        self._available_chain = None
        self._chain_checked_at = 0.0

    @property
    def status(self) -> dict:
        """Return status of all providers."""
        return {
            name: {
                "available": provider.is_available,
                "model": provider.model,
                "package_ok": provider._package_ok,
                "package_error": provider._package_error or None,
                "health": {
                    "latency_ms": provider.health.latency_ms,
                    "error_rate": provider.health.error_rate,
                    "consecutive_failures": provider.health.consecutive_failures,
                    "cooldown_until": provider.health.cooldown_until,
                },
            }
            for name, provider in self._providers.items()
        }

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
        preferred_provider: str | None = None,
    ) -> LLMResponse:
        """Send completion request with automatic fallback."""
        from runtime.observability.metrics import get_metrics
        from runtime.observability.tracer import get_tracer

        tracer = get_tracer()
        metrics = get_metrics()
        chain = self._get_available_chain()
        if not chain:
            raise RuntimeError("No LLM providers available. Check API keys and network.")

        if preferred_provider and preferred_provider in self._providers:
            chain = [preferred_provider] + [p for p in chain if p != preferred_provider]

        last_error = None
        attempts = 0
        with tracer.span("router.complete") as span:
            for provider_name in chain:
                attempts += 1
                provider = self._providers[provider_name]
                # Circuit breaker check — skip if this provider is currently open
                cb = self._circuit_breakers.get(provider_name)
                if cb and not cb.is_available(provider_name):
                    failures = cb.failures if hasattr(cb, 'failures') else 0
                    logger.warning(
                        "Circuit breaker open for %s (consecutive failures: %d), skipping",
                        provider_name, failures
                    )
                    continue
                try:
                    logger.info("Trying %s (%s)", provider_name, provider.model)
                    response = await provider.complete(messages, system_prompt, max_tokens, temperature, tools)
                    self._last_provider = provider_name
                    self._last_model = provider.model
                    metrics.counter(f"provider.ok.{provider_name}", 1)
                    if span is not None:
                        span.set_attribute("provider", provider_name)
                        span.set_attribute("model", provider.model)
                        span.set_attribute("attempts", attempts)
                        span.set_attribute("latency_ms", response.latency_ms)
                        span.set_attribute("tokens", response.tokens_used)
                    tracer.add_metric("llm.tokens_generated", response.tokens_used)
                    logger.info(
                        "Success via %s: %d tokens, %.0fms",
                        provider_name, response.tokens_used, response.latency_ms,
                    )
                    return response
                except Exception as e:
                    last_error = e
                    metrics.counter(f"provider.fail.{provider_name}", 1)
                    self._invalidate_chain()
                    if span is not None:
                        span.record_event("fallback", {"from": provider_name, "error": str(e)[:120]})
                    logger.warning("Provider %s failed: %s", provider_name, e)
                    continue
            if span is not None:
                span.set_attribute("attempts", attempts)
                span.set_attribute("last_error", str(last_error)[:200])

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    async def complete_stream(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
        preferred_provider: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion with automatic fallback + TTFT/token KPIs.

        Each provider attempt is timed as an ``llm.request`` span. The first
        chunk records ``ttft_ms`` (time to first token); completion records
        ``tokens_estimated`` (chars/4, since streams carry no usage) and
        ``tokens_per_second``. These are also published as ``llm.ttft_ms`` /
        ``llm.tokens_generated`` metrics for aggregation.
        """
        from runtime.observability.metrics import get_metrics
        from runtime.observability.tracer import get_tracer

        tracer = get_tracer()
        metrics = get_metrics()
        chain = self._get_available_chain()
        if not chain:
            raise RuntimeError("No LLM providers available.")

        if preferred_provider and preferred_provider in self._providers:
            chain = [preferred_provider] + [p for p in chain if p != preferred_provider]

        last_error = None
        with tracer.span("router.stream") as span:
            for provider_name in chain:
                provider = self._providers[provider_name]
                try:
                    with tracer.span("llm.request", {"provider": provider_name, "model": provider.model}) as req:
                        start = time.perf_counter()
                        chars = 0
                        first_chunk = True
                        async for chunk in provider.complete_stream(
                            messages, system_prompt, max_tokens, temperature, tools,
                        ):
                            if first_chunk:
                                first_chunk = False
                                ttft_ms = (time.perf_counter() - start) * 1000
                                if req is not None:
                                    req.set_attribute("ttft_ms", round(ttft_ms, 1))
                                    req.record_event("first_token", {"ttft_ms": round(ttft_ms, 1)})
                                tracer.add_metric("llm.ttft_ms", ttft_ms)
                                metrics.observe("llm.ttft_ms", ttft_ms)
                            chars += len(chunk)
                            yield chunk
                        elapsed_ms = (time.perf_counter() - start) * 1000
                        tokens = max(1, chars // 4)
                        tokens_per_second = (tokens / (elapsed_ms / 1000.0)) if elapsed_ms > 0 else 0.0
                        if req is not None:
                            req.set_attribute("chars", chars)
                            req.set_attribute("tokens_estimated", tokens)
                            req.set_attribute("generation_ms", round(elapsed_ms, 1))
                            req.set_attribute("tokens_per_second", round(tokens_per_second, 1))
                        tracer.add_metric("llm.tokens_generated", tokens)
                    self._last_provider = provider_name
                    self._last_model = provider.model
                    self._invalidate_chain()
                    metrics.counter(f"provider.ok.{provider_name}", 1)
                    if span is not None:
                        span.set_attribute("provider", provider_name)
                        span.set_attribute("model", provider.model)
                    return  # Stream completed successfully
                except Exception as e:
                    last_error = e
                    metrics.counter(f"provider.fail.{provider_name}", 1)
                    self._invalidate_chain()
                    if span is not None:
                        span.record_event("fallback", {"from": provider_name, "error": str(e)[:120]})
                    logger.warning("Provider %s stream failed: %s", provider_name, e)
                    continue
            if span is not None:
                span.set_attribute("last_error", str(last_error)[:200])

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    def reset_provider(self, name: str):
        """Reset a specific provider's health and quotas."""
        if name in self._providers:
            self._providers[name].reset()
            logger.info("Reset provider: %s", name)
