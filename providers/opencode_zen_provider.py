"""OpenCode Zen Provider — Free models via OpenCode Zen API.

Uses OpenAI-compatible endpoint at https://opencode.ai/zen/v1/chat/completions
Free models: Big Pickle, DeepSeek V4 Flash Free, MiMo-V2.5 Free, etc.
"""

import time
import logging
from typing import AsyncIterator, Optional

from providers.base import LLMProvider, LLMResponse
from providers.types import openai_tools_param, parse_openai_tool_calls

logger = logging.getLogger("jarvis.providers.opencode_zen")


class OpenCodeZenProvider(LLMProvider):
    def __init__(self, config: dict, api_key: str):
        super().__init__("opencode_zen", config)
        self.api_key = api_key
        self.base_url = config.get("base_url", "https://opencode.ai/zen/v1")
        self._client = None
        self._sdk_package = "openai"

    def _get_client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    async def complete(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[list] = None,
    ) -> LLMResponse:
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
            response = await client.chat.completions.create(
                model=self.config.get("model", "nemotron-3-ultra-free"),
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
                provider="opencode_zen",
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
            self.record_failure(str(e))
            raise

    async def complete_stream(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[list] = None,
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
                model=self.config.get("model", "nemotron-3-ultra-free"),
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
            self.record_failure(str(e))
            raise
