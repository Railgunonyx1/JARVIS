"""Provider Router - Intelligent fallback chain with quota management."""

import asyncio
import importlib
import json
import logging
import time
import urllib.request
from collections.abc import AsyncIterator
from typing import Any

from providers.base import LLMProvider, LLMResponse
from providers.types import (
    ErrorKind,
    ProviderError,
    RateLimitError,
    classify_provider_error,
    parse_retry_after,
    restore_tool_names,
    sanitize_tools,
)
from reliability_engine.circuit_breaker import CircuitBreaker

logger = logging.getLogger("jarvis.providers.router")

# Lazy provider class loader — avoids importing all 10 provider modules at startup.
_PROVIDER_CLASSES: dict[str, tuple[str, str]] = {
    "groq": ("providers.groq_provider", "GroqProvider"),
    "gemini": ("providers.gemini_provider", "GeminiProvider"),
    "openrouter": ("providers.openrouter_provider", "OpenRouterProvider"),
    "opencode_zen": ("providers.opencode_zen_provider", "OpenCodeZenProvider"),
    "mistral": ("providers.mistral_provider", "MistralProvider"),
    "nvidia_nim": ("providers.nvidia_nim_provider", "NVIDIAProvider"),
    "omni_route": ("providers.omni_route_provider", "OmniRouteProvider"),
    "ollama": ("providers.ollama_provider", "OllamaProvider"),
    "cerebras": ("providers.cerebras_provider", "CerebrasProvider"),
    "deepseek": ("providers.deepseek_provider", "DeepSeekProvider"),
    "huggingface": ("providers.huggingface_provider", "HuggingFaceProvider"),
    # Generic free-tier providers (freellm-apis directory) — one shared module.
    "llm7": ("providers.free_llm_providers", "LLM7Provider"),
    "github_models": ("providers.free_llm_providers", "GitHubModelsProvider"),
    "cloudflare_ai": ("providers.free_llm_providers", "CloudflareAIProvider"),
    "cohere": ("providers.free_llm_providers", "CohereProvider"),
    "sambanova": ("providers.free_llm_providers", "SambaNovaProvider"),
    "zai": ("providers.free_llm_providers", "ZAIProvider"),
    "agnes": ("providers.free_llm_providers", "AgnesProvider"),
    "kilo_code": ("providers.free_llm_providers", "KiloCodeProvider"),
    "scaleway": ("providers.free_llm_providers", "ScalewayProvider"),
    "sakana": ("providers.sakana_provider", "SakanaProvider"),
}


def _lazy_import_provider(name: str) -> type:
    """Import a provider class on demand (avoids importing all at startup)."""
    if name not in _PROVIDER_CLASSES:
        raise ValueError(f"Unknown provider: {name}")
    module_path, class_name = _PROVIDER_CLASSES[name]
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)

# Maximum retry-after delay before we fallback instead of waiting.
_MAX_RETRY_WAIT_S = 5.0


def _ollama_local_fetch(url: str, timeout: int = 3) -> bytes:
    """Fetch a URL bypassing any system proxy — for localhost Ollama reads."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    resp = opener.open(url, timeout=timeout)
    try:
        return resp.read()
    finally:
        resp.close()


class ProviderRouter:
    """Routes LLM requests through a fallback chain of providers.

    Fallback chain is configuration-driven (see config/models.toml).
    Falls back automatically on failure, rate limit, or cooldown.
    """

    def __init__(self, config: dict | None = None, api_keys: dict | None = None):
        self._providers: dict[str, LLMProvider] = {}
        self._chain: list[str] = []
        self._config = config or {}
        self._last_provider: str | None = None
        self._last_model: str | None = None
        self._last_stream_tool_calls: list = []
        self.preferred_provider: str | None = None
        self.preferred_model: str | None = None
        self._warmed = False
        self._available_chain: list[str] | None = None
        self._chain_checked_at: float = 0.0
        # UI notification callback: (event_name, payload) -> None
        # Set by main.py/bridge so the router can emit semantic events
        # instead of relying on Python logging for user-facing messages.
        self.on_provider_event: callable | None = None
        self._init_providers(self._config, api_keys or {})

    def _notify(self, event: str, **payload) -> None:
        """Emit a semantic event for the UI (non-blocking, best-effort)."""
        if self.on_provider_event is not None:
            try:
                self.on_provider_event(event, payload)
            except Exception:
                pass

    def _init_providers(self, config: dict, api_keys: dict):
        """Initialize all configured providers."""
        router_cfg = config.get("router", {})
        self._chain = router_cfg.get("fallback_chain", ["groq", "gemini", "openrouter", "ollama"])

        # Circuit breaker tracking per provider, persists across calls
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            "groq": CircuitBreaker(),
            "gemini": CircuitBreaker(),
            "openrouter": CircuitBreaker(),
            "opencode_zen": CircuitBreaker(),
            "mistral": CircuitBreaker(),
            "nvidia_nim": CircuitBreaker(),
            "omni_route": CircuitBreaker(),
            "ollama": CircuitBreaker(),
            "cerebras": CircuitBreaker(),
            "deepseek": CircuitBreaker(),
            "huggingface": CircuitBreaker(),
            "llm7": CircuitBreaker(),
            "github_models": CircuitBreaker(),
            "cloudflare_ai": CircuitBreaker(),
            "cohere": CircuitBreaker(),
            "sambanova": CircuitBreaker(),
            "zai": CircuitBreaker(),
            "agnes": CircuitBreaker(),
            "kilo_code": CircuitBreaker(),
            "scaleway": CircuitBreaker(),
        }
        for _name, _breaker in self._circuit_breakers.items():
            _breaker.register(_name)

        # Provider constructor kwargs (only loaded when config has the key)
        # every keyed provider supports numbered extra keys (KEY_2, KEY_3...)
        # via <provider>_extra — rotation lives in OpenAICompatProvider._rotate_key
        _PROVIDER_KWARGS: dict[str, dict[str, Any]] = {
            name: {"extra_keys": (
                lambda n=name: [k for k in api_keys.get(n + "_extra", []) if k]
            )}
            for name in (
                "groq", "openrouter", "mistral", "gemini", "deepseek",
                "llm7", "github_models", "cloudflare", "cohere",
                "sambanova", "zai", "agnes", "kilo_code", "scaleway",
                "zen", "together", "fireworks", "cerebras", "nvidia",
                "perplexity", "xai",
            )
            if name in _PROVIDER_CLASSES
        }

        for name in list(config.keys()):
            if name == "router":
                continue
            provider_key = api_keys.get(name)
            # Ollama, omni_route and llm7 don't need API keys — llm7 serves a
            # subset of its menu with the literal anonymous token "unused"
            # (verified 2026-09-20: GLM-5.3-Flash + codestral-latest work).
            if name not in ("ollama", "omni_route", "llm7") and not provider_key:
                continue
            if name not in _PROVIDER_CLASSES:
                continue
            # Vendor-mismatch guard: a key copied from the wrong vendor (e.g.
            # an OpenRouter ``sk-or-v1-…`` pasted as DEEPSEEK_API_KEY) can
            # never authenticate — skip it loudly instead of paying a doomed
            # 401 round-trip in every fallback walk.
            if name == "deepseek" and provider_key.startswith("sk-or-v1-"):
                logger.error(
                    "deepseek: DEEPSEEK_API_KEY is an OpenRouter key "
                    "(sk-or-…). Set a real DeepSeek key or remove it — "
                    "OpenRouter requests should use the openrouter provider."
                )
                continue
            try:
                cls = _lazy_import_provider(name)
                extra = {}
                if name in _PROVIDER_KWARGS:
                    for kw, fn in _PROVIDER_KWARGS[name].items():
                        extra[kw] = fn()
                # Ollama and omni_route have simpler constructors
                if name == "ollama":
                    self._providers[name] = cls(config[name])
                elif name == "omni_route":
                    self._providers[name] = cls(config[name], provider_key or "omni-route")
                else:
                    self._providers[name] = cls(config[name], provider_key, **extra)
            except Exception as e:
                logger.warning("Failed to init provider %s: %s", name, e)

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

    @staticmethod
    def _classify_error(exc: Exception) -> ErrorKind:
        """Structured classification of an exception."""
        if isinstance(exc, RateLimitError):
            return ErrorKind.RATE_LIMIT
        if isinstance(exc, ProviderError):
            return classify_provider_error(str(exc))
        return classify_provider_error(str(exc))

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        """True for transient failures worth retrying once."""
        kind = ProviderRouter._classify_error(exc)
        return kind in (ErrorKind.RATE_LIMIT, ErrorKind.OVERLOADED, ErrorKind.TIMEOUT)

    @staticmethod
    def _should_fallback(exc: Exception) -> bool:
        """True if we should immediately try the next provider."""
        kind = ProviderRouter._classify_error(exc)
        # Always fallback on these — no point retrying
        if kind in (ErrorKind.QUOTA_EXHAUSTED, ErrorKind.AUTH, ErrorKind.INVALID_REQUEST):
            return True
        # Rate limit: fallback if retry-after is too long
        if kind == ErrorKind.RATE_LIMIT:
            retry_after = parse_retry_after(str(exc))
            if retry_after is not None and retry_after > _MAX_RETRY_WAIT_S:
                return True
        return False

    @staticmethod
    def _rate_limit_delay(exc: Exception) -> float:
        """Get retry delay: use provider's hint, capped at _MAX_RETRY_WAIT_S."""
        retry_after = parse_retry_after(str(exc))
        if retry_after is not None:
            return min(retry_after, _MAX_RETRY_WAIT_S)
        # No hint — short wait, not 8 seconds
        import random
        return random.uniform(1.0, 3.0)

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

    def swap_ollama_model(self, model_name: str) -> bool:
        """Swap the active Ollama model at runtime.

        .. deprecated:: Use ``preferred_model`` parameter in ``complete()`` instead.
           This method mutates shared state and is NOT safe for concurrent use.
           Only use for explicit user-initiated model switches (e.g. /model command).

        Returns True if the swap succeeded, False if Ollama is not available.
        """
        ollama = self._providers.get("ollama")
        if ollama is None:
            return False
        old_model = ollama.config.get("model")
        ollama.config["model"] = model_name
        logger.info("Swapped Ollama model: %s → %s", old_model, model_name)
        return True

    def get_ollama_model(self) -> str | None:
        """Return the current Ollama model name, or None if Ollama is not configured."""
        ollama = self._providers.get("ollama")
        if ollama is None:
            return None
        return ollama.config.get("model")

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
        preferred_provider: str | None = None,
        preferred_model: str | None = None,
    ) -> LLMResponse:
        """Send completion request with automatic fallback.

        When ``preferred_model`` is set and the first provider is Ollama,
        the model is swapped before the request (and restored after)."""
        from runtime.observability.metrics import get_metrics
        from runtime.observability.tracer import get_tracer

        tracer = get_tracer()
        metrics = get_metrics()
        chain = self._get_available_chain()
        if not chain:
            raise RuntimeError("No LLM providers available. Check API keys and network.")

        # Request-scoped model: pass directly to provider, never mutate config.
        _request_model = preferred_model

        if preferred_provider and preferred_provider in self._providers:
            chain = [preferred_provider] + [p for p in chain if p != preferred_provider]

        last_error = None
        attempts = 0
        with tracer.span("router.complete") as span:
            for provider_name in chain:
                attempts += 1
                provider = self._providers[provider_name]
                # All providers get sanitized tools; Ollama provider re-maps internally
                tools_param, name_map = sanitize_tools(tools)
                # Circuit breaker check — skip if this provider is currently open
                cb = self._circuit_breakers.get(provider_name)
                if cb and not cb.is_available(provider_name):
                    failures = cb.failures_for(provider_name) if hasattr(cb, 'failures_for') else 0
                    logger.warning(
                        "Circuit breaker open for %s (consecutive failures: %d), skipping",
                        provider_name, failures
                    )
                    continue
                try:
                    logger.info("Trying %s (%s)", provider_name, provider.model)
                    # Only Ollama accepts model= parameter; cloud providers don't.
                    _provider_kwargs = {}
                    if provider_name == "ollama" and _request_model:
                        _provider_kwargs["model"] = _request_model
                    response = await provider.complete(messages, system_prompt, max_tokens, temperature, tools_param, **_provider_kwargs)  # noqa: E501
                    if name_map:
                        restore_tool_names(response.tool_calls, name_map)
                    self._last_provider = provider_name
                    self._last_model = _request_model or provider.model
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
                    kind = self._classify_error(e)
                    metrics.counter(f"provider.fail.{provider_name}", 1)
                    self._invalidate_chain()
                    if span is not None:
                        span.record_event("fallback", {
                            "from": provider_name, "kind": kind.value,
                            "error": str(e)[:120],
                        })

                    # Immediately fallback for permanent errors
                    if self._should_fallback(e):
                        provider.record_rate_limit() if kind == ErrorKind.RATE_LIMIT else provider.record_failure(str(e)[:200])  # noqa: E501
                        self._notify("provider.rate_limit",
                                     provider=provider_name, message=kind.value,
                                     kind="warning", switching=True)
                        logger.info("%s: %s — falling back", provider_name, kind.value)
                        continue

                    # One retry for transient errors (rate limit / overload / timeout)
                    if self._is_rate_limit(e):
                        provider.record_rate_limit()
                        delay = self._rate_limit_delay(e)
                        self._notify("provider.rate_limit",
                                     provider=provider_name, message="rate limited",
                                     kind="warning", retry_after=delay)
                        logger.info("%s: retrying in %.1fs", provider_name, delay)
                        await asyncio.sleep(delay)
                        try:
                            _pk = {}
                            if provider_name == "ollama" and _request_model:
                                _pk["model"] = _request_model
                            response = await provider.complete(
                                messages, system_prompt, max_tokens, temperature, tools_param,
                                **_pk,
                            )
                            if name_map:
                                restore_tool_names(response.tool_calls, name_map)
                            self._last_provider = provider_name
                            self._last_model = _request_model or provider.model
                            metrics.counter(f"provider.ok.{provider_name}", 1)
                            return response
                        except Exception as retry_err:
                            last_error = retry_err
                            metrics.counter(f"provider.fail.{provider_name}", 1)
                            provider.record_rate_limit()

                    # Non-retryable failure
                    provider.record_failure(str(e)[:200])
                    logger.warning("%s: %s (%s)", provider_name, kind.value, str(e)[:100])
                    continue
            if span is not None:
                span.set_attribute("attempts", attempts)
                span.set_attribute("last_error", str(last_error)[:200])

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    def _model_for(self, provider_name: str, request_model: str | None) -> str | None:
        """Resolve the request-scoped model override for one provider.

        Ollama accepts any local tag, so the caller's choice always applies
        there. Cloud providers only honor a choice that matches a model they
        are configured for (their configured model or fallback) — a choice
        aimed at one provider must never silently rewrite another's request.
        """
        if not request_model:
            return None
        if provider_name == "ollama":
            return request_model
        provider = self._providers.get(provider_name)
        if provider is None:
            return None
        owned = {provider.model, provider.config.get("model")}
        fallback = self._config.get(provider_name, {}).get("fallback", {})
        if isinstance(fallback, dict) and fallback.get("model"):
            owned.add(fallback.get("model"))
        owned.discard(None)
        return request_model if request_model in owned else None

    def list_models(self) -> list[dict]:
        """Every selectable model across the configured provider fleet.

        One entry per provider's primary and fallback model plus its dynamic
        Ollama tags, marked with availability so the UI can gray out providers
        that are offline (missing key, rate-limited, circuit open).
        """
        models: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for name in self._chain:
            provider = self._providers.get(name)
            if provider is None:
                continue
            cfg = self._config.get(name, {}) or {}
            available = bool(provider.is_available)
            entries: list[tuple[str, str]] = [(provider.model, "primary")]
            fallback = cfg.get("fallback", {})
            if isinstance(fallback, dict) and fallback.get("model") and fallback.get("model") != provider.model:
                entries.append((fallback["model"], "fallback"))
            if name == "ollama":
                for tag in self.ollama_tags():
                    entries.append((tag, "local"))
            for model, kind in entries:
                key = (name, model)
                if not model or key in seen:
                    continue
                seen.add(key)
                models.append({
                    "id": f"{name}/{model}",
                    "provider": name,
                    "model": model,
                    "kind": kind,
                    "available": available,
                })
        return models

    def ollama_tags(self) -> list[str]:
        """Live model tags from a running Ollama daemon ([] when offline)."""
        ollama = self._providers.get("ollama")
        if ollama is None:
            return []
        try:
            raw = _ollama_local_fetch(f"{ollama.base_url}/api/tags", timeout=3)
            data = json.loads(raw)
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            return []

    async def complete_stream(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
        preferred_provider: str | None = None,
        preferred_model: str | None = None,
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
        # Consume any half-open probes this chain build admitted: the probe
        # must be spent by REAL traffic, never by read-only is_available
        # observers (status endpoint, UI polling) — see LLMProvider.consume_probe.
        for _probe_name in chain:
            # getattr: minimal test fakes may not implement the optional
            # probe contract (mirrors the captures_stream_tool_calls pattern).
            getattr(self._providers[_probe_name], "consume_probe", lambda: None)()
        if not chain:
            raise RuntimeError("No LLM providers available.")

        if preferred_provider and preferred_provider in self._providers:
            chain = [preferred_provider] + [p for p in chain if p != preferred_provider]

        _request_model = preferred_model
        last_error = None
        with tracer.span("router.stream") as span:
            for provider_name in chain:
                provider = self._providers[provider_name]
                # Request-scoped model override: honor the caller's model on
                # whichever provider actually owns it (Ollama swap + cloud
                # providers whose configured model matches the choice).
                _stream_model = self._model_for(provider_name, _request_model)
                tools_param, name_map = sanitize_tools(tools)
                retries = 0
                while True:
                    try:
                        with tracer.span("llm.request", {"provider": provider_name, "model": provider.model}) as req:
                            start = time.perf_counter()
                            chars = 0
                            first_chunk = True
                            async for chunk in provider.complete_stream(
                                messages, system_prompt, max_tokens, temperature, tools_param,
                                model=_stream_model,
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
                        self._last_model = _request_model or provider.model
                        self._invalidate_chain()
                        metrics.counter(f"provider.ok.{provider_name}", 1)
                        if span is not None:
                            span.set_attribute("provider", provider_name)
                            span.set_attribute("model", provider.model)
                        return  # Stream completed successfully
                    except Exception as e:
                        kind = self._classify_error(e)
                        # Before first token: safe to retry or fallback
                        if first_chunk:
                            if self._is_rate_limit(e) and retries < 1:
                                # Transient throttle with retry budget left:
                                # record_rate_limit never feeds the breaker.
                                retries += 1
                                provider.record_rate_limit()
                                delay = self._rate_limit_delay(e)
                                self._notify("provider.rate_limit",
                                             provider=provider_name, message="rate limited",
                                             kind="warning", retry_after=delay)
                                logger.info("%s: stream retry in %.1fs", provider_name, delay)
                                await asyncio.sleep(delay)
                                self._invalidate_chain()
                                continue
                            if kind == ErrorKind.RATE_LIMIT:
                                # Retry budget exhausted: still transient by
                                # design (cooldown, not breaker) — switch on.
                                provider.record_rate_limit()
                            else:
                                # ANY other pre-first-token failure counts
                                # toward provider health. Previously only
                                # fallback-worthy classes (quota/auth/
                                # invalid) were counted: hard-down servers
                                # (500/502), dead networks, and exhausted
                                # retryable classes (503/timeout) never
                                # armed the breaker — every turn re-paid
                                # the dead head, including the 1-3s retry
                                # sleep, until process restart.
                                provider.record_failure(str(e)[:200])
                            self._notify("provider.rate_limit",
                                         provider=provider_name, message=kind.value,
                                         kind="warning", switching=True)
                            self._invalidate_chain()  # latch takes effect NOW, not after the 1s cache
                            break  # try next provider
                        # After first token: cannot replay, fall through to next provider
                        last_error = e
                        metrics.counter(f"provider.fail.{provider_name}", 1)
                        self._invalidate_chain()
                        if span is not None:
                            span.record_event("fallback", {"from": provider_name, "kind": kind.value})
                        logger.warning("%s: stream %s", provider_name, kind.value)
                        break
            if span is not None:
                span.set_attribute("last_error", str(last_error)[:200])

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    async def complete_stream_typed(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
        preferred_provider: str | None = None,
        preferred_model: str | None = None,
    ) -> AsyncIterator[tuple[str | None, list | None]]:
        """Like :meth:`complete_stream` but also surfaces streamed tool calls.

        Yields ``(text_chunk, tool_calls_so_far)`` tuples. ``tool_calls`` is
        ``None`` while streaming content; the final marker carries the completed
        :class:`ToolCall` list so the agent loop can stream the answer while
        still executing multi-step tool loops. Providers that cannot capture
        streamed tool calls (gemini) fall back to a single non-streaming
        chunk, so tool use is never broken on those upstreams.
        """
        from runtime.observability.metrics import get_metrics
        from runtime.observability.tracer import get_tracer

        tracer = get_tracer()
        metrics = get_metrics()
        chain = self._get_available_chain()
        # Consume any half-open probes this chain build admitted: the probe
        # must be spent by REAL traffic, never by read-only is_available
        # observers (status endpoint, UI polling) — see LLMProvider.consume_probe.
        for _probe_name in chain:
            # getattr: minimal test fakes may not implement the optional
            # probe contract (mirrors the captures_stream_tool_calls pattern).
            getattr(self._providers[_probe_name], "consume_probe", lambda: None)()
        if not chain:
            raise RuntimeError("No LLM providers available.")

        # Request-scoped model
        _request_model = preferred_model

        if preferred_provider and preferred_provider in self._providers:
            chain = [preferred_provider] + [p for p in chain if p != preferred_provider]

        last_error = None
        with tracer.span("router.stream_typed") as span:
            for provider_name in chain:
                provider = self._providers[provider_name]
                # All providers get sanitized tools; Ollama provider re-maps internally
                tools_param, name_map = sanitize_tools(tools)
                retries = 0
                first_chunk = True
                while True:
                    try:
                        if not getattr(provider, "captures_stream_tool_calls", False):
                            _pk = {}
                            if provider_name == "ollama" and _request_model:
                                _pk["model"] = _request_model
                            response = await provider.complete(
                                messages, system_prompt, max_tokens, temperature, tools_param,
                                **_pk,
                            )
                            if name_map:
                                restore_tool_names(response.tool_calls, name_map)
                            self._last_provider = provider_name
                            self._last_model = _request_model or provider.model
                            self._last_stream_tool_calls = response.tool_calls
                            yield response.text, response.tool_calls
                            if span is not None:
                                span.set_attribute("provider", provider_name)
                                span.set_attribute("model", provider.model)
                            return

                        with tracer.span("llm.request", {"provider": provider_name, "model": provider.model}) as req:
                            start = time.perf_counter()
                            chars = 0
                            first_chunk = True
                            provider._init_stream_tool_calls()
                            _stream_model = _request_model if provider_name == "ollama" else None
                            async for chunk in provider.complete_stream(
                                messages, system_prompt, max_tokens, temperature, tools_param,
                                model=_stream_model,
                            ):
                                if first_chunk:
                                    first_chunk = False
                                    ttft_ms = (time.perf_counter() - start) * 1000
                                    if req is not None:
                                        req.set_attribute("ttft_ms", round(ttft_ms, 1))
                                        req.record_event("first_token", {"ttft_ms": round(ttft_ms, 1)})
                                    tracer.add_metric("llm.ttft_ms", ttft_ms)
                                    metrics.observe("llm.ttft_ms", ttft_ms)
                                if chunk:
                                    chars += len(chunk)
                                    yield chunk, None
                            calls = provider._stream_tool_call_results()
                            if name_map:
                                restore_tool_names(calls, name_map)
                            self._last_provider = provider_name
                            self._last_model = _request_model or provider.model
                            self._last_stream_tool_calls = calls
                            yield None, calls
                            elapsed_ms = (time.perf_counter() - start) * 1000
                            tokens = max(1, chars // 4)
                            if req is not None:
                                req.set_attribute("chars", chars)
                                req.set_attribute("tokens_estimated", tokens)
                                req.set_attribute("generation_ms", round(elapsed_ms, 1))
                            tracer.add_metric("llm.tokens_generated", tokens)
                        self._invalidate_chain()
                        metrics.counter(f"provider.ok.{provider_name}", 1)
                        if span is not None:
                            span.set_attribute("provider", provider_name)
                            span.set_attribute("model", provider.model)
                        return
                    except Exception as e:
                        kind = self._classify_error(e)
                        # Before first token: safe to retry or fallback
                        if first_chunk:
                            if self._is_rate_limit(e) and retries < 1:
                                # Transient throttle with retry budget left:
                                # record_rate_limit never feeds the breaker.
                                retries += 1
                                provider.record_rate_limit()
                                delay = self._rate_limit_delay(e)
                                self._notify("provider.rate_limit",
                                             provider=provider_name, message="rate limited",
                                             kind="warning", retry_after=delay)
                                logger.info(
                                    "%s: stream_typed retry in %.1fs", provider_name, delay
                                )
                                await asyncio.sleep(delay)
                                self._invalidate_chain()
                                continue
                            if kind == ErrorKind.RATE_LIMIT:
                                # Retry budget exhausted: still transient by
                                # design (cooldown, not breaker) — switch on.
                                provider.record_rate_limit()
                            else:
                                # ANY other pre-first-token failure counts
                                # toward provider health — mirrors the
                                # complete_stream except-path so hard-down
                                # servers, dead networks, and exhausted
                                # retryable classes arm the breaker on the
                                # agent (typed) path too.
                                provider.record_failure(str(e)[:200])
                            self._notify("provider.rate_limit",
                                         provider=provider_name, message=kind.value,
                                         kind="warning", switching=True)
                            self._invalidate_chain()  # latch takes effect NOW, not after the 1s cache
                            break  # try next provider
                        # After first token: cannot replay, fall through
                        last_error = e
                        metrics.counter(f"provider.fail.{provider_name}", 1)
                        self._invalidate_chain()
                        if span is not None:
                            span.record_event("fallback", {"from": provider_name, "kind": kind.value})
                        logger.warning("%s: stream_typed %s", provider_name, kind.value)
                        break
            if span is not None:
                span.set_attribute("last_error", str(last_error)[:200])

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    def reset_provider(self, name: str):
        """Reset a specific provider's health and quotas."""
        if name in self._providers:
            self._providers[name].reset()
            logger.info("Reset provider: %s", name)
