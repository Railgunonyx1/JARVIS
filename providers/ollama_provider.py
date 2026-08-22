"""Ollama Provider - Local inference for privacy-first / offline mode.

Lane-specific inference profiles:
  1.5B → interrupt/quick: small context, minimal tools, low latency
  3B   → normal coding:   medium context, moderate tools, throughput
  4B   → heavy reasoning: larger context, broad tools, quality
"""

import importlib.util
import json
import logging
import os
import time
import urllib.request
from collections.abc import AsyncIterator
from typing import Any

from providers.base import LLMProvider, LLMResponse
from providers.types import ToolCall, parse_ollama_tool_calls

logger = logging.getLogger("jarvis.providers.ollama")

# Adaptive CPU thread count: use os.cpu_count() at import time
_CPU_COUNT = os.cpu_count() or 4


# ── Proxy bypass for localhost connections ─────────────────────────────
# Ollama runs on 127.0.0.1 — it should NEVER go through a proxy.
# This affects both urllib (for health checks) and httpx (used by ollama SDK).
_local_hosts = "127.0.0.1,localhost,::1"
_existing_noproxy = os.environ.get("NO_PROXY", "")
if _local_hosts not in _existing_noproxy:
    sep = "," if _existing_noproxy else ""
    os.environ["NO_PROXY"] = f"{_existing_noproxy}{sep}{_local_hosts}"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]


def _no_proxy_opener() -> urllib.request.OpenerDirector:
    """Create a URL opener that bypasses proxy for localhost."""
    handler = urllib.request.ProxyHandler({})  # Empty dict = no proxy
    return urllib.request.build_opener(handler)


_local_opener = _no_proxy_opener()


def _local_fetch(url: str, timeout: int = 10, **kwargs: Any) -> Any:
    """Fetch a URL bypassing proxy — for localhost/Ollama connections."""
    return _local_opener.open(url, timeout=timeout, **kwargs)


def _local_post(url: str, data: bytes, headers: dict | None = None,
                timeout: int = 10) -> Any:
    """POST to a URL bypassing proxy — for localhost/Ollama connections."""
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    return _local_opener.open(req, timeout=timeout)

# Lane-specific inference profiles — different parameters per model tier
_LANE_PROFILES: dict[str, dict] = {
    # 1.5B interrupt lane: minimize latency, deterministic output
    "interrupt": {
        "num_ctx": 1536,
        "num_predict": 384,
        "temperature": 0.15,
        "top_k": 8,
        "top_p": 0.65,
        "repeat_penalty": 1.0,
        "num_gpu": 999,
        "num_thread": min(_CPU_COUNT, 4),
        "mirostat": 0,
    },
    # 3B normal coding: balance speed and capability
    "normal": {
        "num_ctx": 4096,
        "num_predict": 1536,
        "temperature": 0.3,
        "top_k": 15,
        "top_p": 0.75,
        "repeat_penalty": 1.0,
        "num_gpu": 999,
        "num_thread": _CPU_COUNT,
        "mirostat": 2,
        "mirostat_tau": 4.0,
        "mirostat_eta": 0.1,
    },
    # 4B heavy reasoning: prioritize quality over speed
    "heavy": {
        "num_ctx": 8192,
        "num_predict": 4096,
        "temperature": 0.4,
        "top_k": 25,
        "top_p": 0.85,
        "repeat_penalty": 1.05,
        "num_gpu": 999,
        "num_thread": _CPU_COUNT,
        "mirostat": 2,
        "mirostat_tau": 6.0,
        "mirostat_eta": 0.15,
    },
}

# Tool priority ranking per lane — ranked tools, not first-N
_TOOL_RANKINGS: dict[str, list[str]] = {
    "interrupt": [
        "memory.retrieve", "memory.remember", "memory.stats",
        "system.status", "git.status", "filesystem.read", "filesystem.list",
        "filesystem.diff", "git.diff",
    ],
    "normal": [
        "filesystem.read", "filesystem.write", "filesystem.edit",
        "filesystem.list", "filesystem.search", "filesystem.diff",
        "shell.execute", "git.status", "git.diff", "git.commit",
        "git.log", "git.branch",
        "search.code", "code.symbol", "code.references",
        "memory.retrieve", "memory.remember",
        "test.run", "test.discover",
    ],
    "heavy": [],  # Empty = use all available tools
}


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
        """Check if Ollama is reachable. Uses proxy bypass for localhost."""
        try:
            resp = _local_fetch(f"{self.base_url}/api/tags", timeout=3)
            return resp.status == 200
        except ConnectionRefusedError:
            logger.debug("Ollama not running at %s", self.base_url)
            return False
        except OSError as exc:
            logger.debug("Ollama probe failed: %s", exc)
            return False
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

    def _detect_lane(self, model: str) -> str:
        """Detect the lane (interrupt/normal/heavy) from model name."""
        ml = model.lower()
        if any(tag in ml for tag in ('1.5b', '1b', '0.5b')):
            return "interrupt"
        if any(tag in ml for tag in ('4b', '7b', '8b', '13b')):
            return "heavy"
        return "normal"  # 3b and unknown models

    def _build_options(self, max_tokens: int | None, temperature: float | None,
                       model: str | None = None) -> dict:
        """Build Ollama options using lane-specific inference profiles.

        Each model tier (1.5B/3B/4B) gets optimized parameters:
        - interrupt: minimize latency (small context, deterministic sampling)
        - normal: balance speed and capability (medium context, mirostat)
        - heavy: prioritize quality (larger context, broader sampling)
        """
        lane = self._detect_lane(model or self.config.get("model", "qwen2.5:1.5b"))
        profile = _LANE_PROFILES[lane].copy()

        # Priority 1: config overrides (legacy compatibility)
        for key in ("num_ctx", "num_thread", "top_k", "top_p", "temperature", "num_predict"):
            if key in self.config:
                profile[key] = self.config[key]
        # Also support 'max_tokens' config key (maps to num_predict)
        if "max_tokens" in self.config:
            profile["num_predict"] = self.config["max_tokens"]

        # Priority 2: explicit request parameters (highest)
        if max_tokens is not None:
            profile["num_predict"] = max_tokens
        if temperature is not None:
            profile["temperature"] = temperature

        # Disable mirostat if explicitly set to 0 in config
        if self.config.get("mirostat") == 0:
            profile["mirostat"] = 0

        return profile

    def prewarm(self, model: str | None = None) -> bool:
        """Preload a model into Ollama memory. Uses proxy bypass for localhost."""
        m = model or self.config.get("model", "qwen2.5:1.5b")
        try:
            data = json.dumps({"model": m, "keep_alive": self._keep_alive}).encode()
            resp = _local_post(
                f"{self.base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            ok = resp.status == 200
            if ok:
                self._loaded_models[m] = time.time()
                logger.info("Prewarmed model: %s", m)
            return ok
        except ConnectionRefusedError:
            logger.debug("Cannot prewarm %s — Ollama not running", m)
            return False
        except Exception:
            return False

    def get_loaded_models(self) -> list[dict]:
        """List models currently loaded in Ollama memory."""
        try:
            resp = _local_fetch(f"{self.base_url}/api/ps", timeout=5)
            data = json.loads(resp.read())
            return data.get("models", [])
        except Exception:
            return []

    def unload_model(self, model: str | None = None) -> bool:
        """Unload a model from Ollama memory."""
        m = model or self.config.get("model", "qwen2.5:1.5b")
        try:
            data = json.dumps({"model": m, "keep_alive": 0}).encode()
            resp = _local_post(
                f"{self.base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status == 200:
                self._loaded_models.pop(m, None)
            return resp.status == 200
        except Exception:
            return False

    def _warm(self) -> None:
        super()._warm()
        if self._prewarm_on_start and self._daemon_ok:
            import threading
            primary = self.config.get("model", "qwen2.5:3b")
            try:
                threading.Thread(target=self.prewarm, args=(primary,), daemon=True).start()
            except Exception:
                pass
            interrupt_model = "qwen2.5:1.5b"
            if interrupt_model != primary:
                try:
                    threading.Thread(target=self.prewarm, args=(interrupt_model,), daemon=True).start()
                except Exception:
                    pass

    def _get_client(self):
        if self._client is None:
            import ollama
            # Ensure NO_PROXY includes localhost for the httpx client
            # used internally by the ollama SDK
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

    def _limit_tools(self, tools: list | None, model: str) -> list | None:
        """Select best tools for the lane, ranked by relevance not position.

        Uses lane-specific tool rankings so the 1.5B interrupt gets only
        memory/status tools (not arbitrary first-N), while 3B/4B get
        tools ranked for coding/reasoning tasks.
        """
        if not tools:
            return tools
        lane = self._detect_lane(model)
        ranking = _TOOL_RANKINGS.get(lane, [])
        if not ranking:
            # Heavy lane or unknown: use all tools (with a sane cap)
            return tools[:20] if len(tools) > 20 else tools

        # Rank tools by lane priority: matching tools first, then others
        ranked = []
        tool_names = {t.get("function", {}).get("name", ""): t for t in tools}
        for name in ranking:
            if name in tool_names:
                ranked.append(tool_names.pop(name))
        # Append remaining tools (capped by lane limit)
        lane_limits = {"interrupt": 7, "normal": 15, "heavy": 25}
        limit = lane_limits.get(lane, 10)
        for t in tool_names.values():
            if len(ranked) >= limit:
                break
            ranked.append(t)
        return ranked

    async def _chat_once(self, client, model: str, full_messages: list,
                         tools: list | None, max_tokens, temperature) -> LLMResponse:
        """Single Ollama chat() call — factored out for fallback reuse."""
        kwargs = {}
        if tools:
            kwargs["tools"] = tools

        is_thinking = "qwen3" in model.lower()
        if is_thinking:
            kwargs["think"] = True

        start = time.time()
        response = await client.chat(
            model=model,
            messages=full_messages,
            options=self._build_options(max_tokens, temperature, model=model),
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
            # Connection refused = Ollama not running — give clear message
            if isinstance(primary_err, (ConnectionRefusedError, OSError)) or \
               "connection refused" in str(primary_err).lower() or \
               "connect" in type(primary_err).__name__.lower():
                msg = (f"Ollama is not running at {self.base_url}. "
                       f"Start it with: ollama serve")
                raise type(primary_err)(msg) from primary_err
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
            # Connection refused = Ollama not running — give clear message
            if isinstance(primary_err, (ConnectionRefusedError, OSError)) or \
               "connection refused" in str(primary_err).lower() or \
               "connect" in type(primary_err).__name__.lower():
                msg = (f"Ollama is not running at {self.base_url}. "
                       f"Start it with: ollama serve")
                raise type(primary_err)(msg) from primary_err
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
            options=self._build_options(max_tokens, temperature, model=model),
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
