"""Ollama provider integration tests — daemon probing, tool schemas, fallback, streaming."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from providers.ollama_provider import OllamaProvider
from providers.types import classify_provider_error, parse_ollama_tool_calls

# ── Helpers ──────────────────────────────────────────────────────────────

def _make_provider(model="qwen2.5:1.5b", fallback_model=None, daemon_ok=True):
    config = {"model": model, "base_url": "http://127.0.0.1:11434"}
    if fallback_model:
        config["fallback"] = {"model": fallback_model}
    with patch.object(OllamaProvider, "_check_package"):
        p = OllamaProvider(config)
    p._package_ok = True
    p._daemon_ok = daemon_ok
    p._last_probe_time = time.time()
    return p


def _fake_response(text="ok", model="qwen2.5:1.5b", tool_calls=None):
    return {
        "message": {"content": text, "tool_calls": tool_calls or []},
        "prompt_eval_count": 10,
        "eval_count": 5,
    }


def _fake_stream_chunk(text=None, tool_calls=None):
    msg = {}
    if text is not None:
        msg["content"] = text
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {"message": msg}


def _tool_schema(name, params=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Tool {name}",
            "parameters": params or {"type": "object", "properties": {}},
        },
    }


# ── Daemon probing ───────────────────────────────────────────────────────

class TestDaemonProbing:
    def test_initial_probe_on_init(self):
        with patch.object(OllamaProvider, "_check_package"):
            p = OllamaProvider({"model": "qwen2.5:1.5b"})
        assert p._daemon_ok is False
        assert p._last_probe_time == 0.0

    def test_probe_daemon_success(self):
        p = _make_provider(daemon_ok=True)
        assert p._daemon_ok is True
        assert p._last_probe_time > 0

    def test_probe_daemon_failure(self):
        p = _make_provider(daemon_ok=False)
        assert p._daemon_ok is False

    def test_is_available_requires_daemon(self):
        p = _make_provider(daemon_ok=False)
        assert p.is_available is False

    def test_refreshable_probe_within_interval(self):
        p = _make_provider(daemon_ok=True)
        p._daemon_ok = False
        p._last_probe_time = time.time()
        assert p.is_available is False

    def test_refreshable_probe_after_interval(self):
        p = _make_provider(daemon_ok=True)
        p._daemon_ok = False
        p._last_probe_time = time.time() - 60
        assert p._probe_interval < 60
        result = p._ensure_daemon()
        assert isinstance(result, bool)


# ── Tool limiting ────────────────────────────────────────────────────────

class TestToolLimiting:
    def test_1_5b_gets_5_tools(self):
        p = _make_provider(model="qwen2.5:1.5b")
        tools = [_tool_schema(f"t{i}") for i in range(10)]
        result = p._limit_tools(tools, "qwen2.5:1.5b")
        assert len(result) == 5

    def test_3b_gets_10_tools(self):
        p = _make_provider(model="qwen2.5:3b")
        tools = [_tool_schema(f"t{i}") for i in range(15)]
        result = p._limit_tools(tools, "qwen2.5:3b")
        assert len(result) == 10

    def test_large_model_gets_20_tools(self):
        p = _make_provider(model="qwen2.5:7b")
        tools = [_tool_schema(f"t{i}") for i in range(25)]
        result = p._limit_tools(tools, "qwen2.5:7b")
        assert len(result) == 20

    def test_no_limit_when_under(self):
        p = _make_provider()
        tools = [_tool_schema(f"t{i}") for i in range(3)]
        result = p._limit_tools(tools, "qwen2.5:1.5b")
        assert len(result) == 3

    def test_none_tools_passthrough(self):
        p = _make_provider()
        assert p._limit_tools(None, "qwen2.5:1.5b") is None

    def test_fallback_model_gets_own_limit(self):
        p = _make_provider(model="qwen2.5:3b", fallback_model="qwen2.5:1.5b")
        tools = [_tool_schema(f"t{i}") for i in range(12)]
        primary = p._limit_tools(tools, "qwen2.5:3b")
        fallback = p._limit_tools(tools, "qwen2.5:1.5b")
        assert len(primary) == 10
        assert len(fallback) == 5


# ── Message conversion ───────────────────────────────────────────────────

class TestMessageConversion:
    def test_tool_call_arguments_from_string(self):
        p = _make_provider()
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": "test", "arguments": '{"a": 1}'}}
                ],
            }
        ]
        result = p._convert_messages(messages)
        assert result[0]["tool_calls"][0]["function"]["arguments"] == {"a": 1}

    def test_tool_call_arguments_from_dict(self):
        p = _make_provider()
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": "test", "arguments": {"a": 1}}}
                ],
            }
        ]
        result = p._convert_messages(messages)
        assert result[0]["tool_calls"][0]["function"]["arguments"] == {"a": 1}

    def test_tool_call_arguments_invalid_json_falls_back_to_empty(self):
        p = _make_provider()
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": "test", "arguments": "hello"}}
                ],
            }
        ]
        result = p._convert_messages(messages)
        assert result[0]["tool_calls"][0]["function"]["arguments"] == {}

    def test_tool_call_arguments_json_string_non_dict_wrapped(self):
        p = _make_provider()
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": "test", "arguments": '"hello"'}}
                ],
            }
        ]
        result = p._convert_messages(messages)
        assert result[0]["tool_calls"][0]["function"]["arguments"] == {"value": "hello"}

    def test_system_prompt_added(self):
        p = _make_provider()
        result = p._convert_messages([{"role": "user", "content": "hi"}], "Be helpful")
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"

    def test_non_assistant_messages_passthrough(self):
        p = _make_provider()
        messages = [{"role": "user", "content": "hello"}]
        result = p._convert_messages(messages)
        assert result == messages


# ── Tool-call parsing ────────────────────────────────────────────────────

class TestToolCallParsing:
    def test_single_tool_call(self):
        message = {
            "tool_calls": [
                {"function": {"name": "shell.execute", "arguments": {"cmd": "ls"}}}
            ]
        }
        calls = parse_ollama_tool_calls(message)
        assert len(calls) == 1
        assert calls[0].name == "shell.execute"
        assert calls[0].id == "ollama_0"

    def test_multiple_tool_calls_unique_ids(self):
        message = {
            "tool_calls": [
                {"function": {"name": "a", "arguments": {}}},
                {"function": {"name": "b", "arguments": {}}},
                {"function": {"name": "c", "arguments": {}}},
            ]
        }
        calls = parse_ollama_tool_calls(message)
        assert [c.id for c in calls] == ["ollama_0", "ollama_1", "ollama_2"]

    def test_empty_tool_calls(self):
        calls = parse_ollama_tool_calls({"tool_calls": []})
        assert calls == []

    def test_no_tool_calls_key(self):
        calls = parse_ollama_tool_calls({"content": "hi"})
        assert calls == []

    def test_arguments_as_string(self):
        message = {
            "tool_calls": [
                {"function": {"name": "test", "arguments": '{"x": 1}'}}
            ]
        }
        calls = parse_ollama_tool_calls(message)
        assert calls[0].arguments == {"x": 1}


# ── captures_stream_tool_calls ───────────────────────────────────────────

class TestCapturesStreamToolCalls:
    def test_ollama_declares_capture(self):
        assert OllamaProvider.captures_stream_tool_calls is True

    def test_instance_has_flag(self):
        p = _make_provider()
        assert p.captures_stream_tool_calls is True


# ── Fallback model inheritance ───────────────────────────────────────────

class TestFallbackModelInheritance:
    def test_fallback_read_from_config(self):
        p = _make_provider(model="qwen2.5:3b", fallback_model="qwen2.5:1.5b")
        assert p._fallback_model == "qwen2.5:1.5b"

    def test_no_fallback(self):
        p = _make_provider(model="qwen2.5:3b")
        assert p._fallback_model is None

    @pytest.mark.asyncio
    async def test_fallback_called_on_primary_failure(self):
        p = _make_provider(model="qwen2.5:3b", fallback_model="qwen2.5:1.5b")
        mock_client = AsyncMock()
        call_models = []

        async def fake_chat(model, messages, options, **kwargs):
            call_models.append(model)
            if model == "qwen2.5:3b":
                raise RuntimeError("model not found")
            return _fake_response(text="fallback ok", model=model)

        mock_client.chat = fake_chat
        p._client = mock_client
        result = await p.complete([{"role": "user", "content": "hi"}])
        assert result.text == "fallback ok"
        assert call_models == ["qwen2.5:3b", "qwen2.5:1.5b"]

    @pytest.mark.asyncio
    async def test_primary_success_skips_fallback(self):
        p = _make_provider(model="qwen2.5:3b", fallback_model="qwen2.5:1.5b")
        mock_client = AsyncMock()
        call_models = []

        async def fake_chat(model, messages, options, **kwargs):
            call_models.append(model)
            return _fake_response(text="primary ok", model=model)

        mock_client.chat = fake_chat
        p._client = mock_client
        result = await p.complete([{"role": "user", "content": "hi"}])
        assert result.text == "primary ok"
        assert call_models == ["qwen2.5:3b"]

    @pytest.mark.asyncio
    async def test_fallback_tool_limit_differs_from_primary(self):
        p = _make_provider(model="qwen2.5:3b", fallback_model="qwen2.5:1.5b")
        mock_client = AsyncMock()
        tool_counts = []

        async def fake_chat(model, messages, options, tools=None, **kwargs):
            tool_counts.append(len(tools) if tools else 0)
            if model == "qwen2.5:3b":
                raise RuntimeError("fail")
            return _fake_response(text="ok", model=model)

        mock_client.chat = fake_chat
        p._client = mock_client
        tools = [_tool_schema(f"t{i}") for i in range(12)]
        await p.complete([{"role": "user", "content": "hi"}], tools=tools)
        assert tool_counts == [10, 5]


# ── Streaming fallback ───────────────────────────────────────────────────

class TestStreamingFallback:
    @pytest.mark.asyncio
    async def test_streaming_fallback_on_primary_failure(self):
        p = _make_provider(model="qwen2.5:3b", fallback_model="qwen2.5:1.5b")
        mock_client = AsyncMock()
        call_models = []

        async def fake_chat(model, messages, options, stream=False, **kwargs):
            call_models.append(model)
            if model == "qwen2.5:3b":
                raise RuntimeError("model not found")

            async def gen():
                yield _fake_stream_chunk(text="fallback stream")
            return gen()

        mock_client.chat = fake_chat
        p._client = mock_client
        chunks = []
        async for chunk in p.complete_stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)
        assert chunks == ["fallback stream"]
        assert call_models == ["qwen2.5:3b", "qwen2.5:1.5b"]

    @pytest.mark.asyncio
    async def test_streaming_primary_success_skips_fallback(self):
        p = _make_provider(model="qwen2.5:3b", fallback_model="qwen2.5:1.5b")
        mock_client = AsyncMock()
        call_models = []

        async def fake_chat(model, messages, options, stream=False, **kwargs):
            call_models.append(model)

            async def gen():
                yield _fake_stream_chunk(text="primary stream")
            return gen()

        mock_client.chat = fake_chat
        p._client = mock_client
        chunks = []
        async for chunk in p.complete_stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)
        assert chunks == ["primary stream"]
        assert call_models == ["qwen2.5:3b"]

    @pytest.mark.asyncio
    async def test_streaming_tool_calls_accumulated(self):
        p = _make_provider(model="qwen2.5:3b", fallback_model="qwen2.5:1.5b")
        mock_client = AsyncMock()
        tc = [{"function": {"name": "shell.execute", "arguments": {"cmd": "ls"}}}]

        async def fake_chat(model, messages, options, stream=False, **kwargs):
            async def gen():
                yield _fake_stream_chunk(text="thinking")
                yield _fake_stream_chunk(tool_calls=tc)
                yield _fake_stream_chunk(text="done")
            return gen()

        mock_client.chat = fake_chat
        p._client = mock_client
        chunks = []
        async for chunk in p.complete_stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)
        assert chunks == ["thinking", "done"]
        results = p._stream_tool_call_results()
        assert len(results) == 1
        assert results[0].name == "shell.execute"


# ── Temperature / max_tokens edge cases ──────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_temperature_zero_not_overridden(self):
        p = _make_provider()
        mock_client = AsyncMock()

        async def fake_chat(model, messages, options, **kwargs):
            assert options["temperature"] == 0
            return _fake_response()

        mock_client.chat = fake_chat
        p._client = mock_client
        await p.complete([{"role": "user", "content": "hi"}], temperature=0)

    @pytest.mark.asyncio
    async def test_max_tokens_zero_not_overridden(self):
        p = _make_provider()
        mock_client = AsyncMock()

        async def fake_chat(model, messages, options, **kwargs):
            assert options["num_predict"] == 0
            return _fake_response()

        mock_client.chat = fake_chat
        p._client = mock_client
        await p.complete([{"role": "user", "content": "hi"}], max_tokens=0)

    @pytest.mark.asyncio
    async def test_none_uses_config_defaults(self):
        p = _make_provider()
        p.config["temperature"] = 0.3
        p.config["max_tokens"] = 100
        mock_client = AsyncMock()

        async def fake_chat(model, messages, options, **kwargs):
            assert options["temperature"] == 0.3
            assert options["num_predict"] == 100
            return _fake_response()

        mock_client.chat = fake_chat
        p._client = mock_client
        await p.complete([{"role": "user", "content": "hi"}])


# ── Error classification ─────────────────────────────────────────────────

class TestErrorClassification:
    def test_rate_limit_error_detected(self):
        kind = classify_provider_error("rate limit exceeded")
        from providers.types import ErrorKind
        assert kind == ErrorKind.RATE_LIMIT

    def test_connection_error_classified(self):
        kind = classify_provider_error("Connection refused")
        from providers.types import ErrorKind
        assert kind == ErrorKind.NETWORK

    def test_timeout_error_classified(self):
        kind = classify_provider_error("request timed out")
        from providers.types import ErrorKind
        assert kind == ErrorKind.TIMEOUT


# ── _stream_tool_call_results ────────────────────────────────────────────

class TestStreamToolCallResults:
    def test_empty_accumulator(self):
        p = _make_provider()
        p._stream_tool_calls = {}
        assert p._stream_tool_call_results() == []

    def test_multiple_calls_sorted(self):
        p = _make_provider()
        p._stream_tool_calls = {
            1: {"id": "ollama_1", "name": "b", "args": ['{"y": 2}']},
            0: {"id": "ollama_0", "name": "a", "args": ['{"x": 1}']},
        }
        results = p._stream_tool_call_results()
        assert [r.name for r in results] == ["a", "b"]

    def test_invalid_json_falls_back_to_empty(self):
        p = _make_provider()
        p._stream_tool_calls = {
            0: {"id": "ollama_0", "name": "test", "args": ["not-json"]},
        }
        results = p._stream_tool_call_results()
        assert results[0].arguments == {}

    def test_empty_name_skipped(self):
        p = _make_provider()
        p._stream_tool_calls = {
            0: {"id": "ollama_0", "name": "", "args": []},
        }
        assert p._stream_tool_call_results() == []
