"""Approval-path integration checks for the Dynamic Island desktop runtime."""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time

os.environ.setdefault("JARVIS_DESKTOP_HOME", "/tmp/jarvis-island-test-audit")
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for _path in (_ROOT, os.path.join(_ROOT, "dynamic-island")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.integration.coordinator import AppCoordinator
from app.integration.jarvis_backend import JarvisBackend
from app.ui.conversation_panel import ConversationPanel
from app.ui.overlay_window import IslandWindow, ApprovalRecord
from core.agent.loop import AgentLoop
from core.agent.permissions import PermissionEngine
from core.agent.tool_service import ToolExecutionService
from core.decision_logger import DecisionLogger
from core.harness import Harness, HarnessConfig, HarnessType
from core.project import ProjectContext
from providers.types import LLMResponse, ToolCall
from tools.registry import ToolRegistry
from tools.schema import Tool

app = QApplication.instance() or QApplication([])


class _Logger:
    def begin_task(self, *_args, **_kwargs):
        return "approval-trace"

    def record(self, *_args, **_kwargs):
        pass

    def record_tool(self, *_args, **_kwargs):
        pass

    def flush(self):
        pass


class _ToolRouter:
    preferred_provider = None
    _last_model = "test-model"
    _last_provider = "test"

    def __init__(self, tool_call):
        self.tool_call = tool_call
        self.calls = 0

    async def complete_stream_typed(self, _messages, **_kwargs):
        self.calls += 1
        calls = [self.tool_call] if self.calls == 1 else []
        yield "", calls

    async def complete(self, _messages, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                text="", model="test", provider="test", tool_calls=[self.tool_call]
            )
        return LLMResponse(text="complete", model="test", provider="test")


def _risky_tool(executed):
    async def handler(arguments):
        executed.append(dict(arguments))
        return {"success": True, "output": "executed"}

    return Tool(
        name="approval.test_action",
        description="test approval action",
        parameters={"type": "object", "properties": {"marker": {"type": "string"}}},
        permission="filesystem.write",
        risk="high",
        is_destructive=True,
        handler=handler,
    )


def _permission_engine(handler):
    logger = _Logger()
    return PermissionEngine(
        logger,
        mode="smart",
        confirmation_handler=handler,
        trusted_mcp_servers=(),
        trusted_workspace=False,
    )


def _await_record(island, approval_id=None, timeout=4.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if approval_id is not None:
            record = island._get_approval(approval_id)
        else:
            island._approval_registry_mutex.lock()
            try:
                record = next(iter(island._approval_registry.values()), None)
            finally:
                island._approval_registry_mutex.unlock()
        if record is not None:
            return record
        time.sleep(0.001)
    raise AssertionError(f"approval record did not appear: {approval_id!r}")


def _run_worker(function):
    result = {}
    errors = []

    def run():
        try:
            result["value"] = function()
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=run, name="approval-integration-worker")
    worker.start()
    return worker, result, errors


def _finish_worker(worker, result, errors):
    worker.join(timeout=12.0)
    assert not worker.is_alive(), "approval worker failed to return"
    assert not errors, f"approval path raised: {errors!r}"
    return result["value"]


def _make_agent_path(island, executed):
    coordinator = AppCoordinator(mode="smart", confirmation_handler=island._confirm)
    backend = JarvisBackend(mode="smart", confirmation_handler=coordinator._action_confirmation)
    coordinator._backend = backend
    coordinator._actions = __import__(
        "app.desktop.actions", fromlist=["DesktopActionLayer"]
    ).DesktopActionLayer(confirmation_handler=coordinator._action_confirmation)

    registry = ToolRegistry()
    tool = _risky_tool(executed)
    registry.register(tool)
    permissions = _permission_engine(backend._confirmation_handler)
    permissions.security = __import__("types").SimpleNamespace(
        check_permission=lambda *_args, **_kwargs: (True, "")
    )
    permissions.mode_manager.requires_confirmation = lambda capability, mode=None: False
    service = ToolExecutionService(
        registry=registry,
        permissions=permissions,
        decision_logger=_Logger(),
        mode="smart",
    )
    harness = Harness(HarnessConfig(
        harness_type=HarnessType.MINIMAL,
        enable_verification=False,
        max_iterations=2,
    ))
    loop = AgentLoop(
        router=_ToolRouter(ToolCall(
            name=tool.name, arguments={"marker": "from-agent"}, id="agent-tool-call"
        )),
        registry=registry,
        project=ProjectContext(root_path=_ROOT),
        decision_logger=_Logger(),
        mode="smart",
        harness=harness,
        tool_service=service,
    )
    backend._agent_loop = loop
    return coordinator, backend, loop, permissions, tool


def test_permission_callback_contract_spans_agent_backend_coordinator_island_and_click():
    island = IslandWindow()
    executed = []
    coordinator, backend, loop, _permissions, _tool = _make_agent_path(island, executed)

    worker, result, errors = _run_worker(lambda: asyncio.run(
        backend._run_agent_with_id("do the protected action", request_id=71)
    ))
    record = _await_record(island)
    app.processEvents()
    assert record.approval_id.startswith("approval-")
    assert island._panel._current_approval_id == record.approval_id
    assert record.approval_id in island._panel._approval_sinks
    assert executed == []

    # Click the actual inline Allow button; its captured approval ID flows via
    # ConversationPanel -> ApprovalSink -> ApprovalRecord -> PermissionEngine.
    island._panel._on_approval_btn(True, record.approval_id)
    _finish_worker(worker, result, errors)
    assert record.state == "approved_once"
    assert executed == [{"marker": "from-agent"}]

    coordinator._backend = None
    island.close()


def test_deny_click_returns_through_agent_loop_and_blocks_tool_handler():
    island = IslandWindow()
    executed = []
    _coordinator, backend, _loop, _permissions, _tool = _make_agent_path(island, executed)

    worker, result, errors = _run_worker(lambda: asyncio.run(
        backend._run_agent_with_id("deny protected action", request_id=72)
    ))
    record = _await_record(island)
    app.processEvents()
    island._panel._on_approval_btn(False, record.approval_id)
    _finish_worker(worker, result, errors)
    assert record.state == "denied"
    assert executed == []
    island.close()


def test_duplicate_and_conflicting_terminal_transitions_have_exactly_one_winner():
    for idx in range(24):
        record = ApprovalRecord(f"approval-race-{idx}", "test_action", {})
        barrier = threading.Barrier(3)
        results = []

        def decide(method):
            barrier.wait()
            results.append(method())

        workers = [
            threading.Thread(target=decide, args=(record.approve,)),
            threading.Thread(target=decide, args=(record.deny,)),
        ]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(timeout=2.0)
            assert not worker.is_alive()
        assert sum(results) == 1
        assert record.state in ("approved_once", "denied")
        assert record.approve() is False
        assert record.deny() is False
        assert record.state in ("approved_once", "denied")


def test_timeout_and_decision_race_never_overwrite_first_terminal_state():
    for idx in range(12):
        record = ApprovalRecord(f"approval-timeout-race-{idx}", "test_action", {})
        barrier = threading.Barrier(2)
        waiter = threading.Thread(target=lambda: (barrier.wait(), record.wait(0.01)))
        decider = threading.Thread(target=lambda: (barrier.wait(), record.approve()))
        waiter.start()
        decider.start()
        waiter.join(timeout=2.0)
        decider.join(timeout=2.0)
        assert not waiter.is_alive() and not decider.is_alive()
        assert record.state in ("approved_once", "expired")
        state = record.state
        assert record.deny() is False
        assert record.state == state


def test_window_hide_resolves_pending_approval_to_denial():
    island = IslandWindow()
    coordinator, _backend, _loop, _permissions, tool = _make_agent_path(island, [])
    worker, result, errors = _run_worker(lambda: asyncio.run(
        _permissions.check(tool, {"marker": "hide"}, "trace-hide")
    ))
    record = _await_record(island)
    island.hide_island()
    assert _finish_worker(worker, result, errors)[0] is False
    assert record.state == "denied"
    coordinator._backend = None
    island.close()


def test_permission_service_denial_never_executes_risky_tool():
    island = IslandWindow()
    coordinator, backend, _loop, permissions, tool = _make_agent_path(island, [])
    island.expand()  # Create the panel lazily
    executed = []
    tool.handler = lambda args: executed.append(args) or {"success": True, "output": "bad"}
    registry = ToolRegistry()
    registry.register(tool)
    service = ToolExecutionService(
        registry=registry, permissions=permissions, decision_logger=_Logger(), mode="smart"
    )
    worker, result, errors = _run_worker(lambda: asyncio.run(service.execute_tool(
        ToolCall(name=tool.name, arguments={"marker": "deny"}, id="deny-service-call")
    )))
    record = _await_record(island)
    island._panel._on_approval_btn(False, record.approval_id)
    denied_result = _finish_worker(worker, result, errors)
    assert denied_result.permission_denied
    assert executed == []
    coordinator._backend = None
    island.close()


def test_concurrent_approval_requests_are_isolated_and_presented_one_at_a_time():
    island = IslandWindow()
    coordinator, _backend, _loop, _permissions, _tool = _make_agent_path(island, [])
    outcomes = {}
    errors = []
    ids = ["approval-concurrent-A", "approval-concurrent-B"]

    def invoke(approval_id):
        try:
            outcomes[approval_id] = island._confirm("test_action", {"id": approval_id}, approval_id)
        except Exception as exc:
            errors.append(exc)

    workers = [threading.Thread(target=invoke, args=(aid,)) for aid in ids]
    for worker in workers:
        worker.start()
    deadline = time.monotonic() + 4.0
    records = {}
    while time.monotonic() < deadline and len(records) < len(ids):
        app.processEvents()
        island._approval_registry_mutex.lock()
        try:
            records.update({aid: island._approval_registry[aid] for aid in ids if aid in island._approval_registry})
        finally:
            island._approval_registry_mutex.unlock()
        time.sleep(0.001)
    assert set(records) == set(ids)
    app.processEvents()
    assert island._panel._current_approval_id in ids
    first_id = island._panel._current_approval_id
    island._panel._on_approval_btn(True, first_id)
    deadline = time.monotonic() + 3.0
    second_id = None
    while time.monotonic() < deadline:
        app.processEvents()
        second_id = island._panel._current_approval_id
        if second_id is not None and second_id != first_id:
            break
        time.sleep(0.001)
    assert second_id in ids and second_id != first_id
    island._panel._on_approval_btn(False, second_id)
    for worker in workers:
        worker.join(timeout=12.0)
    assert not any(worker.is_alive() for worker in workers)
    assert not errors
    assert outcomes[first_id] == "once"
    assert outcomes[second_id] == "deny"
    assert records[first_id].state == "approved_once"
    assert records[second_id].state == "denied"
    coordinator._backend = None
    island.close()


def test_panel_consumes_double_click_and_wrong_id_decisions_once():
    panel = ConversationPanel()
    got = []
    from app.ui.conversation_panel import ApprovalSink
    sink = ApprovalSink("approval-current", got.append)
    panel._approval_sinks["approval-current"] = sink
    panel.set_approval("test_action", "", "approval-current")
    panel._on_approval_btn(True, "approval-stale")
    panel._on_approval_btn(True, "approval-current")
    panel._on_approval_btn(False, "approval-current")
    assert got == ["once"]


def test_expired_request_cannot_be_approved_late():
    record = ApprovalRecord("approval-expired", "test_action", {})
    assert record.wait(0.001) == "expired"
    assert record.approve() is False
    assert record.state == "expired"


def test_generated_approval_id_passes_the_coordinator_adapter():
    island = IslandWindow()
    coordinator = AppCoordinator(mode="smart", confirmation_handler=island._confirm)
    observed = {}

    def handler(tool_name, arguments, approval_id):
        observed.update(tool=tool_name, arguments=arguments, approval_id=approval_id)
        return "deny"

    coordinator._confirmation_handler = handler
    assert coordinator._action_confirmation("tool.name", {"x": 1}) == "deny"
    assert observed["tool"] == "tool.name"
    assert observed["arguments"] == {"x": 1}
    assert observed["approval_id"].startswith("approval-")


def test_coordinator_preserves_two_argument_permission_callback_shape():
    island = IslandWindow()
    coordinator = AppCoordinator(mode="smart", confirmation_handler=island._confirm)
    invoked = {}

    def handler(tool_name, arguments, approval_id):
        invoked.update(tool=tool_name, args=arguments, id=approval_id)
        return "deny"

    coordinator._confirmation_handler = handler
    assert coordinator._action_confirmation("tool.name", {"target": 3}) == "deny"
    assert invoked == {
        "tool": "tool.name", "args": {"target": 3}, "id": invoked["id"]
    }
    assert invoked["id"].startswith("approval-")
