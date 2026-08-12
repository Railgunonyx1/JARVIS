"""Ollama Provider - Local inference for privacy-first / offline mode."""

import importlib.util
import logging
import time
from collections.abc import AsyncIterator

from providers.base import LLMProvider, LLMResponse
from providers.types import openai_tools_param, parse_ollama_tool_calls

logger = logging.getLogger("jarvis.providers.ollama")


class OllamaProvider(LLMProvider):
    def __init__(self, config: dict):
        super().__init__("ollama", config)
        self.base_url = config.get("base_url", "http://127.0.0.1:11434")
        self._client = None
        self._sdk_package = "ollama"
        self._check_package()

    def _check_package(self) -> bool:
        try:
            # find_spec is cheap and does NOT execute the SDK — the real
            # import happens lazily in _get_client() on first request.
            self._package_ok = importlib.util.find_spec("ollama") is not None
            if not self._package_ok:
                self._package_error = "ollama package not installed"
            return self._package_ok
        except Exception:
            self._package_ok = False
            self._package_error = "ollama package not importable"
            return False

    def _get_client(self):
        if self._client is None:
            import ollama
            self._client = ollama.AsyncClient(host=self.base_url)
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
            response = await client.chat(
                model=self.config.get("model", "qwen2.5:1.5b"),
                messages=full_messages,
                options={
                    "num_predict": max_tokens or self.config.get("max_tokens", 2048),
                    "temperature": temperature or self.config.get("temperature", 0.7),
                    "num_ctx": self.config.get("num_ctx", 4096),
                },
                **kwargs,
            )
            latency = (time.time() - start) * 1000
            message = response["message"]
            text = message.get("content") or ""
            prompt_tokens = response.get("prompt_eval_count", 0)
            completion_tokens = response.get("eval_count", 0)

            result = LLMResponse(
                text=text,
                model=self.config.get("model", "qwen2.5:1.5b"),
                provider="ollama",
                tokens_prompt=prompt_tokens,
                tokens_completion=completion_tokens,
                tokens_used=prompt_tokens + completion_tokens,
                latency_ms=latency,
                finish_reason="stop",
                tool_calls=parse_ollama_tool_calls(message),
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
            stream = await client.chat(
                model=self.config.get("model", "qwen2.5:1.5b"),
                messages=full_messages,
                options={
                    "num_predict": max_tokens or self.config.get("max_tokens", 2048),
                    "temperature": temperature or self.config.get("temperature", 0.7),
                    "num_ctx": self.config.get("num_ctx", 4096),
                },
                **kwargs,
                stream=True,
            )
            async for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    yield chunk["message"]["content"]
            latency = (time.time() - start) * 1000
            self.record_success(latency)
        except Exception as e:
            self.record_failure(str(e))
            raise
