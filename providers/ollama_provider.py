"""Ollama Provider - Local inference for privacy-first / offline mode."""

import importlib.util
import json
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
        self._daemon_ok = False
        self._check_package()

    def _check_package(self) -> bool:
        try:
            # find_spec is cheap and does NOT execute the SDK — the real
            # import happens lazily in _get_client() on first request.
            self._package_ok = importlib.util.find_spec("ollama") is not None
            if not self._package_ok:
                self._package_error = "ollama package not installed"
                return False
        except Exception:
            self._package_ok = False
            self._package_error = "ollama package not importable"
            return False
        # Probe daemon availability via /api/tags
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                self._daemon_ok = resp.status == 200
        except Exception:
            self._daemon_ok = False
        return True

    @property
    def is_available(self) -> bool:
        if not self._package_ok or not self._daemon_ok:
            return False
        return self.health.available and self.check_quota()

    def _get_client(self):
        if self._client is None:
            import ollama
            self._client = ollama.AsyncClient(host=self.base_url)
        return self._client

    def _convert_messages(self, messages: list[dict], system_prompt: str | None = None) -> list[dict]:
        """Ollama's SDK validates messages via pydantic and requires
        ``tool_calls[].function.arguments`` to be a dict, not a JSON string."""
        out = []
        if system_prompt:
            out.append({"role": "system", "content": system_prompt})
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                calls = []
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {}) or {}
                    raw = fn.get("arguments", "{}")
                    try:
                        parsed = json.loads(raw) if isinstance(raw, str) else raw
                        if not isinstance(parsed, dict):
                            parsed = {"value": parsed}
                    except (TypeError, ValueError):
                        parsed = {}
                    calls.append({**tc, "function": {**fn, "arguments": parsed}})
                out.append({**msg, "tool_calls": calls})
            else:
                out.append(msg)
        return out

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        full_messages = self._convert_messages(messages, system_prompt)

        # Ollama handles its own tool format — send raw tools, not
        # the compressed OpenAI format (which strips descriptions).
        # Small local models (<=3B params) can only handle a few tools.
        _max_tools = 5 if '1.5b' in self.config.get('model', '') or '1b' in self.config.get('model', '') else 20
        _limited_tools = tools[:_max_tools] if tools and len(tools) > _max_tools else tools
        start = time.time()
        try:
            kwargs = {}
            if _limited_tools:
                kwargs["tools"] = _limited_tools
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
            error_str = str(e)
            from providers.types import classify_provider_error, ErrorKind
            kind = classify_provider_error(error_str)
            if kind in (ErrorKind.RATE_LIMIT, ErrorKind.QUOTA_EXHAUSTED):
                self.record_rate_limit()
            elif kind == ErrorKind.TIMEOUT:
                self.record_failure(error_str)
            elif kind in (ErrorKind.AUTH, ErrorKind.INVALID_REQUEST):
                self.record_failure(error_str)
            else:
                # Connection refused, network errors, model not found, etc.
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
        """Stream text chunks from Ollama.

        NOTE: Ollama's streaming responses can contain tool_calls in later
        chunks, but this implementation only yields text content.  When tools
        are present, the router detects ``captures_stream_tool_calls = False``
        and falls back to a single non-streaming ``complete()`` call, which
        IS reliable for tool execution.  Streaming is only used for pure
        text generation (no tools).
        """
        client = self._get_client()
        full_messages = self._convert_messages(messages, system_prompt)

        # Ollama handles its own tool format — send raw tools, not
        # the compressed OpenAI format (which strips descriptions).
        # Small local models (<=3B params) can only handle a few tools.
        _max_tools = 5 if '1.5b' in self.config.get('model', '') or '1b' in self.config.get('model', '') else 20
        _limited_tools = tools[:_max_tools] if tools and len(tools) > _max_tools else tools
        start = time.time()
        try:
            kwargs = {}
            if _limited_tools:
                kwargs["tools"] = _limited_tools
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
