"""OpenAI-compatible provider base class.

Eliminates the duplicated complete/complete_stream/key-rotation pattern
shared by Groq, OpenRouter, Mistral, NVIDIA, OpenCodeZen, and OmniRoute.
Subclasses only need to set ``name``, ``base_url``, ``default_model``,
and optionally ``extra_headers`` or ``_is_rate_limit_error``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

from providers.base import LLMProvider
from providers.types import (
    LLMResponse,
    ProviderError,
    is_rate_limit_error,
    openai_tools_param,
    parse_openai_tool_calls,
)

logger = logging.getLogger("jarvis.providers.openai_compat")


class OpenAICompatibleProvider(LLMProvider):
    """Base for any provider that speaks the OpenAI chat completions API.

    Subclass attributes (set in __init__ before calling super):
        name            e.g. "groq"
        base_url        e.g. "https://api.groq.com/openai/v1"
        default_model   e.g. "llama-3.1-8b-instant"
        extra_headers   dict sent with every request (optional)
        captures_stream_tool_calls  True for OpenAI-compatible streaming
    """

    captures_stream_tool_calls = True

    # Subclasses override to provide provider-specific rate-limit detection
    # if the default ``is_rate_limit_error()`` is insufficient.
    _custom_rate_check: classmethod | None = None

    def __init__(self, name: str, config: dict, api_key: str,
                 extra_keys: list[str] | None = None,
                 base_url: str | None = None,
                 default_model: str | None = None):
        super().__init__(name, config)
        self._keys = [k for k in [api_key] + (extra_keys or []) if k]
        self._key_index = 0
        self.api_key = self._keys[0]
        self.base_url = base_url or config.get("base_url", "")
        self.default_model = default_model or config.get("model", "unknown")
        self._client = None
        self._client_key_index = -1
        self._sdk_package = "openai"
        self._timeout_seconds: float = config.get("timeout_seconds", 120.0)

    # ── Client management ───────────────────────────────────────────────

    def _get_client(self):
        if self._client is None or self._client_key_index != self._key_index:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                max_retries=0,
                timeout=self._timeout_seconds,
            )
            self._client_key_index = self._key_index
            logger.info("%s: using key index %d", self.name, self._key_index)
        return self._client

    def _rotate_key(self) -> bool:
        if len(self._keys) <= 1:
            return False
        old = self._key_index
        self._key_index = (self._key_index + 1) % len(self._keys)
        self.api_key = self._keys[self._key_index]
        self._client = None
        self._client_key_index = -1
        logger.info("%s: rotated to key index %d", self.name, self._key_index)
        return old != self._key_index

    # ── Extra headers hook ──────────────────────────────────────────────

    def _extra_headers(self) -> dict:
        """Override to inject extra HTTP headers into every SDK call."""
        return {}

    # ── Rate-limit detection ────────────────────────────────────────────

    def _check_rate_limit(self, error_str: str) -> bool:
        if self._custom_rate_check is not None:
            return self._custom_rate_check(error_str)
        return is_rate_limit_error(error_str)

    # ── Message building ────────────────────────────────────────────────

    def _build_messages(self, messages: list[dict],
                        system_prompt: str | None = None) -> list[dict]:
        full = []
        if system_prompt:
            full.append({"role": "system", "content": system_prompt})
        full.extend(messages)
        return full

    # ── complete() ──────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
    ) -> LLMResponse:
        full_messages = self._build_messages(messages, system_prompt)
        tool_param = openai_tools_param(tools)
        last_error: Exception | None = None
        attempts = 0

        while attempts < len(self._keys):
            client = self._get_client()
            start = time.time()
            try:
                kwargs: dict = {}
                headers = self._extra_headers()
                if headers:
                    kwargs["extra_headers"] = headers
                if tool_param:
                    kwargs["tools"] = tool_param
                response = await client.chat.completions.create(
                    model=self.config.get("model", self.default_model),
                    messages=full_messages,
                    max_tokens=max_tokens or self.config.get("max_tokens", 4096),
                    temperature=temperature or self.config.get("temperature", 0.7),
                    **kwargs,
                )
                latency = (time.time() - start) * 1000
                choice = response.choices[0]
                usage = response.usage
                result = LLMResponse(
                    text=choice.message.content or "",
                    model=response.model or self.config.get("model", self.default_model),
                    provider=self.name,
                    tokens_prompt=usage.prompt_tokens if usage else 0,
                    tokens_completion=usage.completion_tokens if usage else 0,
                    tokens_used=(usage.prompt_tokens + usage.completion_tokens) if usage else 0,
                    latency_ms=latency,
                    finish_reason=choice.finish_reason or "stop",
                    tool_calls=parse_openai_tool_calls(choice.message),
                )
                self.record_success(latency)
                return result

            except Exception as e:
                error_str = str(e)
                if self._check_rate_limit(error_str):
                    self.record_rate_limit()
                    if self._rotate_key():
                        attempts += 1
                        continue
                else:
                    self.record_failure(error_str)
                raise

        raise ProviderError(self.name, f"all {len(self._keys)} keys exhausted")

    # ── complete_stream() ───────────────────────────────────────────────

    async def complete_stream(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
    ) -> AsyncIterator[str]:
        full_messages = self._build_messages(messages, system_prompt)
        tool_param = openai_tools_param(tools)
        last_error: Exception | None = None
        attempts = 0

        while attempts < len(self._keys):
            client = self._get_client()
            start = time.time()
            try:
                kwargs: dict = {}
                headers = self._extra_headers()
                if headers:
                    kwargs["extra_headers"] = headers
                if tool_param:
                    kwargs["tools"] = tool_param
                stream = await client.chat.completions.create(
                    model=self.config.get("model", self.default_model),
                    messages=full_messages,
                    max_tokens=max_tokens or self.config.get("max_tokens", 4096),
                    temperature=temperature or self.config.get("temperature", 0.7),
                    stream=True,
                    **kwargs,
                )
                self._init_stream_tool_calls()
                async for chunk in stream:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield delta.content
                        self._merge_tool_call_delta(delta.tool_calls)
                latency = (time.time() - start) * 1000
                self.record_success(latency)
                return

            except Exception as e:
                last_error = e
                error_str = str(e)
                if self._check_rate_limit(error_str):
                    self.record_rate_limit()
                    if self._rotate_key():
                        attempts += 1
                        continue
                else:
                    self.record_failure(error_str)
                raise

        raise ProviderError(self.name, f"all {len(self._keys)} keys exhausted (stream)")

    # ── Response builder ─────────────────────────────────────────────────

    def _make_response(self, choice, response, usage, latency_ms: float) -> LLMResponse:
        return LLMResponse(
            text=choice.message.content or "",
            model=response.model or self.config.get("model", self.default_model),
            provider=self.name,
            tokens_prompt=usage.prompt_tokens if usage else 0,
            tokens_completion=usage.completion_tokens if usage else 0,
            tokens_used=(usage.prompt_tokens + usage.completion_tokens) if usage else 0,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason or "stop",
            tool_calls=parse_openai_tool_calls(choice.message),
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} model={self.model!r}>"
