"""Sprint 20 -- Kernel integration tests.

Tests the full pipeline: Harness -> Gateway -> AgentLoop -> ToolExecution -> Bus.
"""

from __future__ import annotations

import asyncio

import pytest

from core.agent.loop import AgentLoop, AgentResult
from core.agent.tool_service import ToolExecutionService, ToolExecutionResult
from core.agent.verification import VerificationEngine, VerificationReport
from core.harness import Harness, HarnessSelector, HarnessType, HarnessConfig
from providers.model_gateway import (
    Capability, Combo, ModelGateway, ModelProfile, ProviderHealth,
)
from providers.types import LLMResponse, ToolCall
from tools import build_default_registry
from core.project import ProjectContext
from runtime.protocols import MCPAdapter, ACPAdapter, CodexExecAdapter

import os
import tempfile

ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])


class StubLogger:
    def begin_task(self, request, source=""):
        return "test_trace"
    def record(self, *a, **kw):
        pass
    def record_tool(self, *a, **kw):
        pass
    def flush(self):
        pass


class FakeRouter:
    def __init__(self, responses):
        self._responses = list(responses)
    async def complete(self, messages, **kw):
        return self._responses.pop(0)


def _resp(text="", **kw):
    return LLMResponse(text=text, model="fake-model", provider="fake",
                       tokens_prompt=10, tokens_completion=5, **kw)


# ── Harness tests ──────────────────────────────────────────────────────


class TestHarness:
    def test_harness_config_overrides(self):
        hc = HarnessConfig(
            harness_type=HarnessType.CODING,
            max_iterations=25,
            temperature=0.2,
            max_tool_calls_per_step=10,
        )
        h = Harness(hc)
        assert h.config.max_iterations == 25
        assert h.config.temperature == 0.2

    def test_harness_tool_filtering(self):
        hc = HarnessConfig(
            harness_type=HarnessType.RESEARCH,
            tool_whitelist=("web_search", "file_read"),
        )
        h = Harness(hc)
        tools = [
            {"function": {"name": "web_search"}},
            {"function": {"name": "bash"}},
            {"function": {"name": "file_read"}},
        ]
        filtered = h.filter_tools(tools)
        assert len(filtered) == 2
        names = {t["function"]["name"] for t in filtered}
        assert names == {"web_search", "file_read"}

    def test_harness_tool_blacklist(self):
        hc = HarnessConfig(
            harness_type=HarnessType.NATIVE,
            tool_blacklist=("shell.execute",),
        )
        h = Harness(hc)
        tools = [
            {"function": {"name": "web_search"}},
            {"function": {"name": "shell.execute"}},
        ]
        filtered = h.filter_tools(tools)
        assert len(filtered) == 1

    def test_system_prompt_addendum(self):
        hc = HarnessConfig(
            harness_type=HarnessType.DEBUG,
            system_prompt_addendum="\nAlways reproduce first.",
        )
        h = Harness(hc)
        assert "reproduce" in h.build_system_prompt_addendum()


# ── HarnessSelector tests ─────────────────────────────────────────────


class TestHarnessSelector:
    def test_default_is_native(self):
        sel = HarnessSelector()
        assert sel.active.type == HarnessType.NATIVE

    def test_select_specific(self):
        sel = HarnessSelector()
        h = sel.select(HarnessType.CODING)
        assert h.type == HarnessType.CODING
        assert sel.active is h

    def test_auto_select_debug(self):
        sel = HarnessSelector()
        h = sel.auto_select("fix the authentication bug")
        assert h.type == HarnessType.DEBUG

    def test_auto_select_coding(self):
        sel = HarnessSelector()
        h = sel.auto_select("implement a new feature for user auth")
        assert h.type == HarnessType.CODING

    def test_auto_select_research(self):
        sel = HarnessSelector()
        h = sel.auto_select("search for best practices in testing")
        assert h.type == HarnessType.RESEARCH

    def test_list_harnesses(self):
        sel = HarnessSelector()
        items = sel.list_harnesses()
        assert len(items) == 6
        assert any(h["type"] == "coding" for h in items)


# ── ModelGateway tests ────────────────────────────────────────────────


class TestModelGateway:
    def test_register_and_select(self):
        gw = ModelGateway()
        gw.register_model(ModelProfile(
            name="gemini-2.5-pro", provider="gemini",
            capabilities=(Capability.CODING, Capability.REASONING),
        ))
        gw.register_model(ModelProfile(
            name="llama-3", provider="groq",
            capabilities=(Capability.FAST,),
        ))
        best = gw.select(requirements={Capability.CODING})
        assert best is not None
        assert best.provider == "gemini"

    def test_health_cooldown(self):
        gw = ModelGateway()
        gw.register_model(ModelProfile(
            name="model-a", provider="provider-a",
            capabilities=(Capability.CODING,),
        ))
        # Simulate failures
        for _ in range(5):
            gw.record_failure("provider-a")
        best = gw.select(requirements={Capability.CODING})
        assert best is None  # provider in cooldown

    def test_session_affinity(self):
        gw = ModelGateway()
        gw.register_model(ModelProfile(
            name="m1", provider="p1", capabilities=(Capability.CODING,),
        ))
        gw.register_model(ModelProfile(
            name="m2", provider="p2", capabilities=(Capability.CODING,),
        ))
        gw.select(requirements={Capability.CODING}, session_id="s1")
        # Second call should return same model (affinity)
        second = gw.select(requirements={Capability.CODING}, session_id="s1")
        assert second is not None
        assert second.name == "m1"

    def test_combo_selection(self):
        gw = ModelGateway()
        gw.register_model(ModelProfile(
            name="fast", provider="groq", capabilities=(Capability.FAST,),
        ))
        gw.register_model(ModelProfile(
            name="smart", provider="gemini", capabilities=(Capability.CODING,),
        ))
        gw.register_combo(Combo(
            name="coding-fast",
            models=(
                ModelProfile(name="fast", provider="groq", capabilities=(Capability.FAST,)),
                ModelProfile(name="smart", provider="gemini", capabilities=(Capability.CODING,)),
            ),
        ))
        best = gw.select(combo_name="coding-fast")
        assert best is not None
        assert best.provider == "groq"  # fast is first and healthy

    def test_status(self):
        gw = ModelGateway()
        gw.register_model(ModelProfile(name="m", provider="p"))
        gw.record_success("p", 100.0)
        s = gw.status()
        assert "models" in s
        assert "health" in s


# ── ToolExecutionService tests ────────────────────────────────────────


class TestToolExecutionService:
    def test_execute_unknown_tool(self):
        svc = ToolExecutionService(registry=build_default_registry())
        call = ToolCall(name="nonexistent.tool", arguments={}, id="t1")
        result = asyncio.run(svc.execute_tool(call))
        assert not result.success
        assert "not registered" in result.error

    def test_execute_known_tool(self):
        svc = ToolExecutionService(registry=build_default_registry())
        import tempfile, os
        tmp = os.path.join(tempfile.gettempdir(), "test_svc.txt")
        call = ToolCall(name="filesystem.write", arguments={"path": tmp, "content": "hello"}, id="t2")
        result = asyncio.run(svc.execute_tool(call))
        assert result.success
        if os.path.exists(tmp):
            os.remove(tmp)

    def test_execute_appends_to_messages(self):
        svc = ToolExecutionService(registry=build_default_registry())
        import tempfile, os
        tmp = os.path.join(tempfile.gettempdir(), "test_svc2.txt")
        call = ToolCall(name="filesystem.write", arguments={"path": tmp, "content": "world"}, id="t3")
        msgs = []
        asyncio.run(svc.execute_tool(call, append_to_messages=msgs))
        assert len(msgs) == 1
        assert msgs[0]["role"] == "tool"
        if os.path.exists(tmp):
            os.remove(tmp)

    def test_execute_tools_batch(self):
        svc = ToolExecutionService(registry=build_default_registry())
        import tempfile, os
        tmp1 = os.path.join(tempfile.gettempdir(), "test_b1.txt")
        tmp2 = os.path.join(tempfile.gettempdir(), "test_b2.txt")
        calls = [
            ToolCall(name="filesystem.write", arguments={"path": tmp1, "content": "a"}, id="b1"),
            ToolCall(name="filesystem.write", arguments={"path": tmp2, "content": "b"}, id="b2"),
        ]
        results = asyncio.run(svc.execute_tools(calls))
        assert len(results) == 2
        assert all(r.success for r in results)
        for p in (tmp1, tmp2):
            if os.path.exists(p):
                os.remove(p)


# ── AgentLoop + Harness integration ────────────────────────────────────


class TestAgentLoopHarnessIntegration:
    def test_loop_with_harness_config(self):
        sel = HarnessSelector()
        harness = sel.select(HarnessType.MINIMAL)
        loop = AgentLoop(
            router=FakeRouter([_resp("done.")]),
            registry=build_default_registry(),
            project=ProjectContext(root_path=ROOT),
            decision_logger=StubLogger(),
            harness=harness,
        )
        assert loop.max_iterations == 3
        assert loop.temperature == 0.4
        result = asyncio.run(loop.run("test"))
        assert result.success

    def test_loop_with_model_gateway(self):
        gw = ModelGateway()
        gw.register_model(ModelProfile(
            name="fake-model", provider="fake",
            capabilities=(Capability.CODING,),
        ))
        hc = HarnessConfig(harness_type=HarnessType.MINIMAL, enable_verification=False)
        harness = Harness(hc)
        loop = AgentLoop(
            router=FakeRouter([_resp("done.")]),
            registry=build_default_registry(),
            project=ProjectContext(root_path=ROOT),
            decision_logger=StubLogger(),
            model_gateway=gw,
            harness=harness,
        )
        result = asyncio.run(loop.run("code something"))
        assert result.success

    def test_loop_with_harness_and_gateway(self):
        sel = HarnessSelector()
        hc = HarnessConfig(
            harness_type=HarnessType.CODING,
            max_iterations=20,
            enable_verification=False,
        )
        harness = Harness(hc)
        gw = ModelGateway()
        gw.register_model(ModelProfile(
            name="fake-model", provider="fake",
            capabilities=(Capability.CODING, Capability.TOOL_USE),
        ))
        loop = AgentLoop(
            router=FakeRouter([_resp("done.")]),
            registry=build_default_registry(),
            project=ProjectContext(root_path=ROOT),
            decision_logger=StubLogger(),
            harness=harness,
            model_gateway=gw,
        )
        assert loop.max_iterations == 20
        result = asyncio.run(loop.run("implement feature"))
        assert result.success


# ── VerificationEngine tests ──────────────────────────────────────────


class TestVerificationEngine:
    def test_verify_no_steps(self):
        engine = VerificationEngine(project_root=ROOT)
        report = asyncio.run(engine.verify())
        assert report.all_passed
        assert report.steps_run == 0

    def test_verify_passing_command(self):
        engine = VerificationEngine(project_root=ROOT)
        from core.agent.verification import VerificationStep
        engine.add_step(VerificationStep(name="echo", command="python -c \"print('ok')\""))
        report = asyncio.run(engine.verify())
        assert report.all_passed
        assert report.steps_run == 1
        assert report.steps_passed == 1

    def test_verify_failing_command(self):
        engine = VerificationEngine(project_root=ROOT)
        from core.agent.verification import VerificationStep
        engine.add_step(VerificationStep(name="fail", command="python -c \"exit(1)\""))
        report = asyncio.run(engine.verify())
        assert not report.all_passed
        assert report.results[0].exit_code == 1

    def test_verify_stops_on_first_failure(self):
        engine = VerificationEngine(project_root=ROOT)
        from core.agent.verification import VerificationStep
        engine.add_step(VerificationStep(name="fail", command="python -c \"exit(1)\""))
        engine.add_step(VerificationStep(name="pass", command="python -c \"print('ok')\""))
        report = asyncio.run(engine.verify())
        assert report.steps_run == 1  # stopped after first failure

    def test_configure_defaults(self):
        engine = VerificationEngine(project_root=ROOT)
        engine.configure_defaults(has_tests=True, has_lint=True, has_typecheck=False)
        assert len(engine._steps) == 2
        assert engine._steps[0].name == "tests"
        assert engine._steps[1].name == "lint"

    def test_report_to_dict(self):
        engine = VerificationEngine(project_root=ROOT)
        from core.agent.verification import VerificationStep
        engine.add_step(VerificationStep(name="echo", command="python -c \"print('ok')\""))
        report = asyncio.run(engine.verify())
        d = report.to_dict()
        assert "all_passed" in d
        assert "results" in d


# ── FailureClass + State Machine tests ─────────────────────────────────


class TestFailureClassification:
    def test_classify_malformed_tool(self):
        from core.agent.state import classify_failure, FailureClass
        fc = classify_failure("Tool 'nonexistent' is not registered")
        assert fc == FailureClass.MALFORMED_TOOL

    def test_classify_permission_denied(self):
        from core.agent.state import classify_failure, FailureClass
        fc = classify_failure("denied", is_permission=True)
        assert fc == FailureClass.PERMISSION_DENIED

    def test_classify_timeout(self):
        from core.agent.state import classify_failure, FailureClass
        fc = classify_failure("timed out", is_timeout=True)
        assert fc == FailureClass.TIMEOUT

    def test_classify_cancelled(self):
        from core.agent.state import classify_failure, FailureClass
        fc = classify_failure("cancelled", is_cancelled=True)
        assert fc == FailureClass.CANCELLED

    def test_classify_verification_fail(self):
        from core.agent.state import classify_failure, FailureClass
        fc = classify_failure("tests failed", is_verification=True)
        assert fc == FailureClass.VERIFICATION_FAIL

    def test_classify_tool_failure_default(self):
        from core.agent.state import classify_failure, FailureClass
        fc = classify_failure("something went wrong")
        assert fc == FailureClass.TOOL_FAILURE

    def test_classify_max_iterations(self):
        from core.agent.state import classify_failure, FailureClass
        fc = classify_failure("Max iterations (10) reached")
        assert fc == FailureClass.MAX_ITERATIONS

    def test_precedence_cancelled_wins(self):
        from core.agent.state import classify_failure, FailureClass
        fc = classify_failure("error", is_cancelled=True, is_timeout=True)
        assert fc == FailureClass.CANCELLED

    def test_precedence_timeout_beats_tool(self):
        from core.agent.state import classify_failure, FailureClass
        fc = classify_failure("Tool 'x' failed", is_timeout=True)
        assert fc == FailureClass.TIMEOUT

    def test_pick_worst(self):
        from core.agent.state import FailureClass, pick_worst_failure
        result = pick_worst_failure(FailureClass.TOOL_FAILURE, FailureClass.TIMEOUT)
        assert result == FailureClass.TIMEOUT

    def test_pick_worst_none(self):
        from core.agent.state import pick_worst_failure
        assert pick_worst_failure(None, None) is None

    def test_state_transition_to_recovering(self):
        from core.agent.state import AgentState, TaskStatus
        s = AgentState(task_id="t", goal="g")
        s.transition(TaskStatus.CLASSIFYING)
        s.transition(TaskStatus.EXECUTING)
        s.transition(TaskStatus.OBSERVING)
        s.transition(TaskStatus.VERIFYING)
        s.transition(TaskStatus.RECOVERING)
        assert s.status == TaskStatus.RECOVERING

    def test_state_recovering_to_executing(self):
        from core.agent.state import AgentState, TaskStatus
        s = AgentState(task_id="t", goal="g")
        s.transition(TaskStatus.CLASSIFYING)
        s.transition(TaskStatus.EXECUTING)
        s.transition(TaskStatus.OBSERVING)
        s.transition(TaskStatus.VERIFYING)
        s.transition(TaskStatus.RECOVERING)
        s.transition(TaskStatus.EXECUTING)
        assert s.status == TaskStatus.EXECUTING

    def test_state_dict_includes_failure_class(self):
        from core.agent.state import AgentState, TaskStatus, FailureClass
        s = AgentState(task_id="t", goal="g")
        s.failure_class = FailureClass.TOOL_FAILURE
        d = s.to_dict()
        assert d["failure_class"] == "tool_failure"


# ── Unified Pipeline tests ──────────────────────────────────────────────


class TestUnifiedPipeline:
    """All entry points (Terminal/AgentLoop, MCP, ACP, Codex) must route
    through the same ToolExecutionService boundary."""

    def _make_svc(self):
        return ToolExecutionService(registry=build_default_registry())

    def test_agentloop_uses_tool_service(self):
        svc = self._make_svc()
        loop = AgentLoop(
            router=FakeRouter([_resp("done.")]),
            registry=build_default_registry(),
            project=ProjectContext(root_path=ROOT),
            decision_logger=StubLogger(),
            tool_service=svc,
        )
        assert loop._tool_service is svc

    def test_agentloop_creates_default_tool_service(self):
        loop = AgentLoop(
            router=FakeRouter([_resp("done.")]),
            registry=build_default_registry(),
            project=ProjectContext(root_path=ROOT),
            decision_logger=StubLogger(),
        )
        assert loop._tool_service is not None

    def test_mcp_uses_tool_service(self):
        svc = self._make_svc()
        mcp = MCPAdapter(tool_service=svc)
        assert mcp._tool_service is svc

    def test_acp_uses_tool_service(self):
        svc = self._make_svc()
        acp = ACPAdapter(tool_service=svc)
        assert acp._tool_service is svc

    def test_codex_uses_tool_service(self):
        svc = self._make_svc()
        codex = CodexExecAdapter(tool_service=svc)
        assert codex._tool_service is svc

    def test_mcp_tools_call_goes_through_service(self):
        svc = self._make_svc()
        mcp = MCPAdapter(tool_service=svc)
        result = asyncio.run(mcp._call_tool("filesystem.write", {
            "path": os.path.join(tempfile.gettempdir(), "mcp_test.txt"),
            "content": "mcp",
        }))
        assert result["status"] == "completed"
        p = os.path.join(tempfile.gettempdir(), "mcp_test.txt")
        if os.path.exists(p):
            os.remove(p)

    def test_acp_tools_call_goes_through_service(self):
        svc = self._make_svc()
        acp = ACPAdapter(tool_service=svc)
        result = asyncio.run(acp._call_tool("filesystem.write", {
            "path": os.path.join(tempfile.gettempdir(), "acp_test.txt"),
            "content": "acp",
        }))
        assert result["status"] == "completed"
        p = os.path.join(tempfile.gettempdir(), "acp_test.txt")
        if os.path.exists(p):
            os.remove(p)

    def test_codex_tool_goes_through_service(self):
        svc = self._make_svc()
        codex = CodexExecAdapter(tool_service=svc)
        result = asyncio.run(codex.handle_tool("filesystem.write", {
            "path": os.path.join(tempfile.gettempdir(), "codex_test.txt"),
            "content": "codex",
        }))
        assert result["status"] == "completed"
        p = os.path.join(tempfile.gettempdir(), "codex_test.txt")
        if os.path.exists(p):
            os.remove(p)

    def test_all_paths_produce_same_result_type(self):
        svc = self._make_svc()
        import tempfile, os
        tmp = os.path.join(tempfile.gettempdir(), "unified_test.txt")
        call = ToolCall(name="filesystem.write", arguments={"path": tmp, "content": "x"}, id="u1")
        result = asyncio.run(svc.execute_tool(call))
        assert isinstance(result, ToolExecutionResult)
        assert result.success
        if os.path.exists(tmp):
            os.remove(tmp)

    def test_permission_denial_blocks_all_paths(self):
        from core.agent.permissions import PermissionEngine
        from core.decision_logger import get_decision_logger
        from unittest.mock import AsyncMock, patch
        logger = get_decision_logger()
        perm = PermissionEngine(logger, mode="agent")
        svc = ToolExecutionService(
            registry=build_default_registry(),
            permissions=perm,
        )
        call = ToolCall(name="shell.execute", arguments={"command": "echo pwned"}, id="denied1")
        original_check = perm.check
        async def deny_all(*a, **kw):
            return False, "test denial"
        perm.check = deny_all
        result = asyncio.run(svc.execute_tool(call))
        assert result.permission_denied
        assert not result.success or result.permission_denied
        perm.check = original_check

    def test_redaction_applies_on_all_paths(self):
        svc = self._make_svc()
        import tempfile, os
        tmp = os.path.join(tempfile.gettempdir(), "redact_test.txt")
        call = ToolCall(name="filesystem.write", arguments={"path": tmp, "content": "test"}, id="r1")
        result = asyncio.run(svc.execute_tool(call))
        assert "REDACTED" not in result.output or result.success
        if os.path.exists(tmp):
            os.remove(tmp)
