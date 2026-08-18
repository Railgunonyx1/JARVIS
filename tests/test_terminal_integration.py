"""Sprint 14 -- Integration tests for the terminal domain pipeline.

Tests the full flow: Event Bus -> Terminal Store -> Renderer.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from jarvis.terminal.breakpoints import Breakpoint, classify_width, panels_for_breakpoint, should_show
from jarvis.terminal.events import EventType, TerminalEvent, make_terminal_event
from jarvis.terminal.intents import (
    IntentType,
    intent_cancel,
    intent_set_layout,
    intent_submit,
)
from jarvis.terminal.keymap import KeyBinding, Keymap
from jarvis.terminal.persistence import SessionPersistence, _serialize_state, _deserialize_state
from jarvis.terminal.renderer import TerminalRenderer
from jarvis.terminal.reducers import reduce
from jarvis.terminal.store import TerminalStore
from jarvis.terminal.task_queue import CancellationToken, TaskQueue, TaskState
from jarvis.terminal.types import (
    LayoutMode,
    Message,
    Plan,
    PlanStep,
    SessionState,
    SessionStatus,
    StepStatus,
)
from runtime.event_bus import BusEvent, EventBus, get_event_bus
from runtime.event_bus_bridge import EventBusBridge


# ── Reducer integration tests ───────────────────────────────────────────


class TestReducerPipeline:
    def test_full_event_sequence(self):
        state = SessionState()
        store = TerminalStore(state)
        events = [
            BusEvent(name=EventType.SESSION_STARTED.value, source="terminal", payload={"session_id": "s1"}),
            BusEvent(name=EventType.PLAN_CREATED.value, source="terminal", payload={"goal": "test", "steps": ["a", "b"]}),
            BusEvent(name=EventType.PLAN_STEP_STARTED.value, source="terminal", payload={"step_id": "step-0"}),
            BusEvent(name=EventType.TOOL_EXECUTED.value, source="terminal", payload={"step_id": "step-0", "tool_name": "bash"}),
            BusEvent(name=EventType.PLAN_STEP_COMPLETED.value, source="terminal", payload={"step_id": "step-0"}),
            BusEvent(name=EventType.MESSAGE_ADDED.value, source="terminal", payload={"role": "assistant", "content": "done"}),
            BusEvent(name=EventType.SESSION_IDLE.value, source="terminal"),
        ]
        for event in events:
            state = store.dispatch(event)

        assert state.status == SessionStatus.IDLE
        assert state.plan.goal == "test"
        assert len(state.plan.steps) == 2
        assert state.plan.steps[0].status == StepStatus.COMPLETED
        assert len(state.messages) == 1
        assert state.messages[0].content == "done"

    def test_streaming_accumulation(self):
        store = TerminalStore()
        store.dispatch(TerminalEvent(type=EventType.MESSAGE_ADDED, payload={"role": "assistant", "content": ""}))
        for chunk in ["Hello", " ", "world"]:
            store.dispatch(TerminalEvent(type=EventType.STREAM_CHUNK, payload={"chunk": chunk}))
        state = store.state
        assert state.messages[-1].content == "Hello world"

    def test_confirmation_flow(self):
        store = TerminalStore()
        store.dispatch(TerminalEvent(type=EventType.SESSION_STARTED))
        store.dispatch(TerminalEvent(type=EventType.CONFIRMATION_REQUESTED, payload={
            "tool_name": "shell.execute", "description": "rm -rf /", "risk_level": "high",
        }))
        assert store.state.status == SessionStatus.WAITING_CONFIRM
        assert store.state.pending_confirmation is not None


# ── Event Bus integration ───────────────────────────────────────────────


class TestEventBusIntegration:
    def test_bridge_forwards_observer_events(self):
        from core.agent.observer import TaskObserver

        bus = EventBus()
        bridge = EventBusBridge(bus)
        observer = TaskObserver()
        bridge.attach(observer)

        received = []
        bus.subscribe("task.started", lambda e: received.append(e))

        observer.start("t1", "test goal")
        assert len(received) == 1
        assert received[0].payload["goal"] == "test goal"

    def test_bus_wildcard_subscribe(self):
        bus = EventBus()
        received = []
        bus.subscribe("tool.*", lambda e: received.append(e.name))

        bus.publish(BusEvent(name="tool.requested"))
        bus.publish(BusEvent(name="tool.executed"))
        bus.publish(BusEvent(name="task.started"))

        assert received == ["tool.requested", "tool.executed"]


# ── Keymap integration ──────────────────────────────────────────────────


class TestKeymapIntegration:
    def test_ctrl_c_cancels(self):
        keymap = Keymap()
        intent = keymap.resolve("c", ctrl=True)
        assert intent.type == IntentType.CANCEL

    def test_override_binding(self):
        keymap = Keymap()
        keymap.override(KeyBinding(key="x", ctrl=True, intent_type=IntentType.SET_LAYOUT, payload={"mode": "focus"}))
        intent = keymap.resolve("x", ctrl=True)
        assert intent.type == IntentType.SET_LAYOUT
        assert intent.payload["mode"] == "focus"

    def test_unknown_key_returns_unknown(self):
        keymap = Keymap()
        intent = keymap.resolve("z", ctrl=False)
        assert intent.type == IntentType.UNKNOWN


# ── Breakpoint integration ──────────────────────────────────────────────


class TestBreakpointIntegration:
    def test_narrow_shows_only_essentials(self):
        assert classify_width(50) == Breakpoint.NARROW
        panels = panels_for_breakpoint(Breakpoint.NARROW)
        assert "conversation" in panels
        assert "plan" not in panels

    def test_ultra_shows_everything(self):
        assert classify_width(200) == Breakpoint.ULTRA
        panels = panels_for_breakpoint(Breakpoint.ULTRA)
        assert "code" in panels
        assert "memory" in panels

    def test_should_show_logic(self):
        assert should_show(Breakpoint.WIDE, "activity") is True
        assert should_show(Breakpoint.NARROW, "activity") is False


# ── Renderer integration ────────────────────────────────────────────────


class TestRendererIntegration:
    def test_render_idle_state(self):
        renderer = TerminalRenderer(width=80)
        state = SessionState()
        renderable = renderer.render(state)
        assert renderable is not None

    def test_render_with_plan(self):
        renderer = TerminalRenderer(width=120)
        state = SessionState(
            plan=Plan(goal="test goal", steps=(
                PlanStep(description="step 1", status=StepStatus.COMPLETED),
                PlanStep(description="step 2", status=StepStatus.RUNNING),
            )),
        )
        renderable = renderer.render(state)
        assert renderable is not None

    def test_render_status_bar(self):
        renderer = TerminalRenderer(width=80)
        state = SessionState(status=SessionStatus.RUNNING, model="gpt-4", provider="openai")
        panel = renderer.render_status_bar(state)
        assert panel is not None


# ── Persistence integration ─────────────────────────────────────────────


class TestPersistenceIntegration:
    def test_save_and_load_roundtrip(self, tmp_path):
        from jarvis.terminal.types import Message
        persistence = SessionPersistence(db_path=tmp_path / "test.db")
        state = SessionState(
            model="test-model",
            messages=(Message(role="user", content="hello"),),
        )
        persistence.save_state(state)
        loaded = persistence.load_state(state.session_id)
        assert loaded is not None
        assert loaded.model == "test-model"
        assert len(loaded.messages) == 1
        assert loaded.messages[0].content == "hello"
        persistence.close()

    def test_event_replay(self, tmp_path):
        persistence = SessionPersistence(db_path=tmp_path / "replay.db")
        sid = "replay-test"
        events = [
            (TerminalEvent(type=EventType.SESSION_STARTED, payload={"session_id": sid}), 0),
            (TerminalEvent(type=EventType.MESSAGE_ADDED, payload={"role": "user", "content": "hi"}), 1),
            (TerminalEvent(type=EventType.SESSION_IDLE), 2),
        ]
        for event, seq in events:
            persistence.record_event(sid, event, seq)
        state = persistence.replay_events(sid)
        assert state is not None
        assert state.status == SessionStatus.IDLE
        assert len(state.messages) == 1
        persistence.close()

    def test_list_sessions(self, tmp_path):
        persistence = SessionPersistence(db_path=tmp_path / "list.db")
        persistence.save_state(SessionState(session_id="s1"))
        persistence.save_state(SessionState(session_id="s2"))
        sessions = persistence.list_sessions()
        assert len(sessions) == 2
        persistence.close()


# ── Task queue integration ──────────────────────────────────────────────


class TestTaskQueueIntegration:
    def test_submit_and_complete(self):
        queue = TaskQueue()
        queue.start()

        async def work(token: CancellationToken):
            return "done"

        token, task = queue.submit(work, description="test task")
        time.sleep(0.5)
        assert task.state == TaskState.COMPLETED
        assert task.result == "done"
        queue.stop()

    def test_cancellation(self):
        queue = TaskQueue()
        queue.start()

        async def slow_work(token: CancellationToken):
            for _ in range(100):
                await asyncio.sleep(0.05)
                token.check()
            return "should not reach"

        token, task = queue.submit(slow_work, description="slow task")
        time.sleep(0.1)
        queue.cancel(task.id, reason="user stopped")
        time.sleep(0.5)
        assert task.state == TaskState.CANCELLED
        queue.stop()
