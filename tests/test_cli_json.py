"""Phase 8 — ``--json`` byte-clean output and streaming wiring (cli.main)."""

from __future__ import annotations

import asyncio
import io
import json
from contextlib import redirect_stdout

from cli.main import _run_once


class StubState:
    provider = "stub"
    model = "stub/1"
    iteration = 1
    tokens_used = 42
    tokens_prompt = 10
    tokens_completion = 32
    tool_calls = []

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "iteration": self.iteration,
            "tokens_used": self.tokens_used,
        }


class StubResult:
    success = True
    response = "hello"
    trace_id = "trace-1"
    error = ""
    observation = {}
    perf = {}
    state = StubState()

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "response": self.response,
            "trace_id": self.trace_id,
            "error": self.error,
            "state": self.state.to_dict(),
            "observation": self.observation,
            "perf": self.perf,
        }


class StubObserver:
    on_event = None

    def summary(self) -> dict:
        return {"status": "ok", "steps": []}


class StubRouter:
    _last_model = "stub/1"
    _last_provider = "stub"


class StubLogger:
    def flush(self):
        pass


class StubLoop:
    def __init__(self, result=None):
        self.result = result or StubResult()
        self._last_goal = None
        self._last_result = None
        self.observer = StubObserver()
        self.router = StubRouter()
        self.permissions = type("P", (), {"mode": "agent"})()
        self.mem = None
        self.logger = StubLogger()
        self.received_on_chunk = None

    async def run(self, goal, session_id="", on_chunk=None):
        self.received_on_chunk = on_chunk
        if on_chunk is not None:
            await on_chunk("hel")
            await on_chunk("lo")
        return self.result


def test_json_output_is_pure_and_parses():
    out = io.StringIO()
    with redirect_stdout(out):
        asyncio.run(_run_once("hi", StubLoop(), json_output=True))

    text = out.getvalue()
    assert text.startswith("{") and text.rstrip().endswith("}")
    data = json.loads(text)
    assert data["goal"] == "hi"
    assert data["success"] is True
    assert data["response"] == "hello"
    assert data["trace_id"] == "trace-1"
    assert data["provider"] == "stub"
    assert data["model"] == "stub/1"


def test_json_survives_streaming_through_bridge():
    """With a bridge attached, on_chunk is wired and json stays clean."""
    from cli.bridge import AgentBridge

    loop = StubLoop()
    bridge = AgentBridge()
    bridge.attach_loop(loop)

    out = io.StringIO()
    with redirect_stdout(out):
        asyncio.run(_run_once("hi", loop, json_output=True, bridge=bridge))

    assert loop.received_on_chunk is not None
    assert bridge.state.messages[-1].content == "hello"
    data = json.loads(out.getvalue())
    assert data["response"] == "hello"


def test_streaming_populates_bridge_message():
    from cli.bridge import AgentBridge

    loop = StubLoop()
    bridge = AgentBridge()
    bridge.attach_loop(loop)

    async def go():
        await _run_once("hi", loop, bridge=bridge)

    asyncio.run(go())
    # streamed chunks accumulate into one agent message, finish_run
    # does not duplicate it
    agents = [m for m in bridge.state.messages if m.role == "agent"]
    assert len(agents) == 1
    assert agents[0].content == "hello"


def test_non_json_fallback_keeps_plain_output():
    loop = StubLoop()
    out = io.StringIO()
    with redirect_stdout(out):
        asyncio.run(_run_once("hi", loop))
    assert "hello" in out.getvalue()
    assert loop.received_on_chunk is None
