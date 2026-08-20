"""Tests for the JARVIS event-sourced core.

Covers:
  - types.py (immutable value objects)
  - core_events.py (versioned events)
  - reducers.py (pure state transitions)
  - store.py (event-sourced store with replay)
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from core.core_events import (
    CoreEvent,
    EventCategory,
    files_changed,
    iteration_incremented,
    message_added,
    mode_changed,
    permission_requested,
    permission_responded,
    plan_created,
    plan_step_updated,
    recovery_completed,
    recovery_started,
    session_started,
    status_message,
    task_completed,
    task_failed,
    task_transitioned,
    tokens_updated,
    tool_completed,
    tool_started,
    verification_failed,
    verification_passed,
    verification_started,
    verification_step,
)
from core.reducers import get_reducer_map, reduce
from core.store import EventSerializer, Store
from core.types import (
    ConfirmationRequest,
    FailureClass,
    Message,
    Mode,
    Plan,
    PlanStep,
    RiskLevel,
    SessionState,
    StepStatus,
    TaskStatus,
    ToolCallRecord,
    VerificationStatus,
    VerificationStep,
)


# ═══════════════════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionState:
    def test_defaults(self):
        s = SessionState()
        assert s.status == TaskStatus.CREATED
        assert s.mode == Mode.AGENT
        assert s.messages == ()
        assert s.tool_calls == ()
        assert s.verification_status == VerificationStatus.IDLE
        assert s.seq == 0

    def test_frozen(self):
        s = SessionState()
        with pytest.raises(AttributeError):
            s.status = TaskStatus.COMPLETED  # type: ignore[misc]

    def test_session_id_generated(self):
        s1 = SessionState()
        s2 = SessionState()
        assert s1.session_id != s2.session_id


class TestPlan:
    def test_new_plan(self):
        plan = Plan.new("fix the bug", ("inspect", "fix", "test"))
        assert plan.goal == "fix the bug"
        assert len(plan.steps) == 3
        assert plan.steps[0].status == StepStatus.ACTIVE
        assert plan.steps[1].status == StepStatus.PENDING

    def test_with_step_pure(self):
        plan = Plan.new("task", ("a", "b"))
        step_id = plan.steps[0].id
        new_plan = plan.with_step(step_id, StepStatus.COMPLETED)
        assert new_plan is not plan
        assert new_plan.steps[0].status == StepStatus.COMPLETED
        assert new_plan.revision == plan.revision + 1
        # Original unchanged
        assert plan.steps[0].status == StepStatus.ACTIVE

    def test_plan_frozen(self):
        plan = Plan.new("task", ("a",))
        with pytest.raises(AttributeError):
            plan.goal = "changed"  # type: ignore[misc]


class TestToolCallRecord:
    def test_frozen(self):
        rec = ToolCallRecord(id="t1", name="shell.execute")
        assert rec.id == "t1"
        with pytest.raises(AttributeError):
            rec.success = False  # type: ignore[misc]


class TestMessage:
    def test_frozen(self):
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        with pytest.raises(AttributeError):
            msg.content = "changed"  # type: ignore[misc]


class TestVerificationStep:
    def test_defaults(self):
        vs = VerificationStep(name="lint")
        assert vs.passed is False
        assert vs.running is False
        assert vs.duration_ms == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Events
# ═══════════════════════════════════════════════════════════════════════════


class TestCoreEvents:
    def test_session_started(self):
        e = session_started("s1", "fix the bug", "agent")
        assert e.seq == 0
        assert e.category == EventCategory.LIFECYCLE
        assert e.name == "session.started"
        assert e.session_id == "s1"
        assert e.payload["goal"] == "fix the bug"

    def test_tool_started(self):
        e = tool_started("s1", 5, "shell.execute", "pytest", "tc1")
        assert e.seq == 5
        assert e.category == EventCategory.TOOL
        assert e.payload["tool"] == "shell.execute"
        assert e.payload["tool_call_id"] == "tc1"

    def test_tool_completed(self):
        e = tool_completed("s1", 6, "shell.execute", "tc1", True, "17 passed", "", 120.5)
        assert e.payload["success"] is True
        assert e.payload["duration_ms"] == 120.5

    def test_plan_created(self):
        e = plan_created("s1", 2, "fix bug", ("inspect", "fix"))
        assert e.payload["steps"] == ["inspect", "fix"]

    def test_verification_step(self):
        e = verification_step("s1", 10, "lint", True, 50.0, "ruff check .")
        assert e.payload["passed"] is True
        assert e.payload["command"] == "ruff check ."

    def test_permission_requested(self):
        req = ConfirmationRequest(operation="shell.execute", risk=RiskLevel.HIGH)
        e = permission_requested("s1", 15, req)
        assert e.payload["risk"] == "high"
        assert e.payload["operation"] == "shell.execute"

    def test_all_events_have_schema_version(self):
        events = [
            session_started("s", "goal"),
            task_completed("s", 1),
            task_failed("s", 2, "tool_failure"),
            tool_started("s", 3, "t"),
            tool_completed("s", 4, "t", "tc", True),
            message_added("s", 5, "user", "hi"),
            plan_created("s", 6, "goal", ()),
            plan_step_updated("s", 7, "sid", StepStatus.COMPLETED),
            verification_started("s", 8),
            verification_step("s", 9, "lint", True),
            verification_passed("s", 10),
            verification_failed("s", 11),
            recovery_started("s", 12, 1),
            recovery_completed("s", 13),
            permission_responded("s", 14, "shell.execute", "once"),
            tokens_updated("s", 15, 1000, 32000, 0.03),
            mode_changed("s", 16, Mode.AGENT),
            iteration_incremented("s", 17, 3),
            files_changed("s", 18, ("a.py",)),
            status_message("s", 19, "hello"),
        ]
        for e in events:
            assert e.schema_version == 2


# ═══════════════════════════════════════════════════════════════════════════
# Reducers
# ═══════════════════════════════════════════════════════════════════════════


class TestReducers:
    def test_reducer_map_populated(self):
        rmap = get_reducer_map()
        assert "session.started" in rmap
        assert "tool.started" in rmap
        assert "task.completed" in rmap
        assert len(rmap) >= 15

    def test_session_started_reducer(self):
        state = SessionState()
        event = session_started("s1", "fix bug", "plan")
        new_state = reduce(state, event)
        assert new_state is not state
        assert new_state.goal == "fix bug"
        assert new_state.mode == Mode.PLAN

    def test_tool_started_reducer(self):
        state = SessionState()
        e = tool_started("s1", 1, "shell.execute", "pytest", "tc1")
        new_state = reduce(state, e)
        assert len(new_state.tool_calls) == 1
        assert new_state.tool_calls[0].name == "shell.execute"
        assert new_state.iteration == 1

    def test_tool_completed_reducer(self):
        state = SessionState()
        s1 = tool_started("s1", 1, "shell.execute", "pytest", "tc1")
        state = reduce(state, s1)
        c1 = tool_completed("s1", 2, "shell.execute", "tc1", True, "17 passed", "", 120.5)
        state = reduce(state, c1)
        assert state.tool_calls[0].success is True
        assert state.tool_calls[0].duration_ms == 120.5
        assert state.tool_calls[0].output == "17 passed"

    def test_message_added_reducer(self):
        state = SessionState()
        e = message_added("s1", 1, "user", "hello")
        new_state = reduce(state, e)
        assert len(new_state.messages) == 1
        assert new_state.messages[0].role == "user"
        assert new_state.messages[0].content == "hello"

    def test_plan_created_reducer(self):
        state = SessionState()
        e = plan_created("s1", 1, "fix bug", ("inspect", "fix"))
        new_state = reduce(state, e)
        assert new_state.plan is not None
        assert len(new_state.plan.steps) == 2

    def test_plan_step_updated_reducer(self):
        state = SessionState()
        s1 = plan_created("s1", 1, "fix bug", ("inspect", "fix"))
        state = reduce(state, s1)
        step_id = state.plan.steps[0].id
        s2 = plan_step_updated("s1", 2, step_id, StepStatus.COMPLETED)
        new_state = reduce(state, s2)
        assert new_state.plan.steps[0].status == StepStatus.COMPLETED

    def test_verification_flow(self):
        state = SessionState()
        # Start verification
        e1 = verification_started("s1", 1)
        state = reduce(state, e1)
        assert state.verification_status == VerificationStatus.RUNNING

        # Step passes
        e2 = verification_step("s1", 2, "lint", True, 50.0, "ruff check .")
        state = reduce(state, e2)
        assert len(state.verification_steps) == 1
        assert state.verification_steps[0].command == "ruff check ."

        # Verification passes
        e3 = verification_passed("s1", 3)
        state = reduce(state, e3)
        assert state.verification_status == VerificationStatus.PASSED

    def test_verification_failed(self):
        state = SessionState()
        state = reduce(state, verification_started("s1", 1))
        state = reduce(state, verification_failed("s1", 2, [{"name": "test", "error": "2 failed"}]))
        assert state.verification_status == VerificationStatus.FAILED
        assert "2 failed" in state.status_message

    def test_recovery_flow(self):
        state = SessionState()
        e = recovery_started("s1", 1, 2, "test failed")
        state = reduce(state, e)
        assert state.recovery_active is True
        assert state.recovery_attempt == 2
        assert state.status == TaskStatus.RECOVERING

        e2 = recovery_completed("s1", 2)
        state = reduce(state, e2)
        assert state.recovery_active is False

    def test_permission_flow(self):
        state = SessionState()
        req = ConfirmationRequest(operation="shell.execute", risk=RiskLevel.HIGH)
        e1 = permission_requested("s1", 1, req)
        state = reduce(state, e1)
        assert state.pending_confirmation is not None
        assert state.pending_confirmation.operation == "shell.execute"

        e2 = permission_responded("s1", 2, "shell.execute", "once")
        state = reduce(state, e2)
        assert state.pending_confirmation is None

    def test_task_transitioned(self):
        state = SessionState()
        e = task_transitioned("s1", 1, TaskStatus.CREATED, TaskStatus.EXECUTING)
        state = reduce(state, e)
        assert state.status == TaskStatus.EXECUTING

    def test_task_completed(self):
        state = SessionState()
        e = task_completed("s1", 1, "done")
        state = reduce(state, e)
        assert state.status == TaskStatus.COMPLETED
        assert len(state.messages) == 1
        assert state.messages[0].content == "done"

    def test_task_failed(self):
        state = SessionState()
        e = task_failed("s1", 1, FailureClass.TIMEOUT, "timed out")
        state = reduce(state, e)
        assert state.status == TaskStatus.FAILED
        assert state.failure_class == FailureClass.TIMEOUT

    def test_tokens_updated(self):
        state = SessionState()
        e = tokens_updated("s1", 1, 5000, 32000, 15.6)
        state = reduce(state, e)
        assert state.tokens_used == 5000
        assert state.context_usage_pct == 15.6

    def test_mode_changed(self):
        state = SessionState()
        e = mode_changed("s1", 1, Mode.CONTROLLED)
        state = reduce(state, e)
        assert state.mode == Mode.CONTROLLED

    def test_files_changed_merges(self):
        state = SessionState()
        e1 = files_changed("s1", 1, ("a.py", "b.py"))
        state = reduce(state, e1)
        e2 = files_changed("s1", 2, ("b.py", "c.py"))
        state = reduce(state, e2)
        assert state.files_changed == ("a.py", "b.py", "c.py")

    def test_unknown_event_passes_through(self):
        state = SessionState()
        event = CoreEvent(seq=1, category="unknown", name="unknown.event")
        new_state = reduce(state, event)
        assert new_state is state  # same object — no change

    def test_reducers_are_pure(self):
        """Reducers never mutate the input state."""
        original = SessionState(goal="test")
        e = tool_started("s1", 1, "shell.execute", "pytest", "tc1")
        new_state = reduce(original, e)
        assert original.goal == "test"
        assert original.tool_calls == ()
        assert original.iteration == 0
        assert new_state.tool_calls == (new_state.tool_calls[0],)


# ═══════════════════════════════════════════════════════════════════════════
# Store
# ═══════════════════════════════════════════════════════════════════════════


class TestStore:
    def test_append_and_snapshot(self):
        store = Store()
        e1 = session_started(store._session_id, "fix bug")
        state = store.append(e1)
        assert state.goal == "fix bug"
        assert store.seq == 0
        assert store.event_count() == 1

    def test_append_many(self):
        store = Store()
        sid = store._session_id
        events = [
            session_started(sid, "fix bug"),
            tool_started(sid, 1, "shell.execute", "pytest", "tc1"),
            tool_completed(sid, 2, "shell.execute", "tc1", True),
            task_completed(sid, 3, "done"),
        ]
        state = store.append_many(events)
        assert state.status == TaskStatus.COMPLETED
        assert store.event_count() == 4

    def test_replay(self):
        store = Store()
        sid = store._session_id
        events = [
            session_started(sid, "fix bug"),
            tool_started(sid, 1, "shell.execute", "pytest", "tc1"),
            tool_completed(sid, 2, "shell.execute", "tc1", True, "passed"),
        ]
        state = store.replay(events)
        assert state.goal == "fix bug"
        assert len(state.tool_calls) == 1
        assert store.event_count() == 3

    def test_listener(self):
        store = Store()
        received = []
        store.on_event(lambda e: received.append(e.name))
        store.append(session_started(store._session_id, "task"))
        assert received == ["session.started"]

    def test_save_and_load_events(self):
        store = Store()
        sid = store._session_id
        store.append_many([
            session_started(sid, "fix bug"),
            tool_started(sid, 1, "shell.execute", "pytest", "tc1"),
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            store.save_events(path)

            store2 = Store(_session_id=sid)
            count = store2.load_events(path)
            assert count == 2
            assert store2.state.goal == "fix bug"
            assert len(store2.state.tool_calls) == 1

    def test_save_and_load_snapshot(self):
        store = Store()
        store.append(session_started(store._session_id, "fix bug"))
        store.append(tool_started(store._session_id, 1, "shell.execute", "pytest", "tc1"))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshot.json"
            store.save_snapshot(path)

            store2 = Store()
            assert store2.load_snapshot(path) is True
            assert store2.state.goal == "fix bug"

    def test_clear(self):
        store = Store()
        store.append(session_started(store._session_id, "fix bug"))
        store.clear()
        assert store.event_count() == 0
        assert store.state.goal == ""

    def test_recent_events(self):
        store = Store()
        sid = store._session_id
        for i in range(10):
            store.append(tool_started(sid, i, f"tool_{i}", "", f"tc_{i}"))
        recent = store.recent_events(limit=3)
        assert len(recent) == 3
        assert recent[0].payload["tool"] == "tool_7"


# ═══════════════════════════════════════════════════════════════════════════
# Serializer
# ═══════════════════════════════════════════════════════════════════════════


class TestEventSerializer:
    def test_roundtrip(self):
        event = tool_started("s1", 5, "shell.execute", "pytest", "tc1")
        line = EventSerializer.serialize(event)
        restored = EventSerializer.deserialize(line)
        assert restored is not None
        assert restored.seq == 5
        assert restored.name == "tool.started"
        assert restored.payload["tool"] == "shell.execute"

    def test_state_roundtrip(self):
        state = SessionState(goal="fix bug", mode=Mode.CONTROLLED)
        data = EventSerializer.serialize_state(state)
        restored = EventSerializer.deserialize_state(data)
        assert restored is not None
        assert restored.goal == "fix bug"
        assert restored.mode == Mode.CONTROLLED

    def test_bad_json_returns_none(self):
        assert EventSerializer.deserialize("not json") is None

    def test_bad_state_json_returns_none(self):
        assert EventSerializer.deserialize_state("not json") is None


# ═══════════════════════════════════════════════════════════════════════════
# Integration: full lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestFullLifecycle:
    def test_complete_task_lifecycle(self):
        """Simulate a full agent run: start → plan → execute → verify → complete."""
        store = Store()
        sid = store._session_id

        # 1. Session starts
        store.append(session_started(sid, "fix the auth bug", "smart"))

        # 2. Plan created
        store.append(plan_created(sid, 1, "fix the auth bug", ("inspect", "fix", "test")))

        # 3. Tool: inspect
        store.append(tool_started(sid, 2, "filesystem.read", "auth.py", "tc1"))
        store.append(tool_completed(sid, 3, "filesystem.read", "tc1", True, "284 lines"))

        # 4. Plan step 1 done
        plan = store.state.plan
        store.append(plan_step_updated(sid, 4, plan.steps[0].id, StepStatus.COMPLETED))

        # 5. Tool: fix
        store.append(tool_started(sid, 5, "edit_file", "auth.py", "tc2"))
        store.append(tool_completed(sid, 6, "edit_file", "tc2", True, "+14 -6"))
        store.append(files_changed(sid, 7, ("auth.py",)))

        # 6. Plan step 2 done
        store.append(plan_step_updated(sid, 8, plan.steps[1].id, StepStatus.COMPLETED))

        # 7. Tool: test
        store.append(tool_started(sid, 9, "shell.execute", "pytest", "tc3"))
        store.append(tool_completed(sid, 10, "shell.execute", "tc3", True, "24 passed"))

        # 8. Verification
        store.append(verification_started(sid, 11))
        store.append(verification_step(sid, 12, "pytest", True, 1200.0))
        store.append(verification_passed(sid, 13))

        # 9. Tokens
        store.append(tokens_updated(sid, 14, 8500, 32000, 26.6))

        # 10. Complete
        store.append(task_completed(sid, 15, "Fixed the auth bug. 24 tests pass."))

        # Verify final state
        final = store.state
        assert final.status == TaskStatus.COMPLETED
        assert final.goal == "fix the auth bug"
        assert final.mode == Mode.SMART
        assert len(final.tool_calls) == 3
        assert final.tool_calls[0].name == "filesystem.read"
        assert final.tool_calls[2].name == "shell.execute"
        assert len(final.files_changed) == 1
        assert final.verification_status == VerificationStatus.PASSED
        assert len(final.verification_steps) == 1
        assert final.plan is not None
        assert final.plan.steps[0].status == StepStatus.COMPLETED
        assert final.tokens_used == 8500
        assert final.messages[0].role == "agent"
        assert "auth bug" in final.messages[0].content
        assert store.event_count() == 16

    def test_failure_and_recovery_lifecycle(self):
        """Simulate: execute → fail → recover → retry → complete."""
        store = Store()
        sid = store._session_id

        store.append(session_started(sid, "run tests", "agent"))
        store.append(tool_started(sid, 1, "shell.execute", "pytest", "tc1"))
        store.append(tool_completed(sid, 2, "shell.execute", "tc1", False, "", "2 failed", 800.0))
        store.append(task_transitioned(sid, 3, TaskStatus.EXECUTING, TaskStatus.VERIFYING))
        store.append(verification_started(sid, 4))
        store.append(verification_step(sid, 5, "pytest", False, 800.0, "pytest tests/", "2 failed"))
        store.append(verification_failed(sid, 6, [{"name": "pytest", "error": "2 failed"}]))

        # Recovery
        store.append(recovery_started(sid, 7, 1, "2 tests failed"))
        assert store.state.recovery_active is True
        assert store.state.status == TaskStatus.RECOVERING

        # Retry
        store.append(tool_started(sid, 8, "edit_file", "auth.py", "tc2"))
        store.append(tool_completed(sid, 9, "edit_file", "tc2", True, "+14 -6"))
        store.append(recovery_completed(sid, 10))
        store.append(tool_started(sid, 11, "shell.execute", "pytest", "tc3"))
        store.append(tool_completed(sid, 12, "shell.execute", "tc3", True, "24 passed"))
        store.append(verification_started(sid, 13))
        store.append(verification_step(sid, 14, "pytest", True, 1200.0))
        store.append(verification_passed(sid, 15))
        store.append(task_completed(sid, 16, "All 24 tests pass."))

        final = store.state
        assert final.status == TaskStatus.COMPLETED
        assert final.recovery_active is False
        assert final.verification_status == VerificationStatus.PASSED
        assert len(final.tool_calls) == 3  # tc1, tc2, tc3

    def test_full_lifecycle_persistence(self):
        """Save events to disk, reload, and verify state is identical."""
        store = Store()
        sid = store._session_id
        store.append_many([
            session_started(sid, "fix bug"),
            tool_started(sid, 1, "shell.execute", "pytest", "tc1"),
            tool_completed(sid, 2, "shell.execute", "tc1", True, "17 passed"),
            task_completed(sid, 3, "done"),
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            store.save_events(path)

            # New store, replay from disk
            store2 = Store(_session_id=sid)
            store2.load_events(path)

            assert store2.state.goal == "fix bug"
            assert store2.state.status == TaskStatus.COMPLETED
            assert len(store2.state.tool_calls) == 1
            assert store2.event_count() == 4
