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

    async def complete(self, messages, system_prompt=None, max_tokens=None,
                       temperature=None, tools=None, preferred_provider=None):
        return self._responses.pop(0)


def _resp(text="", *, tool_calls=None):
    return LLMResponse(
        text=text, model="fake-model", provider="fake",
        tokens_prompt=10, tokens_completion=5,
        tool_calls=tool_calls or [],
    )


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
    assert summary["status"] == "completed"
    assert summary["steps"][0]["status"] == "ok"
    assert summary["steps"][0]["duration_ms"] == 12.5
    assert summary["files_changed"] == ["a.txt"]
    assert summary["tokens_used"] == 15
    assert summary["iterations"] == 1
    assert summary["progress"] == 1.0
    assert isinstance(summary["duration_ms"], float)
    assert events_log == [
        "task.started", "step.started", "step.completed",
        "permission.observed", "task.finished",
    ]


def test_observer_progress_and_errors():
    obs = TaskObserver()
    obs.start("tc_y", "goal")
    s1 = obs.step_started("tool.a", {})
    obs.step_finished(s1, "ok", 1.0)
    s2 = obs.step_started("tool.b", {})
    obs.step_finished(s2, "error", 2.0, "boom")
    obs.finish(TaskStatus.FAILED, response="", iterations=2)

    summary = obs.summary()
    assert summary["status"] == "failed"
    assert summary["steps"][1]["status"] == "error"
    assert "boom" in summary["errors"]
    assert summary["progress"] == 1.0
    assert obs.is_finished


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
    loop = AgentLoop(
        router=FakeRouter([
            _resp(tool_calls=[
                ToolCall(name="filesystem.write", id="tc_t_00001",
                         arguments={"path": "temp/observer_test.txt", "content": "hello"}),
                ToolCall(name="filesystem.list", id="tc_t_00002",
                         arguments={"path": "."}),
            ]),
            _resp("All done."),
        ]),
        registry=build_default_registry(),
        project=ProjectContext(root_path=ROOT),
        decision_logger=StubLogger(),
        mode="agent",
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
        assert obs["steps"][0]["duration_ms"] > 0
        assert obs["tokens_used"] == 30
        assert obs["context_usage"]["total_tokens"] >= 0
        assert "compacted" in obs["context_usage"]
        assert target.exists()
        assert any(Path(f).name == "observer_test.txt" for f in obs["files_changed"])
    finally:
        target.unlink(missing_ok=True)


def test_loop_observation_on_max_iterations():
    loop = AgentLoop(
        router=FakeRouter([
            _resp(tool_calls=[ToolCall(name="filesystem.list", id="tc_t_00001",
                                       arguments={"path": "."})]),
            _resp(tool_calls=[ToolCall(name="filesystem.list", id="tc_t_00002",
                                       arguments={"path": "."})]),
        ]),
        registry=build_default_registry(),
        project=ProjectContext(root_path=ROOT),
        decision_logger=StubLogger(),
        mode="agent",
        max_iterations=1,
    )
    result = asyncio.run(loop.run("never ends"))
    assert not result.success
    assert "Max iterations" in result.error
    assert result.observation["status"] == "failed"
    assert result.observation["steps"][0]["tool"] == "filesystem.list"
