"""Mistral Provider — OpenAI-compatible endpoint at https://api.mistral.ai/v1.

Supports multi-key rotation on rate limit (free tier is 1 RPM per key).
"""

import logging
import time
from collections.abc import AsyncIterator

from providers.base import LLMProvider, LLMResponse
from providers.types import openai_tools_param, parse_openai_tool_calls

logger = logging.getLogger("jarvis.providers.mistral")


class MistralProvider(LLMProvider):
    def __init__(self, config: dict, api_key: str, extra_keys: list[str] | None = None):
        super().__init__("mistral", config)
        self._keys = [k for k in [api_key] + (extra_keys or []) if k]
        self._key_index = 0
        self.api_key = self._keys[0]
        self.base_url = config.get("base_url", "https://api.mistral.ai/v1")
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

    def _rotate_key(self) -> bool:
        if len(self._keys) <= 1:
            return False
        old = self._key_index
        self._key_index = (self._key_index + 1) % len(self._keys)
        self.api_key = self._keys[self._key_index]
        self._client = None
        logger.info("Mistral: rotated to key index %d", self._key_index)
        return old != self._key_index

    @staticmethod
    def _is_rate_limit_error(error_str: str) -> bool:
        lower = error_str.lower()
        return any(word in lower for word in ["rate", "limit", "quota", "429", "too many"])

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
    ) -> LLMResponse:
        tool_param = openai_tools_param(tools)
        attempts = 0
        while attempts < len(self._keys):
            client = self._get_client()
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)
            start = time.time()
            try:
                kwargs = {}
                if tool_param:
                    kwargs["tools"] = tool_param
                response = await client.chat.completions.create(
                    model=self.config.get("model", "mistral-small-latest"),
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
                    model=response.model or self.config.get("model", "unknown"),
                    provider="mistral",
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
                if self._is_rate_limit_error(error_str):
                    self.record_rate_limit()
                else:
                    self.record_failure(error_str)
                if self._is_rate_limit_error(error_str) and self._rotate_key():
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
        client = self._get_client()
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        tool_param = openai_tools_param(tools)
        start = time.time()
        try:
            kwargs = {}
            if tool_param:
                kwargs["tools"] = tool_param
            stream = await client.chat.completions.create(
                model=self.config.get("model", "mistral-small-latest"),
                messages=full_messages,
                max_tokens=max_tokens or self.config.get("max_tokens", 4096),
                temperature=temperature or self.config.get("temperature", 0.7),
                stream=True,
                **kwargs,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            latency = (time.time() - start) * 1000
            self.record_success(latency)
        except Exception as e:
            error_str = str(e)
            if self._is_rate_limit_error(error_str):
                self.record_rate_limit()
            else:
                self.record_failure(error_str)
            raise
