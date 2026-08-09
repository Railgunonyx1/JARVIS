"""Google Gemini Provider - Multi-modal AI via Google AI Studio."""

import time
import logging
import warnings
from typing import AsyncIterator, Optional

from providers.base import LLMProvider, LLMResponse
from providers.types import json_args, parse_gemini_function_calls, to_gemini_tools

logger = logging.getLogger("jarvis.providers.gemini")

# The deprecated google.generativeai SDK raises a FutureWarning at import that
# is attributed to importlib via stacklevel, so it evades module-scoped
# filters. Match on the message text to keep it out of user-facing output.
warnings.filterwarnings("ignore", category=FutureWarning,
                        message=r"(?s).*google\.generativeai")


class GeminiProvider(LLMProvider):
    def __init__(self, config: dict, api_key: str):
        super().__init__("gemini", config)
        self.api_key = api_key
        self._client = None
        self._sdk_package = "google.generativeai"

    def _get_client(self):
        if self._client is None:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(
                model_name=self.config.get("model", "gemini-2.0-flash"),
            )
        return self._client

    def _convert_messages(self, messages: list[dict], system_prompt: Optional[str]):
        """Convert OpenAI-format messages (incl. tool_calls) to Gemini format."""
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [system_prompt]})
            contents.append({"role": "model", "parts": ["Understood. I will follow these instructions."]})

        id_to_name: dict[str, str] = {}
        for msg in messages:
            role = msg.get("role")
            if role == "assistant" and msg.get("tool_calls"):
                parts = []
                if msg.get("content"):
                    parts.append(msg["content"])
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    if tc.get("id"):
                        id_to_name[tc["id"]] = name
                    parts.append({
                        "function_call": {
                            "name": name,
                            "args": json_args(fn.get("arguments", "{}")),
                        }
                    })
                contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                fn_name = id_to_name.get(msg.get("tool_call_id", ""), msg.get("name", ""))
                contents.append({
                    "role": "user",
                    "parts": [{
                        "function_response": {
                            "name": fn_name,
                            "response": {"result": msg.get("content", "")},
                        }
                    }],
                })
            else:
                g_role = "model" if role == "assistant" else "user"
                contents.append({"role": g_role, "parts": [msg.get("content", "")]})

        return self._merge_adjacent_user_turns(contents)

    @staticmethod
    def _merge_adjacent_user_turns(contents: list[dict]) -> list[dict]:
        """Gemini forbids consecutive same-role turns; merge adjacent user parts."""
        merged = []
        for entry in contents:
            if entry["role"] == "user" and merged and merged[-1]["role"] == "user":
                merged[-1]["parts"].extend(entry["parts"])
            else:
                merged.append(dict(entry))
        return merged

    async def complete(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[list] = None,
    ) -> LLMResponse:
        client = self._get_client()
        contents = self._convert_messages(messages, system_prompt)

        kwargs = {}
        gemini_tools = to_gemini_tools(tools)
        if gemini_tools:
            kwargs["tools"] = gemini_tools

        start = time.time()
        try:
            import asyncio
            response = await asyncio.to_thread(
                client.generate_content,
                contents,
                generation_config={
                    "max_output_tokens": max_tokens or self.config.get("max_tokens", 8192),
                    "temperature": temperature or self.config.get("temperature", 0.7),
                },
                **kwargs,
            )
            latency = (time.time() - start) * 1000
            try:
                text = response.text or ""
            except Exception:
                text = ""
            tool_calls = parse_gemini_function_calls(response)
            prompt_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
            completion_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

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
        contents = self._convert_messages(messages, system_prompt)

        kwargs = {}
        gemini_tools = to_gemini_tools(tools)
        if gemini_tools:
            kwargs["tools"] = gemini_tools

        start = time.time()
        try:
            import asyncio
            response = await asyncio.to_thread(
                client.generate_content,
                contents,
                generation_config={
                    "max_output_tokens": max_tokens or self.config.get("max_tokens", 8192),
                    "temperature": temperature or self.config.get("temperature", 0.7),
                },
                **kwargs,
                stream=True,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            latency = (time.time() - start) * 1000
            self.record_success(latency)
        except Exception as e:
            self.record_failure(str(e))
            raise
