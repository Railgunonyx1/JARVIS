"""Groq LLM Provider - Ultra-fast inference via GroqCloud.

Supports multi-key rotation on rate limit / quota error.
"""

import importlib.util
import logging
import time
from collections.abc import AsyncIterator

from providers.base import LLMProvider, LLMResponse
from providers.types import openai_tools_param, parse_openai_tool_calls

logger = logging.getLogger("jarvis.providers.groq")


class GroqProvider(LLMProvider):
    def __init__(self, config: dict, api_key: str, extra_keys: list[str] | None = None):
        super().__init__("groq", config)
        self._keys = [k for k in [api_key] + (extra_keys or []) if k]
        self._key_index = 0
        self._client = None
        self._client_key_index = -1
        self._sdk_package = "groq"
        self._check_package()

    def _check_package(self) -> bool:
        try:
            # find_spec is cheap and does NOT execute the SDK — the real
            # import happens lazily in _get_client() on first request.
            self._package_ok = importlib.util.find_spec("groq") is not None
            if not self._package_ok:
                self._package_error = "groq package not installed"
            return self._package_ok
        except Exception:
            self._package_ok = False
            self._package_error = "groq package not importable"
            return False

    def _get_client(self):
        import groq
        current_key = self._keys[self._key_index]
        if self._client is None or self._client_key_index != self._key_index:
            # max_retries=0: surface 429/5xx immediately so _rotate_key() and
            # the router fallback handle them fast — the SDK's default
            # exponential backoff sleeps 35-50s per Retry-After.
            self._client = groq.AsyncGroq(api_key=current_key, max_retries=0)
            self._client_key_index = self._key_index
            logger.info("Groq: using key index %d", self._key_index)
        return self._client

    def _rotate_key(self):
        if len(self._keys) > 1:
            self._key_index = (self._key_index + 1) % len(self._keys)
            self._client = None
            self._client_key_index = -1
            logger.info("Groq: rotated to key index %d", self._key_index)

    def _is_rate_limit_error(self, error_str: str) -> bool:
        lower = error_str.lower()
        return any(word in lower for word in ["rate", "limit", "quota", "429", "too many", "credits"])

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
    ) -> LLMResponse:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        tool_param = openai_tools_param(tools)
        start = time.time()
        attempts = 0
        while attempts < len(self._keys):
            client = self._get_client()
            try:
                kwargs = {}
                if tool_param:
                    kwargs["tools"] = tool_param
                response = await client.chat.completions.create(
                    model=self.config.get("model", "llama-3.1-8b-instant"),
                    messages=full_messages,
                    max_tokens=max_tokens or self.config.get("max_tokens", 2048),
                    temperature=temperature or self.config.get("temperature", 0.7),
                    **kwargs,
                )
                latency = (time.time() - start) * 1000
                choice = response.choices[0]
                usage = response.usage
                tool_calls = parse_openai_tool_calls(choice.message)

                result = LLMResponse(
                    text=choice.message.content or "",
                    model=response.model,
                    provider="groq",
                    tokens_prompt=usage.prompt_tokens if usage else 0,
                    tokens_completion=usage.completion_tokens if usage else 0,
                    tokens_used=(usage.prompt_tokens + usage.completion_tokens) if usage else 0,
                    latency_ms=latency,
                    finish_reason=choice.finish_reason or "stop",
                    tool_calls=tool_calls,
                )
                self.record_success(latency)
                return result
            except Exception as e:
                error_str = str(e)
                if self._is_rate_limit_error(error_str):
                    self.record_rate_limit()
                else:
                    self.record_failure(error_str)
                if self._is_rate_limit_error(error_str) and attempts < len(self._keys) - 1:
                    self._rotate_key()
                    attempts += 1
                    continue
                raise

    async def complete_stream(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
    ) -> AsyncIterator[str]:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        tool_param = openai_tools_param(tools)
        start = time.time()
        attempts = 0
        while attempts < len(self._keys):
            client = self._get_client()
            try:
                kwargs = {}
                if tool_param:
                    kwargs["tools"] = tool_param
                stream = await client.chat.completions.create(
                    model=self.config.get("model", "llama-3.1-8b-instant"),
                    messages=full_messages,
                    max_tokens=max_tokens or self.config.get("max_tokens", 2048),
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
                error_str = str(e)
                if self._is_rate_limit_error(error_str):
                    self.record_rate_limit()
                else:
                    self.record_failure(error_str)
                if self._is_rate_limit_error(error_str) and attempts < len(self._keys) - 1:
                    self._rotate_key()
                    attempts += 1
                    continue
                raise
