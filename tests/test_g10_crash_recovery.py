"""G10 — crash recovery: WAITING_BROWSER state + bounded relaunch flow.

Hermetic by construction. A fake CDP backend goes "down" (reports CDP
connection-closed on tool calls) mid-task; the loop must park the task in
WAITING_BROWSER, relaunch through BrowserRecovery, resume EXECUTING with a
BROWSER RECOVERED observation, and finish successfully. Exhaustion fails the
task deterministically (TOOL_FAILURE, WAITING_BROWSER -> FAILED). The coding
agent (no recovery provider) keeps its old behavior.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest  # noqa: F401  (fixtures)

from core.agent.loop import AgentLoop
from core.agent.permissions import PermissionEngine
from core.agent.recovery import RecoveryOutcome, RecoveryProvider
from core.agent.tool_service import ToolExecutionService
from core.agent.state import FailureClass, TaskStatus
from core.harness import Harness, HarnessConfig, HarnessType
from core.project import ProjectContext
from orbit.cdp import CDPBackend
from orbit.controller import get_orbit_controller, reset_orbit_controller
from providers.types import LLMResponse, ToolCall
from tools.registry import ToolRegistry

from orbit.recovery import BROWSER_DOWN_MARKERS, BrowserRecovery, is_browser_down_error
from orbit.tools import build_orbit_tools


# ---------------------------------------------------------------------------
# Fake browser transport that can crash and recover
# ---------------------------------------------------------------------------

class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.title = "Fake"
        self.body = "hello from the fake page"
        self.interactives_json = []

    def snapshot(self) -> dict:
        return {"url": self.url, "title": self.title,
                "interactives": self.interactives_json, "links": [],
                "forms": [], "viewport": {"w": 800, "h": 600}, "total": 0}


class FakeConn:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    def call(self, method: str, params: dict | None = None) -> dict:
        params = params or {}
        if method == "Runtime.evaluate":
            return self._evaluate(params.get("expression", ""))
        if method == "Page.navigate":
            self.page.url = params.get("url", self.page.url)
            return {}
        if method == "Target.createTarget":
            return {"targetId": "target-fake-1"}
        if method == "Target.getTargets":
            return {"targetInfos": [{"type": "page", "id": "target-fake-1",
                                     "url": self.page.url, "title": self.page.title}]}
        return {}

    def close(self) -> None:
        pass

    def wait_for_event(self, method_prefix: str, *, timeout: float = 10.0,
                       predicate=None):
        return None

    def consume_events(self, method_prefix: str) -> list:
        return []

    def _evaluate(self, expr: str) -> dict:
        if "document.title" in expr:
            return {"result": {"type": "string", "value": self.page.title}}
        if "location.href" in expr:
            return {"result": {"type": "string", "value": self.page.url}}
        return {"result": {"type": "undefined", "value": None}}


class CrashyBackend(CDPBackend):
    """CDPBackend that can crash; launches succeed once failures are spent."""

    def __init__(self, fail_reads: int = 1) -> None:
        super().__init__(chrome="fake-chrome", headless=True, auto_launch=True)
        self.failures_left = fail_reads
        self.page = FakePage()
        self.launch_count = 0
        self.healthy = False
        self._browser_conn = FakeConn(self.page)

    def launch(self, launch_url: str = "about:blank") -> None:
        self.launch_count += 1
        self.failures_left = max(0, self.failures_left - 1)
        if self.failures_left > 0:
            self.healthy = False
            return
        self.healthy = True
        self._started = True
        self._launched = True
        self._base = "http://127.0.0.1:0"

    def shutdown(self) -> None:
        self.healthy = False
        self._started = False
        self._launched = False
        self._browser_conn = None

    def status(self) -> dict:
        return {
            "backend": "orbit-cdp", "available": self.healthy,
            "launched": self.healthy and self._launched,
            "tabs": 0, "active_tab": None, "sessions": 0,
            "network_policy": "default-deny-private", "owns": {},
        }

    def _ensure_readable(self) -> None:
        if not self.healthy:
            raise RuntimeError("CDP connection closed for Runtime.evaluate")

    def get_dom_snapshot(self, tab_id=None):
        self._ensure_readable()
        return {"interactives": [], "links": [], "forms": [],
                "viewport": {"w": 800, "h": 600}}

    def get_page_text(self, tab_id=None):
        self._ensure_readable()
        return self.page.body

    def get_url(self, tab_id=None):
        self._ensure_readable()
        return self.page.url

    def get_title(self, tab_id=None):
        self._ensure_readable()
        return self.page.title


# ---------------------------------------------------------------------------
# Scripted streaming router + records
# ---------------------------------------------------------------------------

class StreamRouter:
    """Mimics ProviderRouter.complete_stream_typed with pre-scripted steps."""

    preferred_provider = None
    _last_provider = "fake"
    _last_model = "fake-model"

    def __init__(self, steps) -> None:
        self._steps = list(steps)
        self.calls = []

    async def complete_stream_typed(self, messages, **kwargs):
        self.calls.append(list(messages))
        chunk, calls = self._steps.pop(0)
        yield chunk, calls

    async def complete_stream(self, messages, **kwargs):
        yield "streamed"

    async def complete(self, messages, **kwargs):
        return LLMResponse(text="ok", model="fake-model", provider="fake",
                           tokens_used=1, finish_reason="stop")


class StubLogger:
    def begin_task(self, request, source=""):
        return "g10_trace"

    def record(self, *a, **kw):
        pass

    def record_tool(self, *a, **kw):
        pass

    def flush(self):
        pass


class RecordingBus:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event) -> None:
        self.events.append((event.name, dict(event.payload or {})))


async def _noop_chunk(chunk: str) -> None:
    return None


def _orbit_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register_many(build_orbit_tools())
    return reg


def _build_loop(router, backend, *, browser_recovery=None, bus=None) -> AgentLoop:
    logger = StubLogger()
    permissions = PermissionEngine(logger, mode="agent")
    service = ToolExecutionService(
        registry=_orbit_registry(),
        permissions=permissions,
        decision_logger=logger,
        mode="agent",
    )
    harness = Harness(HarnessConfig(
        harness_type=HarnessType.MINIMAL,
        enable_verification=False,
        max_iterations=4,
        temperature=0.3,
        max_tool_calls_per_step=2,
    ))
    return AgentLoop(
        router=router,
        registry=_orbit_registry(),
        project=ProjectContext(root_path=str(Path(__file__).resolve().parents[1])),
        decision_logger=logger,
        harness=harness,
        tool_service=service,
        browser_recovery=browser_recovery,
        event_bus=bus,
    )


def _tool_bodies(messages) -> list[str]:
    return [str(m.get("content") or "") for m in messages
            if isinstance(m, dict) and m.get("role") == "tool" and m.get("content")]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestClassifier:
    def test_marker_sniffing(self):
        for marker in ("CDP connection closed for Page.navigate",
                       "Chromium exited early (code 0)",
                       "browser not launched",
                       "chromium did not expose cdp within start timeout",
                       "failed to connect to 127.0.0.1",
                       "no unbranded Chromium runtime resolvable"):
            assert is_browser_down_error(marker), marker
        for ok in ("navigate failed: net::ERR_NAME_NOT_RESOLVED",
                   "read failed: tab not found",
                   "PERMISSION DENIED: consent required"):
            assert not is_browser_down_error(ok), ok

    def test_markers_are_populated(self):
        assert len(BROWSER_DOWN_MARKERS) >= 4


class TestBrowserRecoveryUnit:
    def test_recovers_after_transient_starts(self):
        backend = CrashyBackend(fail_reads=2)
        rec = BrowserRecovery(
            controller_getter=lambda: SimpleNamespace(backend=backend),
            max_attempts=3,
            backoff=0.0,
        )
        outcome = asyncio.run(rec.recover())
        assert outcome.ok is True
        assert outcome.attempts == 2
        assert backend.launch_count == 2
        assert "relaunched" in outcome.detail

    def test_exhaustion_fails_deterministically(self):
        backend = CrashyBackend(fail_reads=99)
        rec = BrowserRecovery(
            controller_getter=lambda: SimpleNamespace(backend=backend),
            max_attempts=2,
            backoff=0.0,
        )
        outcome = asyncio.run(rec.recover())
        assert outcome.ok is False
        assert outcome.attempts == 2
        assert outcome.detail
        assert backend.launch_count == 2
        assert backend.healthy is False

    def test_protocol_contract(self):
        rec = BrowserRecovery(
            controller_getter=lambda: None, max_attempts=1, backoff=0.0,
        )
        assert isinstance(rec, RecoveryProvider)
        assert isinstance(asyncio.run(rec.recover()), RecoveryOutcome)


class TestLoopRecovery:
    @pytest.fixture
    def browser(self):
        reset_orbit_controller()  # drop any singleton left by earlier suites
        backend = CrashyBackend(fail_reads=1)
        get_orbit_controller(backend=backend)
        yield backend
        reset_orbit_controller()

    def _loop(self, router, backend, *, browser_recovery=None, bus=None):
        return _build_loop(router, backend,
                           browser_recovery=browser_recovery, bus=bus)

    def test_browser_crash_recovers_and_task_completes(self, browser):
        router = StreamRouter([
            (None, [ToolCall(name="orbit.read", arguments={}, id="r1")]),
            ("The page is open. Done.", None),
        ])
        bus = RecordingBus()
        loop = self._loop(
            router, browser,
            browser_recovery=BrowserRecovery(
                controller_getter=get_orbit_controller, max_attempts=3, backoff=0.0,
            ),
            bus=bus,
        )
        result = asyncio.run(loop.run("Read the page", session_id="s10",
                                      on_chunk=_noop_chunk))
        assert result.success is True
        assert result.state.status == TaskStatus.COMPLETED
        statuses = [s for s, _ in result.state._status_history]
        assert TaskStatus.WAITING_BROWSER.value in statuses
        assert browser.launch_count >= 1
        # The next model round saw the structured recovery observation.
        assert any("BROWSER RECOVERED" in b for b in _tool_bodies(router.calls[1]))
        names = [n for n, _ in bus.events]
        assert "browser.waiting" in names
        assert "browser.recovered" in names

    def test_recovery_exhaustion_fails_deterministically(self, browser):
        browser.failures_left = 99
        router = StreamRouter([
            (None, [ToolCall(name="orbit.read", arguments={}, id="r1")]),
        ])
        loop = self._loop(
            router, browser,
            browser_recovery=BrowserRecovery(
                controller_getter=get_orbit_controller, max_attempts=2, backoff=0.0,
            ),
        )
        result = asyncio.run(loop.run("Read the page", session_id="s11",
                                      on_chunk=_noop_chunk))
        assert result.success is False
        assert result.state.status == TaskStatus.FAILED
        assert result.state.failure_class.value == FailureClass.TOOL_FAILURE.value
        assert "browser unavailable" in result.error
        statuses = [s for s, _ in result.state._status_history]
        assert TaskStatus.WAITING_BROWSER.value in statuses
        assert "browser unavailable after 2 recovery" in result.error

    def test_coding_agent_without_provider_is_unchanged(self, browser):
        browser.failures_left = 99
        router = StreamRouter([
            (None, [ToolCall(name="orbit.read", arguments={}, id="r1")]),
        ])
        loop = self._loop(router, browser, browser_recovery=None)
        result = asyncio.run(loop.run("Read the page", session_id="s12",
                                      on_chunk=_noop_chunk))
        assert result.success is False
        statuses = [s for s, _ in result.state._status_history]
        assert TaskStatus.WAITING_BROWSER.value not in statuses