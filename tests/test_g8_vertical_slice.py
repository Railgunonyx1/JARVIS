"""G8 — end-to-end vertical slice: DSH-style task -> bridge /v1/agent ->
AgentEngine -> AgentLoop -> ToolExecutionService -> orbit.navigate ->
BrowserController -> CDP (fake transport).

Hermetic by construction: the model is a scripted streaming router and the
browser is the in-memory FakeConn/FakePage surface, so no provider key and no
Chromium are ever needed. The path exercised is identical to production
except for those two seams.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import types
from pathlib import Path

BRIDGE_DIR = Path(__file__).resolve().parent.parent / "jbrowser-bridge"
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

import pytest  # noqa: E402

from core.agent.loop import AgentLoop  # noqa: E402
from core.agent.permissions import PermissionEngine  # noqa: E402
from core.agent.tool_service import ToolExecutionService  # noqa: E402
from core.decision_logger import get_decision_logger  # noqa: E402
from core.harness import Harness, HarnessConfig, HarnessType  # noqa: E402
from core.project import ProjectContext  # noqa: E402
from orbit.cdp import CDPBackend  # noqa: E402
from orbit.controller import get_orbit_controller, reset_orbit_controller  # noqa: E402
from providers.types import LLMResponse, ToolCall  # noqa: E402
from tools.registry import ToolRegistry  # noqa: E402

from agent import AgentEngine  # noqa: E402
from backend import KernelBackend  # noqa: E402
from orbit.tools import build_orbit_tools  # noqa: E402
from server import serve  # noqa: E402

TARGET = "https://example.com/"


# ---------------------------------------------------------------------------
# Fake CDP transport (in-memory browser)
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


def _browser_backend(page: FakePage) -> CDPBackend:
    conn = FakeConn(page)
    backend = CDPBackend(chrome="fake-chrome", headless=True, auto_launch=True)

    def fake_launch(self, launch_url="about:blank"):
        self._started = True
        self._launched = True
        self._base = "http://127.0.0.1:0"

    def fake_page_conn(self, tab_id: str):
        return conn

    backend.launch = types.MethodType(fake_launch, backend)
    backend._page_conn = types.MethodType(fake_page_conn, backend)
    backend._browser_conn = conn
    return backend


# ---------------------------------------------------------------------------
# Scripted streaming router (one tool turn, then a final answer)
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
        return "g8_trace"

    def record(self, *a, **kw):
        pass

    def record_tool(self, *a, **kw):
        pass

    def flush(self):
        pass


def _build_loop(router: StreamRouter, registry: ToolRegistry) -> AgentLoop:
    logger = StubLogger()
    permissions = PermissionEngine(logger, mode="agent")
    service = ToolExecutionService(
        registry=registry,
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
        registry=registry,
        project=ProjectContext(root_path=str(Path(__file__).resolve().parents[1])),
        decision_logger=logger,
        harness=harness,
        tool_service=service,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def orbit_browser():
    page = FakePage()
    get_orbit_controller(backend=_browser_backend(page))
    yield page
    reset_orbit_controller()


def _read_sse(resp):
    body = resp.read().decode("utf-8")
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def _post_agent(port, task, session="s9"):
    import urllib.request
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/agent",
        data=json.dumps({"task": task, "session_id": session}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, _read_sse(resp)


class TestAgentEngine:
    def test_task_goal_extraction_and_streaming(self):
        router = StreamRouter([
            (None, [ToolCall(name="orbit.navigate",
                            arguments={"url": TARGET}, id="t1")]),
            ("The page was opened successfully.", None),
        ])
        engine = AgentEngine(loop_factory=lambda: _build_loop(router, _orbit_registry()))
        events = []
        text = engine.stream_chat(
            "s1",
            [{"role": "user", "content": "Browse https://example.com and report"}],
            {"title": "Start", "url": "about:blank"},
            events.append,
        )
        kinds = [e["type"] for e in events]
        assert kinds[0] == "start" and kinds[-1] == "done"
        assert any(e["type"] == "delta" for e in events)
        assert events[-1]["success"] is True
        assert "opened successfully" in text

    def test_failed_task_emits_error(self):
        router = StreamRouter([
            (None, [ToolCall(name="orbit.navigate",
                            arguments={"url": TARGET}, id="t1")]),
            ("", None),
        ])
        engine = AgentEngine(loop_factory=lambda: _build_loop(router, _orbit_registry()))
        events = []
        text = engine.stream_chat("s2", [{"role": "user", "content": "go"}], None,
                                  events.append)
        assert text == ""
        assert events[-1]["type"] == "error"


def _orbit_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register_many(build_orbit_tools())
    return reg


class TestVerticalSlice:
    def test_task_streams_and_reaches_cdp(self, orbit_browser):
        router = StreamRouter([
            (None, [ToolCall(name="orbit.navigate",
                            arguments={"url": TARGET}, id="t1")]),
            ("Done — example.com is open.", None),
        ])
        engine = AgentEngine(
            loop_factory=lambda: _build_loop(router, _orbit_registry()),
        )
        httpd = serve(port=0, backend_kind="kernel", engine=engine)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            status, events = _post_agent(httpd.server_address[1], TASK)
        finally:
            httpd.shutdown()
            httpd.server_close()
        assert status == 200
        assert [e["type"] for e in events][-1] == "done"
        assert events[-1]["success"] is True
        # The fake CDP page actually navigated: agent -> tool -> controller -> CDP.
        assert orbit_browser.url == TARGET

    def test_agent_endpoint_fails_closed_without_engine(self):
        httpd = serve(port=0, backend_kind="echo")
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            import urllib.request
            req = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_address[1]}/v1/agent",
                data=b'{"task":"x"}',
                headers={"Content-Type": "application/json"},
            )
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(req, timeout=10)
            assert exc.value.code == 501
        finally:
            httpd.shutdown()
            httpd.server_close()


TASK = "Browse https://example.com and tell me what you find on the page."


class TestKernelEngineSeam:
    def test_agent_engine_routes_through_kernel_backend(self):
        loop = KernelBackend(engine=AgentEngine(loop_factory=lambda: _build_loop(
            StreamRouter([("fine", None)]), _orbit_registry())))
        events = []
        assert loop.status()["kernel"] == "online"
        assert loop.status()["engine"] == "agent_loop"