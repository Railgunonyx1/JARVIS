"""OmniRoute Provider — free local AI gateway via OpenAI-compatible endpoint.

OmniRoute (https://github.com/diegosouzapw/OmniRoute) runs a local gateway
that routes requests to upstream providers with a model of ``auto``.
Endpoint: http://localhost:20128/v1
"""

import logging
import time
from collections.abc import AsyncIterator

from providers.base import LLMProvider, LLMResponse
from providers.types import openai_tools_param, parse_openai_tool_calls

logger = logging.getLogger("jarvis.providers.omni_route")


class OmniRouteProvider(LLMProvider):
    def __init__(self, config: dict, api_key: str = "omni-route"):
        super().__init__("omni_route", config)
        self.api_key = api_key or "omni-route"
        self.base_url = config.get("base_url", "http://localhost:20128/v1")
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
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
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
                model=self.config.get("model", "auto"),
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
                provider="omni_route",
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
                model=self.config.get("model", "auto"),
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
