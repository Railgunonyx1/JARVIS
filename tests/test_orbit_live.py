"""JARVIS Orbit live CDP smoke tests (OPT-IN; skipped by default).

Prove the real G3-G4 chain against unbranded Chromium via CDP:

    OrbitRuntime -> ToolExecutionService -> orbit.navigate -> BrowserController
                 -> CDPBackend -> CDP -> Chromium -> read back

Runs only when ``JARVIS_RUN_BROWSER_LIVE=1`` and requires a resolvable unbranded
Chromium runtime (J_BROWSER_CHROMIUM_PATH or a Playwright build). The test
serves a tiny local page, allowlists its loopback origin (the default network
policy stays default-deny for everything else), and verifies navigation +
read-back over the real CDP path. No internet required; hermetic elsewhere.
"""

from __future__ import annotations

import functools
import http.server
import os
import socketserver
import threading
from pathlib import Path

import pytest

from orbit.cdp import CDPBackend, _find_chromium
from orbit.runtime import OrbitRuntime
from orbit.tools import build_orbit_tools

_RUN_LIVE = os.environ.get("JARVIS_RUN_BROWSER_LIVE", "0") == "1"

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        not _RUN_LIVE,
        reason="set JARVIS_RUN_BROWSER_LIVE=1 to run live browser integration tests",
    ),
]

_HTML = b"""<!doctype html><html><head><title>Orbit Live</title></head>
<body><h1>orbit cdp works</h1><a href="https://example.com">ex</a>
<input type="text" placeholder="search"></body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(_HTML)))
        self.end_headers()
        self.wfile.write(_HTML)

    def log_message(self, *args):  # noqa: D401
        pass


@functools.lru_cache(maxsize=1)
def _chrome_path() -> str | None:
    found = _find_chromium()
    return str(found) if found else None


@pytest.fixture(scope="module")
def local_site():
    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as srv:
        srv.daemon_threads = True
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        yield f"127.0.0.1:{srv.server_address[1]}"
        srv.shutdown()


@pytest.fixture(scope="module")
def runtime(local_site):
    chrome = _chrome_path()
    if chrome is None:
        pytest.skip("no unbranded Chromium resolvable (J_BROWSER_CHROMIUM_PATH "
                    "or playwright install chromium)")
    from orbit.cdp import BrowserNetworkPolicy
    backend = CDPBackend(
        chrome=chrome,
        headless=True,
        profile_dir=Path("config/browser_profiles/orbit_live_test"),
        network_policy=BrowserNetworkPolicy(allowlist={local_site}),
        auto_launch=True,
        start_timeout=30.0,
    )
    runtime = OrbitRuntime()

    # Bind the runtime to this backend so nothing touches the default process.
    from orbit import tools as orbit_tools
    from jbrowser.controller import BrowserController
    backend.launch()
    ctl = BrowserController(backend=backend, profile_root=Path("."))
    orbit_tools.get_orbit_controller = lambda *a, **k: ctl
    yield runtime, ctl, local_site
    ctl.shutdown()


class TestLiveCDPChain:
    def test_navigate_and_read_back(self, runtime):
        orbit_runtime, ctl, site = runtime
        url = f"http://{site}/"
        placeholder = runtime[0]

        async def run():
            payload = await placeholder.handle_command(
                {"action": "browse", "tool": "orbit.navigate",
                 "arguments": {"url": url}},
                trace_id="live-1", session_id="live-sess",
            )
            read = await placeholder.handle_command(
                {"tool": "orbit.read"}, trace_id="live-1", session_id="live-sess")
            return payload, read

        import asyncio
        payload, read = asyncio.run(run())
        assert payload["success"] is True
        assert payload["readback"]["page"]["title"] == "Orbit Live"
        assert "orbit cdp works" in payload["readback"]["page"]["text_preview"]
        assert read["success"] is True
        assert "orbit cdp works" in read["output"]
        # Interactive el[0] should be the link; handle exists.
        assert "[el0]" in read["output"]

    def test_ownership_and_tabs_visible(self, runtime):
        _, ctl, _ = runtime
        tabs = ctl.list_tabs()
        assert tabs, "expected the wired tab to be visible to the controller"
        tab = tabs[0]
        assert tab["tab_id"].startswith("tab_")
        assert "localhost" not in tab["url"]
        assert tab["title"] == "Orbit Live"

    def test_default_policy_still_denies_loopback(self, runtime):
        backend = runtime[1].backend
        from jbrowser.network import NetworkPolicyError
        with pytest.raises(NetworkPolicyError):
            backend._network.validate("http://127.0.0.1:9999/secret")