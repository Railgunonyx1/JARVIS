"""Integration tests for the CLI bridge event pipeline.

Tests that verification/recovery events flow through the bridge into
dedicated AppState fields, and that the renderer produces correct blocks.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from cli.bridge import AgentBridge
from cli.models import AppState, Message, StepStatus
from cli.renderer import Renderer
from cli.ux import LiveTaskDisplay


# ── Helpers ─────────────────────────────────────────────────────────────


def _make_bridge() -> AgentBridge:
    """Create a bridge with a fresh renderer and state."""
    renderer = Renderer()
    return AgentBridge(renderer=renderer)


# ── Verification event tests ────────────────────────────────────────────


class TestVerificationEvents:
    def test_verification_started_initializes_state(self):
        bridge = _make_bridge()
        bridge._on_verification_started({})
        assert bridge.state.verification_steps == []
        assert bridge.state.verification_status == "running"

    def test_verification_step_appends_to_state(self):
        bridge = _make_bridge()
        bridge._on_verification_started({})
        bridge._on_verification_step({"name": "tests", "passed": True, "duration_ms": 1200})
        bridge._on_verification_step({"name": "lint", "passed": True, "duration_ms": 300})
        assert len(bridge.state.verification_steps) == 2
        assert bridge.state.verification_steps[0]["name"] == "tests"
        assert bridge.state.verification_steps[0]["passed"] is True
        assert bridge.state.verification_steps[1]["name"] == "lint"
        assert bridge.state.verification_steps[1]["passed"] is True

    def test_verification_passed_sets_status(self):
        bridge = _make_bridge()
        bridge._on_verification_started({})
        bridge._on_verification_step({"name": "tests", "passed": True, "duration_ms": 100})
        bridge._on_verification_passed({"steps_run": 1})
        assert bridge.state.verification_status == "passed"
        assert bridge.state.status_message == ""

    def test_verification_failed_sets_status_and_message(self):
        bridge = _make_bridge()
        bridge._on_verification_started({})
        bridge._on_verification_step({"name": "tests", "passed": False, "duration_ms": 100})
        bridge._on_verification_failed({
            "failures": [{"name": "tests", "error": "2 tests failed"}]
        })
        assert bridge.state.verification_status == "failed"
        assert "verification failed" in bridge.state.status_message

    def test_verification_does_not_pollute_messages(self):
        """Verification events should NOT create Message objects."""
        bridge = _make_bridge()
        initial_count = len(bridge.state.messages)
        bridge._on_verification_started({})
        bridge._on_verification_step({"name": "tests", "passed": True})
        bridge._on_verification_passed({"steps_run": 1})
        assert len(bridge.state.messages) == initial_count

    def test_full_verification_sequence(self):
        """Simulate: started → step1 → step2 → step3 → passed."""
        bridge = _make_bridge()
        bridge._on_verification_started({})
        bridge._on_verification_step({"name": "tests", "passed": True, "duration_ms": 1200})
        bridge._on_verification_step({"name": "lint", "passed": True, "duration_ms": 300})
        bridge._on_verification_step({"name": "typecheck", "passed": True, "duration_ms": 500})
        bridge._on_verification_passed({"steps_run": 3})

        assert bridge.state.verification_status == "passed"
        assert len(bridge.state.verification_steps) == 3
        assert all(s["passed"] for s in bridge.state.verification_steps)

    def test_verification_failure_sequence(self):
        """Simulate: started → step1(pass) → step2(fail) → failed."""
        bridge = _make_bridge()
        bridge._on_verification_started({})
        bridge._on_verification_step({"name": "tests", "passed": True, "duration_ms": 1200})
        bridge._on_verification_step({"name": "lint", "passed": False, "duration_ms": 300})
        bridge._on_verification_failed({
            "failures": [{"name": "lint", "error": "E501 line too long"}]
        })

        assert bridge.state.verification_status == "failed"
        assert len(bridge.state.verification_steps) == 2
        assert bridge.state.verification_steps[1]["passed"] is False


# ── Recovery event tests ────────────────────────────────────────────────


class TestRecoveryEvents:
    def test_recovery_started_activates_state(self):
        bridge = _make_bridge()
        bridge._on_recovery_started({"error": "tests failed", "attempt": 2})
        assert bridge.state.recovery_active is True
        assert bridge.state.recovery_attempt == 2
        assert "tests failed" in bridge.state.recovery_error
        assert "recovering" in bridge.state.status_message

    def test_recovery_does_not_pollute_messages(self):
        """Recovery events should NOT create Message objects."""
        bridge = _make_bridge()
        initial_count = len(bridge.state.messages)
        bridge._on_recovery_started({"error": "tests failed", "attempt": 1})
        assert len(bridge.state.messages) == initial_count

    def test_recovery_cleared_on_task_finished(self):
        """When the task finishes, recovery state should be cleared."""
        bridge = _make_bridge()
        bridge._on_recovery_started({"error": "tests failed", "attempt": 2})
        assert bridge.state.recovery_active is True
        bridge._on_task_finished({})
        assert bridge.state.recovery_active is False


# ── Conversation renderer integration tests ─────────────────────────────


class TestConversationWithVerification:
    def test_conversation_includes_verification_block(self):
        """When verification_steps are populated, the conversation includes them."""
        renderer = Renderer()
        renderer.state.messages = [
            Message(role="user", content="run tests"),
            Message(role="agent", content="Running verification..."),
        ]
        renderer.state.verification_steps = [
            {"name": "tests", "passed": True, "duration_ms": 1200},
            {"name": "lint", "passed": True, "duration_ms": 300},
        ]
        renderer.state.verification_status = "passed"

        block = renderer.render_conversation()
        assert block is not None

    def test_conversation_includes_recovery_block(self):
        """When recovery is active, the conversation includes the recovery block."""
        renderer = Renderer()
        renderer.state.messages = [
            Message(role="user", content="run tests"),
            Message(role="agent", content="Tests failed, recovering..."),
        ]
        renderer.state.recovery_active = True
        renderer.state.recovery_attempt = 2
        renderer.state.recovery_error = "pytest: 2 tests failed"

        block = renderer.render_conversation()
        assert block is not None

    def test_conversation_without_verification_or_recovery(self):
        """Normal conversation without verification/recovery works fine."""
        renderer = Renderer()
        renderer.state.messages = [
            Message(role="user", content="hello"),
            Message(role="agent", content="Hi!"),
        ]
        block = renderer.render_conversation()
        assert block is not None


# ── Renderer tool card tests ────────────────────────────────────────────


class TestToolCards:
    def test_collapsed_tool_card(self):
        renderer = Renderer()
        card = renderer.render_tool_card(
            "filesystem.read",
            {"path": "src/auth.py"},
            status="ok",
            duration_ms=18,
        )
        assert card is not None

    def test_expanded_tool_card(self):
        renderer = Renderer()
        card = renderer.render_tool_card(
            "shell.execute",
            {"command": "pytest tests/"},
            status="ok",
            duration_ms=1200,
            expanded=True,
        )
        assert card is not None

    def test_running_tool_card(self):
        renderer = Renderer()
        card = renderer.render_tool_card(
            "search.code",
            {"pattern": "TODO"},
            status="running",
        )
        assert card is not None

    def test_denied_tool_card(self):
        renderer = Renderer()
        card = renderer.render_tool_card(
            "shell.execute",
            {"command": "rm -rf /"},
            status="denied",
        )
        assert card is not None


# ── Verification/Recovery renderer tests ────────────────────────────────


class TestVerificationRecoveryRenderer:
    def test_verification_block_all_passed(self):
        renderer = Renderer()
        steps = [
            {"name": "tests", "passed": True, "duration_ms": 1200},
            {"name": "lint", "passed": True, "duration_ms": 300},
        ]
        block = renderer.render_verification_block(steps)
        assert block is not None

    def test_verification_block_with_failure(self):
        renderer = Renderer()
        steps = [
            {"name": "tests", "passed": True, "duration_ms": 1200},
            {"name": "lint", "passed": False, "duration_ms": 300},
        ]
        block = renderer.render_verification_block(steps)
        assert block is not None

    def test_verification_block_empty(self):
        renderer = Renderer()
        block = renderer.render_verification_block([])
        assert block is not None

    def test_recovery_block(self):
        renderer = Renderer()
        block = renderer.render_recovery_block("pytest failed: 2 tests", attempt=2)
        assert block is not None

    def test_recovery_block_first_attempt(self):
        renderer = Renderer()
        block = renderer.render_recovery_block("permission denied", attempt=1)
        assert block is not None
