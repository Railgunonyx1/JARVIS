"""Ollama Provider - Local inference for privacy-first / offline mode."""

import importlib.util
import json
import logging
import time
from collections.abc import AsyncIterator

from providers.base import LLMProvider, LLMResponse
from providers.types import ToolCall, parse_ollama_tool_calls

logger = logging.getLogger("jarvis.providers.ollama")


class OllamaProvider(LLMProvider):
    captures_stream_tool_calls = True

    def __init__(self, config: dict):
        super().__init__("ollama", config)
        self.base_url = config.get("base_url", "http://127.0.0.1:11434")
        self._client = None
        self._sdk_package = "ollama"
        self._daemon_ok = False
        self._last_probe_time: float = 0.0
        self._probe_interval: float = 30.0
        fallback_cfg = config.get("fallback", {})
        self._fallback_model = fallback_cfg.get("model") if isinstance(fallback_cfg, dict) else None
        # Model residency management
        self._keep_alive = config.get("keep_alive", "5m")
        self._prewarm_on_start = config.get("prewarm", True)
        self._loaded_models: dict[str, float] = {}
        self._check_package()

    def _probe_daemon(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _check_package(self) -> bool:
        try:
            self._package_ok = importlib.util.find_spec("ollama") is not None
            if not self._package_ok:
                self._package_error = "ollama package not installed"
                return False
        except Exception:
            self._package_ok = False
            self._package_error = "ollama package not importable"
            return False
        self._daemon_ok = self._probe_daemon()
        self._last_probe_time = time.time()
        return True

    def _ensure_daemon(self) -> bool:
        now = time.time()
        if now - self._last_probe_time < self._probe_interval:
            return self._daemon_ok
        self._daemon_ok = self._probe_daemon()
        self._last_probe_time = now
        return self._daemon_ok

    @property
    def is_available(self) -> bool:
        if not self._package_ok:
            return False
        if not self._ensure_daemon():
            return False
        return self.health.available and self.check_quota()

    def _build_options(self, max_tokens: int | None, temperature: float | None) -> dict:
        """Build Ollama options with aggressive performance tuning."""
        return {
            "num_predict": max_tokens if max_tokens is not None else self.config.get("max_tokens", 1024),
            "temperature": temperature if temperature is not None else self.config.get("temperature", 0.4),
            "num_ctx": self.config.get("num_ctx", 2048),
            "num_thread": self.config.get("num_thread", 8),
            "top_k": self.config.get("top_k", 20),
            "top_p": self.config.get("top_p", 0.8),
            "repeat_penalty": 1.0,
            "mirostat": 2,           # Adaptive sampling — better quality/speed ratio
            "mirostat_tau": 5.0,     # Target entropy
            "mirostat_eta": 0.1,     # Learning rate
            "num_gpu": 999,          # Offload all layers to GPU if available
        }

    def prewarm(self, model: str | None = None) -> bool:
        m = model or self.config.get("model", "qwen2.5:1.5b")
        try:
            import json as _json
            import urllib.request
            data = _json.dumps({"model": m, "keep_alive": self._keep_alive}).encode()
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                ok = resp.status == 200
                if ok:
                    self._loaded_models[m] = time.time()
                return ok
        except Exception:
            return False

    def get_loaded_models(self) -> list[dict]:
        try:
            import json as _json
            import urllib.request
            req = urllib.request.Request(f"{self.base_url}/api/ps")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read())
                return data.get("models", [])
        except Exception:
            return []

    def unload_model(self, model: str | None = None) -> bool:
        m = model or self.config.get("model", "qwen2.5:1.5b")
        try:
            import json as _json
            import urllib.request
            data = _json.dumps({"model": m, "keep_alive": 0}).encode()
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    self._loaded_models.pop(m, None)
                return resp.status == 200
        except Exception:
            return False

    def _warm(self) -> None:
        super()._warm()
        if self._prewarm_on_start and self._daemon_ok:
            primary = self.config.get("model", "qwen2.5:1.5b")
            try:
                import threading
                threading.Thread(target=self.prewarm, args=(primary,), daemon=True).start()
            except Exception:
                pass

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

    @staticmethod
    def _max_tools_for_model(model: str) -> int:
        if any(tag in model for tag in ('1.5b', '1b')):
            return 5
        if '3b' in model:
            return 10
        return 20

    def _limit_tools(self, tools: list | None, model: str) -> list | None:
        if not tools:
            return tools
        limit = self._max_tools_for_model(model)
        return tools[:limit] if len(tools) > limit else tools

    async def _chat_once(self, client, model: str, full_messages: list,
                         tools: list | None, max_tokens, temperature) -> LLMResponse:
        """Single Ollama chat() call — factored out for fallback reuse."""
        kwargs = {}
        if tools:
            kwargs["tools"] = tools
        start = time.time()
        response = await client.chat(
            model=model,
            messages=full_messages,
            options=self._build_options(max_tokens, temperature),
            **kwargs,
        )
        latency = (time.time() - start) * 1000
        message = response["message"]
        text = message.get("content") or ""
        prompt_tokens = response.get("prompt_eval_count", 0)
        completion_tokens = response.get("eval_count", 0)
        return LLMResponse(
            text=text,
            model=model,
            provider="ollama",
            tokens_prompt=prompt_tokens,
            tokens_completion=completion_tokens,
            tokens_used=prompt_tokens + completion_tokens,
            latency_ms=latency,
            finish_reason="stop",
            tool_calls=parse_ollama_tool_calls(message),
        )

    async def complete(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        full_messages = self._convert_messages(messages, system_prompt)

        # Request-scoped model: use explicit model param, fall back to config
        primary_model = model or self.config.get("model", "qwen2.5:1.5b")
        try:
            result = await self._chat_once(client, primary_model, full_messages,
                                          self._limit_tools(tools, primary_model), max_tokens, temperature)
            self.record_success(result.latency_ms)
            return result
        except Exception as primary_err:
            if self._fallback_model and self._fallback_model != primary_model:
                try:
                    logger.info("Ollama primary model %s failed, trying fallback %s",
                                primary_model, self._fallback_model)
                    result = await self._chat_once(
                        client, self._fallback_model, full_messages,
                        self._limit_tools(tools, self._fallback_model),
                        max_tokens, temperature)
                    self.record_success(result.latency_ms)
                    return result
                except Exception:
                    pass
            from providers.types import ErrorKind, classify_provider_error
            error_str = str(primary_err)
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
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream text chunks from Ollama.

        Accumulates tool calls from streamed chunks so the router's
        ``_stream_tool_call_results()`` can retrieve them when tools
        are present.  Ollama sends complete tool_calls per chunk (not
        OpenAI-style deltas), so we overwrite on each chunk.
        """
        client = self._get_client()
        full_messages = self._convert_messages(messages, system_prompt)

        primary_model = model or self.config.get("model", "qwen2.5:1.5b")
        start = time.time()
        self._stream_tool_calls = {}
        try:
            async for chunk in self._stream_once(client, primary_model, full_messages, tools, max_tokens, temperature):
                yield chunk
            latency = (time.time() - start) * 1000
            self.record_success(latency)
        except Exception as primary_err:
            if self._fallback_model and self._fallback_model != primary_model:
                try:
                    logger.info("Ollama streaming primary %s failed, trying fallback %s",
                                primary_model, self._fallback_model)
                    self._stream_tool_calls = {}
                    async for chunk in self._stream_once(client, self._fallback_model, full_messages,
                                                        tools, max_tokens, temperature):
                        yield chunk
                    latency = (time.time() - start) * 1000
                    self.record_success(latency)
                    return
                except Exception:
                    pass
            from providers.types import ErrorKind, classify_provider_error
            error_str = str(primary_err)
            kind = classify_provider_error(error_str)
            if kind in (ErrorKind.RATE_LIMIT, ErrorKind.QUOTA_EXHAUSTED):
                self.record_rate_limit()
            else:
                self.record_failure(error_str)
            raise

    async def _stream_once(self, client, model: str, full_messages: list,
                           tools: list | None, max_tokens, temperature) -> None:
        kwargs = {}
        limited = self._limit_tools(tools, model)
        if limited:
            kwargs["tools"] = limited
        stream = await client.chat(
            model=model,
            messages=full_messages,
            options=self._build_options(max_tokens, temperature),
            **kwargs,
            stream=True,
        )
        async for chunk in stream:
            msg = chunk.get("message", {})
            chunk_tools = msg.get("tool_calls") or []
            if chunk_tools:
                calls = parse_ollama_tool_calls(msg)
                for i, call in enumerate(calls):
                    self._stream_tool_calls[i] = {
                        "id": call.id,
                        "name": call.name,
                        "args": [json.dumps(call.arguments)],
                    }
            if "content" in msg and msg["content"]:
                yield msg["content"]

    def _stream_tool_call_results(self) -> list[ToolCall]:
        """Override base class to return accumulated Ollama tool calls.

        Ollama sends complete tool_calls per chunk (not OpenAI-style deltas),
        so we accumulate them in ``_stream_tool_calls`` during streaming.
        """
        calls: list[ToolCall] = []
        for idx in sorted(self._stream_tool_calls):
            slot = self._stream_tool_calls[idx]
            name = slot.get("name", "")
            raw = "".join(slot.get("args", []))
            try:
                arguments = json.loads(raw) if raw.strip() else {}
                if not isinstance(arguments, dict):
                    arguments = {"value": arguments}
            except (TypeError, ValueError):
                arguments = {}
            if name:
                calls.append(ToolCall(name=name, arguments=arguments, id=slot.get("id", f"ollama_{idx}")))
        return calls
