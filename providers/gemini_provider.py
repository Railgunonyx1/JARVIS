"""Google Gemini Provider - Multi-modal AI via Google AI Studio."""

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from providers.base import LLMProvider, LLMResponse
from providers.types import json_args, parse_gemini_function_calls, to_gemini_tools

logger = logging.getLogger("jarvis.providers.gemini")


class GeminiProvider(LLMProvider):
    def __init__(self, config: dict, api_key: str):
        super().__init__("gemini", config)
        self.api_key = api_key
        self._client = None
        self._sdk_package = "google.generativeai"

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            # Store model name for generate_content calls
            self._model = self.config.get("model", "gemini-2.0-flash")
        return self._client

    def _convert_messages(self, messages: list[dict], system_prompt: str | None = None):
        """Convert OpenAI-format messages (incl. tool_calls) to Gemini Content.

        google-genai 2.x validates contents strictly via pydantic, so we build
        its own Content/Part/FunctionCall/FunctionResponse objects instead of
        hand-rolled dicts.
        """
        from google.genai import types as gtypes

        contents = []
        if system_prompt:
            contents.append(gtypes.Content(role="user", parts=[gtypes.Part(text=system_prompt)]))
            contents.append(gtypes.Content(role="model", parts=[gtypes.Part(text="Understood.")]))

        id_to_name: dict[str, str] = {}
        for msg in messages:
            role = msg.get("role")
            if role == "assistant" and msg.get("tool_calls"):
                parts = []
                if msg.get("content"):
                    parts.append(gtypes.Part(text=msg["content"]))
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    if tc.get("id"):
                        id_to_name[tc["id"]] = name
                    parts.append(gtypes.Part(function_call=gtypes.FunctionCall(
                        name=name, args=json_args(fn.get("arguments", "{}")),
                    )))
                contents.append(gtypes.Content(role="model", parts=parts))
            elif role == "tool":
                fn_name = id_to_name.get(msg.get("tool_call_id", ""), msg.get("name", ""))
                contents.append(gtypes.Content(role="user", parts=[gtypes.Part(
                    function_response=gtypes.FunctionResponse(
                        name=fn_name, response={"result": msg.get("content", "")},
                    )
                )]))
            else:
                g_role = "model" if role == "assistant" else "user"
                contents.append(gtypes.Content(role=g_role, parts=[gtypes.Part(text=msg.get("content", ""))]))

        return self._merge_adjacent_user_turns(contents)

    @staticmethod
    def _merge_adjacent_user_turns(contents: list) -> list:
        """Gemini forbids consecutive same-role turns; merge adjacent user parts."""
        merged = []
        for entry in contents:
            role = entry.role if hasattr(entry, "role") else entry.get("role")
            if role == "user" and merged:
                last = merged[-1]
                last_role = last.role if hasattr(last, "role") else last.get("role")
                if last_role == "user":
                    if hasattr(last, "parts"):
                        last.parts.extend(entry.parts)
                    else:
                        last["parts"].extend(entry["parts"])
                    continue
            merged.append(entry)
        return merged

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        contents = self._convert_messages(messages, system_prompt)

        config: dict[str, Any] = {
            "max_output_tokens": max_tokens or self.config.get("max_tokens", 8192),
            "temperature": temperature or self.config.get("temperature", 0.7),
        }
        gemini_tools = to_gemini_tools(tools)
        if gemini_tools:
            config["tools"] = gemini_tools

        start = time.time()
        try:
            import asyncio
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self._model,
                contents=contents,
                config=config,
            )
            latency = (time.time() - start) * 1000
            try:
                text = response.text or ""
            except Exception:
                text = ""
            tool_calls = parse_gemini_function_calls(response)
            prompt_tokens = (response.usage_metadata.prompt_token_count or 0) if response.usage_metadata else 0
            completion_tokens = (response.usage_metadata.candidates_token_count or 0) if response.usage_metadata else 0

            result = LLMResponse(
                text=text,
                model=self.config.get("model", "gemini-2.0-flash"),
                provider="gemini",
                tokens_prompt=prompt_tokens,
                tokens_completion=completion_tokens,
                tokens_used=prompt_tokens + completion_tokens,
                latency_ms=latency,
                finish_reason="stop",
                tool_calls=tool_calls,
            )
            self.record_success(latency)
            return result
        except Exception as e:
            error_str = str(e)
            from providers.types import classify_provider_error, ErrorKind
            kind = classify_provider_error(error_str)
            if kind in (ErrorKind.RATE_LIMIT, ErrorKind.QUOTA_EXHAUSTED):
                self.record_rate_limit()
            else:
                self.record_failure(error_str)
            raise

    async def complete_stream(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
    ) -> AsyncIterator[str]:
        import asyncio

        client = self._get_client()
        contents = self._convert_messages(messages, system_prompt)

        config: dict[str, Any] = {
            "max_output_tokens": max_tokens or self.config.get("max_tokens", 8192),
            "temperature": temperature or self.config.get("temperature", 0.7),
        }
        gemini_tools = to_gemini_tools(tools)
        if gemini_tools:
            config["tools"] = gemini_tools

        start = time.time()
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        sentinel = object()

        def _produce() -> None:
            try:
                response = client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                    stream=True,
                )
                for chunk in response:
                    if chunk.text:
                        asyncio.run_coroutine_threadsafe(queue.put(chunk.text), loop)
                asyncio.run_coroutine_threadsafe(queue.put(sentinel), loop)
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop)

        loop = asyncio.get_running_loop()
        import threading
        producer = threading.Thread(target=_produce, daemon=True)
        producer.start()

        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
            latency = (time.time() - start) * 1000
            self.record_success(latency)
        except Exception as e:
            error_str = str(e)
            from providers.types import classify_provider_error, ErrorKind
            kind = classify_provider_error(error_str)
            if kind in (ErrorKind.RATE_LIMIT, ErrorKind.QUOTA_EXHAUSTED):
                self.record_rate_limit()
            else:
                self.record_failure(error_str)
            raise
