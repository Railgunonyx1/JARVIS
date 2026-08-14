"""OpenRouter Provider - Gateway to free and paid models via OpenRouter API.

Supports multiple API keys with automatic rotation on rate limit/quota errors.
"""

import logging
import time
from collections.abc import AsyncIterator

from providers.base import LLMProvider, LLMResponse
from providers.types import openai_tools_param, parse_openai_tool_calls

logger = logging.getLogger("jarvis.providers.openrouter")


class OpenRouterProvider(LLMProvider):
    captures_stream_tool_calls = True

    def __init__(self, config: dict, api_key: str, extra_keys: list[str] | None = None):
        super().__init__("openrouter", config)
        self._all_keys = [api_key] + (extra_keys or [])
        self._key_index = 0
        self.api_key = self._all_keys[0]
        self.base_url = config.get("base_url", "https://openrouter.ai/api/v1")
        self._client = None
        self._sdk_package = "openai"

    def _get_client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                max_retries=0,
            )
        return self._client

    def _rotate_key(self):
        """Switch to the next API key."""
        if len(self._all_keys) <= 1:
            return False
        old_index = self._key_index
        self._key_index = (self._key_index + 1) % len(self._all_keys)
        self.api_key = self._all_keys[self._key_index]
        # Reset client so it uses the new key
        self._client = None
        logger.info("Rotated to OpenRouter key #%d", self._key_index + 1)
        return old_index != self._key_index

    def _is_rate_limit_or_quota_error(self, error: str) -> bool:
        error_lower = error.lower()
        return any(s in error_lower for s in [
            "rate limit", "429", "quota", "too many requests",
            "credits", "billing", "limit exceeded",
        ])

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
        last_error = None
        attempts = 0

        while attempts < len(self._all_keys):
            client = self._get_client()
            start = time.time()
            try:
                kwargs = {}
                if tool_param:
                    kwargs["tools"] = tool_param
                response = await client.chat.completions.create(
                    model=self.config.get("model", "nvidia/nemotron-3-ultra-550b-a55b:free"),
                    messages=full_messages,
                    max_tokens=max_tokens or self.config.get("max_tokens", 4096),
                    temperature=temperature or self.config.get("temperature", 0.7),
                    extra_headers={
                        "HTTP-Referer": "https://jarvis-mkx.local",
                        "X-Title": "JARVIS MK-X",
                    },
                    **kwargs,
                )
                latency = (time.time() - start) * 1000
                choice = response.choices[0]
                usage = response.usage

                prompt_tokens = usage.prompt_tokens if usage and hasattr(usage, 'prompt_tokens') else 0
                completion_tokens = usage.completion_tokens if usage and hasattr(usage, 'completion_tokens') else 0

                result = LLMResponse(
                    text=choice.message.content or "",
                    model=response.model or "unknown",
                    provider="openrouter",
                    tokens_prompt=prompt_tokens,
                    tokens_completion=completion_tokens,
                    tokens_used=prompt_tokens + completion_tokens,
                    latency_ms=latency,
                    finish_reason=choice.finish_reason or "stop",
                    tool_calls=parse_openai_tool_calls(choice.message),
                )
                self.record_success(latency)
                return result
            except Exception as e:
                last_error = e
                error_str = str(e)
                logger.warning("OpenRouter key #%d failed: %s", self._key_index + 1, error_str)

                if self._is_rate_limit_or_quota_error(error_str) and self._rotate_key():
                    self.record_rate_limit()
                    attempts += 1
                    continue

                self.record_failure(error_str)
                raise

        raise RuntimeError(f"All {len(self._all_keys)} OpenRouter keys exhausted. Last error: {last_error}")

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
        last_error = None
        attempts = 0

        while attempts < len(self._all_keys):
            client = self._get_client()
            start = time.time()
            try:
                kwargs = {}
                if tool_param:
                    kwargs["tools"] = tool_param
                stream = await client.chat.completions.create(
                    model=self.config.get("model", "nvidia/nemotron-3-ultra-550b-a55b:free"),
                    messages=full_messages,
                    max_tokens=max_tokens or self.config.get("max_tokens", 4096),
                    temperature=temperature or self.config.get("temperature", 0.7),
                    stream=True,
                    extra_headers={
                        "HTTP-Referer": "https://jarvis-mkx.local",
                        "X-Title": "JARVIS MK-X",
                    },
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
                logger.warning("OpenRouter key #%d stream failed: %s", self._key_index + 1, error_str)

                if self._is_rate_limit_or_quota_error(error_str) and self._rotate_key():
                    self.record_rate_limit()
                    attempts += 1
                    continue

                self.record_failure(error_str)
                raise

        raise RuntimeError(f"All {len(self._all_keys)} OpenRouter keys exhausted. Last error: {last_error}")
