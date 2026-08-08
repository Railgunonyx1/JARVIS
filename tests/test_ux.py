"""Tests for Phase 4 UX: diff preview, state passthrough, LiveTaskDisplay,
and the JSON one-shot output path (no LLM, no real DBs)."""

import asyncio
import io
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agent.observer import TaskObserver, TaskStatus
from core.agent.state import AgentState
from core.project import ProjectContext
from providers.types import LLMResponse
from tools import build_default_registry
from tools.filesystem import _brief_diff, _diff_stats, filesystem_write

ROOT = Path(__file__).resolve().parents[1]


class StubLogger:
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


def _resp(text="ok."):
    return LLMResponse(
        text=text, model="fake-model", provider="fake",
        tokens_prompt=5, tokens_completion=5, tool_calls=[],
    )


# ── diff preview (filesystem_write) ─────────────────────────────────────────

def test_brief_diff_and_stats():
    assert _brief_diff("a\nb", "a\nb") == ""
    diff = _brief_diff("old line\nkeep", "new line\nkeep")
    assert "-old line" in diff
    assert "+new line" in diff
    stats = _diff_stats(diff)
    assert stats["added"] == 1
    assert stats["removed"] == 1


def test_filesystem_write_emits_diff_metadata():
    target = ROOT / "temp" / "ux_diff_test.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        first = filesystem_write({"path": str(target), "content": "hello\nworld\n"})
        assert first.success
        assert first.metadata["diff_stats"]["added"] >= 2

        same = filesystem_write({"path": str(target), "content": "hello\nworld\n"})
        assert same.success
        assert "diff" not in same.metadata

        changed = filesystem_write({"path": str(target), "content": "hello\nJARVIS MK-X\n"})
        assert changed.success
        assert "diff" in changed.metadata
        assert changed.metadata["diff_stats"]["added"] >= 1
    finally:
        target.unlink(missing_ok=True)


# ── AgentState tool passthrough ─────────────────────────────────────────────

def test_record_tool_stores_output_and_diff():
    state = AgentState(task_id="tc_x", goal="g")
    state.record_tool("filesystem.write", "tc_t_1", True, 3.2,
                      output="Wrote 5 chars", metadata={"diff": "+a\n-b", "diff_stats": {"added": 1, "removed": 1}})
    entry = state.tool_calls[0]
    assert entry["output"].startswith("Wrote")
    assert "+a" in entry["diff"]
    assert state.errors == []


# ── LiveTaskDisplay ─────────────────────────────────────────────────────────

def test_live_display_renders_events_without_polling():
    from cli.ux import LiveTaskDisplay
    from rich.console import Console

    out = io.StringIO()
    console = Console(file=out, width=100, force_terminal=False, color_system=None)
    obs = TaskObserver()
    display = LiveTaskDisplay(console=console, enable=True, transient=False)
    display.attach(obs)
    assert obs.on_event.__self__ is display
    display.start()
    obs.start("tc_u", "test goal")
    step = obs.step_started("filesystem.list", {})
    obs.step_finished(step, "ok", 5.0)
    obs.finish(TaskStatus.COMPLETED, response="done")
    display.stop()
    assert out.getvalue() != ""


def test_live_display_disabled_does_not_render():
    from cli.ux import LiveTaskDisplay
    from rich.console import Console

    out = io.StringIO()
    console = Console(file=out, width=100, force_terminal=False, color_system=None)
    obs = TaskObserver()
    display = LiveTaskDisplay(console=console, enable=False)
    display.attach(obs)
    display.start()
    obs.start("tc_v", "goal")
    obs.finish(TaskStatus.COMPLETED, response="done")
    display.stop()
    assert out.getvalue() == ""


# ── JSON one-shot output ────────────────────────────────────────────────────

def test_run_once_json_output(capsys):
    from cli.main import _run_once
    from core.agent.loop import AgentLoop

    loop = AgentLoop(
        router=FakeRouter([_resp()]),
        registry=build_default_registry(),
        project=ProjectContext(root_path=ROOT),
        decision_logger=StubLogger(),
        mode="agent",
    )
    asyncio.run(_run_once("say ok", loop, json_output=True))
    data = json.loads(capsys.readouterr().out)
    assert data["goal"] == "say ok"
    assert data["success"] is True
    assert "task_id" in data
    assert "tokens_used" in data


def test_run_once_empty_reply_is_failed_not_completed(tmp_path, monkeypatch):
    """An empty provider reply must fail (and record 'failed') instead of
    being reported as completed in decision memory with no response shown."""
    from core.agent.loop import AgentLoop
    from memory import vector_store as vs
    from memory.api import MemoryAPI
    from memory.decision_memory import DecisionMemory
    from memory.project_knowledge import ProjectKnowledge
    from memory.store import MemoryStore
    from memory.vector_store import VectorMemoryStore

    monkeypatch.setattr(vs, "_embed_ready", True)
    monkeypatch.setattr(vs, "_embed_model", None)
    mem = MemoryAPI(
        kv=MemoryStore(data_dir=tmp_path),
        vector=VectorMemoryStore(db_path=tmp_path / "vec.db"),
        decisions=DecisionMemory(data_dir=tmp_path),
        knowledge=ProjectKnowledge(data_dir=tmp_path),
    )
    try:
        loop = AgentLoop(
            router=FakeRouter([_resp("")]),
            registry=build_default_registry(),
            project=ProjectContext(root_path=ROOT),
            decision_logger=StubLogger(),
            mode="agent",
            mem=mem,
        )
        result = asyncio.run(loop.run("say hello"))
        assert result.success is False
        assert "empty response" in result.error
        decisions = mem.recall_decisions()
        assert any(d["decision"] == "failed" for d in decisions)
        assert any(d["goal"] == "say hello" for d in decisions)
    finally:
        mem.close()


# ── collapsed summary + expanded details ────────────────────────────────────

def _make_result(tool_calls=None, usage=None):
    from core.agent.loop import AgentResult
    state = AgentState(task_id="tr_x", goal="audit the repo",
                       tool_calls=tool_calls or [])
    obs = {
        "status": "completed",
        "steps": [{"tool": "filesystem_write", "status": "ok", "duration_ms": 5.0}],
        "duration_ms": 12.0,
        "tokens_used": 30,
        "context_usage": usage or {},
    }
    return AgentResult(success=True, response="done", trace_id="tr_x",
                       state=state, observation=obs)


def test_render_summary_collapsed():
    from cli.details import render_summary
    text = render_summary(_make_result())
    assert "audit the repo" in text
    assert "filesystem_write" in text
    assert "12ms" in text


def test_render_expanded_sections():
    from cli.details import render_expanded
    from rich.console import Console

    usage = {
        "system_tokens": 100, "memory_tokens": 50, "files_tokens": 30,
        "messages_tokens": 80, "total_tokens": 260, "total_budget": 1000,
        "compacted": True,
    }
    calls = [{"name": "filesystem_write", "success": True, "duration_ms": 5.0,
              "output": "Wrote 5 chars", "args": {"path": "core/x.py"}}]
    out = io.StringIO()
    Console(file=out, width=100, force_terminal=False,
            color_system=None).print(render_expanded(_make_result(calls, usage)))
    text = out.getvalue()
    assert "Repository Audit" in text
    assert "Tokens" in text and "Execution" in text
    assert "core/x.py" in text
    assert "compacted" in text.lower() or "compressed" in text.lower()


def test_render_expanded_empty_state_no_crash():
    from cli.details import render_expanded
    from rich.console import Console

    out = io.StringIO()
    Console(file=out, width=100, force_terminal=False,
            color_system=None).print(render_expanded(_make_result()))
    assert "audit the repo" in out.getvalue()


# ── status bar + notifications ──────────────────────────────────────────────

def test_render_status_bar_and_notifications():
    import types
    from rich.console import Console
    from cli.cockpit import render_notifications, render_status_bar

    loop = types.SimpleNamespace(
        permissions=types.SimpleNamespace(mode="agent"),
        router=types.SimpleNamespace(_last_provider="ollama", _last_model="qwen3"),
        registry=types.SimpleNamespace(list=lambda: [1, 2, 3]),
        mem=types.SimpleNamespace(get_stats=lambda: {"decisions": 2, "knowledge": 0}),
        context_manager=types.SimpleNamespace(last_report=None),
    )
    bar = render_status_bar(loop)
    assert "mode=agent" in str(bar)
    assert "qwen3/ollama" in str(bar)
    assert "tools=3" in str(bar)

    out = io.StringIO()
    Console(file=out, width=100, force_terminal=False,
            color_system=None).print(render_notifications(
                [("ok", "task done"), ("warn", "denied")]))
    text = out.getvalue()
    assert "task done" in text and "denied" in text
