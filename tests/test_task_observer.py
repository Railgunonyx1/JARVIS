"""Tests for TaskObserver and its AgentLoop integration (no LLM, no real DBs)."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agent.loop import AgentLoop
from core.agent.observer import TaskObserver, TaskStatus
from core.project import ProjectContext
from providers.types import LLMResponse, ToolCall
from tools import build_default_registry

ROOT = Path(__file__).resolve().parents[1]


class StubLogger:
    """No-op logger so tests never touch the real events/audit DBs."""

    def __init__(self):
        self.records = []

    def begin_task(self, request, source=""):
        return "test_trace"

    def record(self, trace_id, name, data=None, **extra):
        self.records.append((name, data))

    def record_tool(self, *args, **kwargs):
        pass

    def flush(self):
        pass


class FakeRouter:
    def __init__(self, responses):
        self._responses = list(responses)

    async def complete(self, messages, **kw):
        return self._responses.pop(0)

    async def complete_stream_typed(self, messages, **kwargs):
        r = await self.complete(messages, **kwargs)
        yield r.text, r.tool_calls


def _resp(text="", *, tool_calls=None):
    return LLMResponse(
        text=text, model="fake-model", provider="fake",
        latency_ms=10, tokens_used=10,
        tokens_prompt=10, tokens_completion=5,
        tool_calls=tool_calls or [],
    )


def _make_loop(router, **kwargs):
    """Create an AgentLoop with verification disabled for testing."""
    loop = AgentLoop(
        router=router,
        registry=build_default_registry(),
        project=ProjectContext(root_path=ROOT),
        decision_logger=StubLogger(),
        mode="agent",
        **kwargs,
    )
    loop._verification_enabled = False
    return loop


# ── Unit: TaskObserver ───────────────────────────────────────────────────

def test_observer_timeline_lifecycle():
    events_log = []
    obs = TaskObserver(on_event=lambda name, payload: events_log.append(name))
    obs.start("tc_x", "Do something")
    step = obs.step_started("filesystem.list", {"path": "."})
    assert step.status == "running"
    obs.step_finished(step, "ok", 12.5)
    obs.observe_permission("filesystem.list", True)
    obs.finish(TaskStatus.COMPLETED, response="done", provider="p", model="m",
               tokens=15, iterations=1, files_changed=["a.txt"])

    summary = obs.summary()
    assert summary["task_id"] == "tc_x"


def test_observer_cancel():
    obs = TaskObserver()
    obs.start("tc_z", "goal")
    assert not obs.is_finished
    obs.cancel()
    assert obs.is_finished
    assert obs.summary()["status"] == "cancelled"


def test_observer_requires_start():
    obs = TaskObserver()
    with pytest.raises(RuntimeError):
        obs.step_started("tool.a", {})


# ── Integration: AgentLoop produces a complete observation ───────────────

def test_loop_populates_observation():
    loop = _make_loop(
        FakeRouter([
            _resp(tool_calls=[
                ToolCall(name="filesystem.write", id="tc_t_00001",
                         arguments={"path": "temp/observer_test.txt", "content": "hello"}),
                ToolCall(name="filesystem.list", id="tc_t_00002",
                         arguments={"path": "."}),
            ]),
            _resp("All done."),
        ]),
        max_iterations=5,
    )
    target = ROOT / "temp" / "observer_test.txt"
    try:
        result = asyncio.run(loop.run("write a file then list the root"))
        assert result.success
        obs = result.observation
        assert obs["status"] == "completed"
        assert obs["iterations"] == 2
        tools = [s["tool"] for s in obs["steps"]]
        assert tools == ["filesystem.write", "filesystem.list"]
        assert all(s["status"] == "ok" for s in obs["steps"])
        assert obs["steps"][0]["duration_ms"] >= 0
        assert obs["tokens_used"] == 30
        assert obs["context_usage"]["total_tokens"] >= 0
        assert "compacted" in obs["context_usage"]
        assert target.exists()
        assert any(Path(f).name == "observer_test.txt" for f in obs["files_changed"])
    finally:
        target.unlink(missing_ok=True)


def test_loop_observation_on_max_iterations():
    loop = _make_loop(
        FakeRouter([
            _resp(tool_calls=[ToolCall(name="filesystem.list", id="tc_t_00001",
                                       arguments={"path": "."})]),
            _resp(tool_calls=[ToolCall(name="filesystem.list", id="tc_t_00002",
                                       arguments={"path": "."})]),
        ]),
        max_iterations=1,
    )
    result = asyncio.run(loop.run("never ends"))
    assert not result.success
    assert "Max iterations" in result.error
    assert result.observation["status"] == "failed"
    assert result.observation["steps"][0]["tool"] == "filesystem.list"
