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
        call = ToolCall(name="bash", arguments={"command": "echo ok"}, id="t2")
        result = asyncio.run(svc.execute_tool(call))
        assert result.success
        assert "ok" in result.output

    def test_execute_appends_to_messages(self):
        svc = ToolExecutionService(registry=build_default_registry())
        call = ToolCall(name="bash", arguments={"command": "echo hi"}, id="t3")
        msgs = []
        asyncio.run(svc.execute_tool(call, append_to_messages=msgs))
        assert len(msgs) == 1
        assert msgs[0]["role"] == "tool"
        assert "hi" in msgs[0]["content"]

    def test_execute_tools_batch(self):
        svc = ToolExecutionService(registry=build_default_registry())
        calls = [
            ToolCall(name="bash", arguments={"command": "echo a"}, id="b1"),
            ToolCall(name="bash", arguments={"command": "echo b"}, id="b2"),
        ]
        results = asyncio.run(svc.execute_tools(calls))
        assert len(results) == 2
        assert all(r.success for r in results)


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
        loop = AgentLoop(
            router=FakeRouter([_resp("done.")]),
            registry=build_default_registry(),
            project=ProjectContext(root_path=ROOT),
            decision_logger=StubLogger(),
            model_gateway=gw,
        )
        result = asyncio.run(loop.run("code something"))
        assert result.success

    def test_loop_with_harness_and_gateway(self):
        sel = HarnessSelector()
        harness = sel.select(HarnessType.CODING)
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
