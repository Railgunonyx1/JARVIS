"""G7 — kernel integration: bridge engine seam, budgets, browser state,
cross-agent tab ownership. All hermetic (fake streamer / no providers)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import sys

BRIDGE_DIR = Path(__file__).resolve().parent.parent / "jbrowser-bridge"
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

from server import serve  # noqa: E402
from backend import KernelBackend  # noqa: E402
from engine import Budget, ModelGatewayEngine, trim_messages  # noqa: E402
from core.agent.state import TaskStatus  # noqa: E402
from core.locks import ResourceLockedError  # noqa: E402
from orbit.registry import TargetRegistry  # noqa: E402


class TestBudgetTrim:
    def test_keeps_system_head_and_recent_tail(self):
        msgs = [{"role": "system", "content": "policy"},
                {"role": "user", "content": "1"}, {"role": "assistant", "content": "2"},
                {"role": "user", "content": "3"}, {"role": "assistant", "content": "4"}]
        out = trim_messages(msgs, Budget(max_messages=3))
        roles = [m["role"] for m in out]
        assert roles == ["system", "user", "assistant"]
        assert out[-1]["content"] == "4"

    def test_token_cap_drops_oldest_non_system(self):
        big = "x" * 20000
        msgs = [{"role": "system", "content": "mandatory"},
                {"role": "user", "content": big},
                {"role": "assistant", "content": big},
                {"role": "user", "content": "final"}]
        out = trim_messages(msgs, Budget(max_input_tokens=1000))
        assert out[0]["role"] == "system"
        assert out[-1]["content"] == "final"
        assert len(out) < len(msgs)

    def test_empty_input(self):
        assert trim_messages([], Budget()) == []
        assert trim_messages(None, Budget()) == []


class TestModelGatewayEngine:
    def _engine(self, tokens=("hello ", "world"), budget=None, fail=False):
        async def fake_streamer(messages, system_prompt, max_tokens):
            if fail:
                raise RuntimeError("provider exploded")
            # Echo the page context we handed it, proving prompt assembly.
            for m in messages:
                if m.get("role") == "system" and "Page title" in m.get("content", ""):
                    yield m["content"] + "|"
            for t in tokens:
                yield t
        return ModelGatewayEngine(streamer=fake_streamer, budget=budget or Budget())

    def test_streams_start_delta_done(self):
        engine = self._engine(tokens=("ab", "cd"))
        seen = []

        def emit(e):
            seen.append(e)

        text = engine.stream_chat("s1", [{"role": "user", "content": "hi"}],
                                  {"title": "Orbit", "url": "http://127.0.0.1/x"},
                                  emit)
        kinds = [e["type"] for e in seen]
        assert kinds[0] == "start" and kinds[-1] == "done"
        assert kinds.count("delta") == 3  # page context + 2 tokens
        assert text.endswith("abcd")
        assert "Page title: Orbit" in text

    def test_output_budget_caps_stream(self):
        engine = self._engine(tokens=("a" * 2000, "b" * 2000),
                              budget=Budget(max_output_chars=2500))
        seen = []
        text = engine.stream_chat("s2", [{"role": "user", "content": "go"}],
                                  None, seen.append)
        assert len(text) == 2500
        assert seen[-1]["type"] == "done"

    def test_failure_emits_error_not_crash(self):
        engine = self._engine(fail=True)
        seen = []

        def emit(e):
            seen.append(e)

        text = engine.stream_chat("s3", [{"role": "user", "content": "x"}], None, emit)
        assert text == ""
        assert seen[-1]["type"] == "error"
        assert seen[-1]["code"] == "engine_error"

    def test_input_window_is_trimmed_before_stream(self):
        dropped = {"role": "user", "content": "drop-me"}
        called = {}

        async def fake(messages, system_prompt, max_tokens):
            called["prompt"] = messages
            yield "ok"

        engine = ModelGatewayEngine(streamer=fake, budget=Budget(max_messages=2))
        engine.stream_chat("s4",
                           [dropped, {"role": "user", "content": "keep-1"},
                            {"role": "user", "content": "keep-2"}],
                           None, lambda e: None)
        assert all(m["content"] != "drop-me" for m in called["prompt"])
        assert [m["content"] for m in called["prompt"]] == ["keep-1", "keep-2"]


class TestKernelBackendWiring:
    def test_no_engine_emits_not_attached(self):
        events, text = [], []
        KernelBackend(engine=None).stream_chat(
            "s", [{"role": "user", "content": "hi"}], None,
            lambda e: events.append(e) or text.append(e.get("text", "")),
        )
        assert events[-1]["type"] == "done"
        assert "not attached" in "".join(text)

    def test_with_engine_delegates(self):
        class FakeEngine:
            name = "fake"
            def stream_chat(self, sid, msgs, page, emit):
                emit({"type": "start", "session_id": sid})
                emit({"type": "delta", "text": "kernel reply"})
                emit({"type": "done", "id": sid})
                return "kernel reply"

        backend = KernelBackend(engine=FakeEngine())
        events = []
        backend.stream_chat("s", [], None, lambda e: events.append(e))
        assert [e["type"] for e in events] == ["start", "delta", "done"]
        assert backend.status()["kernel"] == "online"
        assert backend.status()["engine"] == "fake"

    def test_engine_run_failure_emits_backend_error_and_closes(self):
        class BoomEngine:
            name = "boom"
            def stream_chat(self, sid, msgs, page, emit):
                emit({"type": "start", "session_id": sid})
                raise RuntimeError("engine died")

        httpd = serve(port=0, backend_kind="kernel", engine=BoomEngine())
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            import urllib.request
            req = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_address[1]}/v1/chat",
                data=b'{"session_id":"s","messages":[{"role":"user","content":"hi"}]}',
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                events = _read_sse(resp)
            assert resp.status == 200
            assert events[-1]["type"] == "error"
            assert events[-1]["code"] == "backend_error"
        finally:
            httpd.shutdown()
            httpd.server_close()


class TestWaitingBrowserState:
    def test_enum_roundtrips(self):
        assert TaskStatus.WAITING_BROWSER == "waiting_browser"
        assert str(TaskStatus.WAITING_BROWSER) == "waiting_browser"

    def test_transitions_park_and_resume(self):
        from core.agent.state import AgentState
        st = AgentState(task_id="t", goal="g")
        st.transition(TaskStatus.PLANNING)
        st.transition(TaskStatus.EXECUTING)
        st.transition(TaskStatus.WAITING_BROWSER)
        assert st.status == TaskStatus.WAITING_BROWSER
        st.transition(TaskStatus.EXECUTING)
        assert st.status == TaskStatus.EXECUTING


class TestCrossAgentTabOwnership:
    def test_contest_yields_resource_locked(self):
        reg = TargetRegistry()
        tab = reg.register("http://127.0.0.1/a", session_id="s", owner="AGENT:research-1")
        with pytest.raises(ResourceLockedError) as exc:
            reg.own(tab.tab_id, "AGENT:main")
        assert exc.value.code == "RESOURCE_LOCKED"
        assert exc.value.key == tab.tab_id
        assert exc.value.owner == "AGENT:research-1"

    def test_owner_reacquires_and_releases_for_next_agent(self):
        reg = TargetRegistry()
        tab = reg.register("http://127.0.0.1/b", session_id="s", owner="AGENT:main")
        reg.own(tab.tab_id, "AGENT:main")  # reentrant for same owner
        reg.release(tab.tab_id, "AGENT:main")
        reg.own(tab.tab_id, "AGENT:research-1")  # now free
        assert reg.owner_of(tab.tab_id) == "AGENT:research-1"

    def test_user_holds_agent_out(self):
        reg = TargetRegistry()
        tab = reg.register("http://127.0.0.1/c", session_id="s", owner="USER")
        with pytest.raises(ResourceLockedError):
            reg.own(tab.tab_id, "AGENT:main")


def _read_sse(resp):
    body = resp.read().decode("utf-8")
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    assert events, "no SSE events received"
    return events


class TestBridgeChatWithKernelEngine:
    def test_v1_chat_streams_from_engine(self):
        class FakeEngine:
            name = "fake"
            def stream_chat(self, sid, msgs, page, emit):
                emit({"type": "start", "session_id": sid, "backend": self.name})
                emit({"type": "delta", "text": "hello kernel"})
                emit({"type": "done", "id": sid})
                return "hello kernel"

        httpd = serve(port=0, backend_kind="kernel", engine=FakeEngine())
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            import urllib.request
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/chat",
                data=b'{"session_id":"s","messages":[{"role":"user","content":"hi"}]}',
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                events = _read_sse(resp)
            assert resp.status == 200
            assert [e["type"] for e in events] == ["start", "delta", "done"]
            assert events[1]["text"] == "hello kernel"
            assert events[0]["backend"] == "fake"
        finally:
            httpd.shutdown()
            httpd.server_close()