"""Hermetic tests for the J-Browser bridge server (stdlib HTTP/SSE).

These tests start the bridge in-process on an ephemeral port and exercise the
SSE chat protocol, status, error handling, and the agent/cdp seams. They never
launch a browser or Playwright driver, so they are safe to run in the default
suite.
"""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BRIDGE_DIR = Path(__file__).resolve().parent.parent / "jbrowser-bridge"
sys.path.insert(0, str(BRIDGE_DIR))

from server import serve  # noqa: E402


@pytest.fixture()
def bridge():
    httpd = serve(host="127.0.0.1", port=0, backend_kind="echo")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base
    finally:
        httpd.shutdown()
        httpd.server_close()


def _post(base, path, payload) -> bytes:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


def _get(base, path) -> bytes:
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return r.read()


def _chat_events(base, payload):
    req = urllib.request.Request(
        base + "/v1/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    events = []
    deltas = []
    kinds = set()
    with urllib.request.urlopen(req, timeout=10) as r:
        for raw_line in r:
            line = raw_line.decode().strip()
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            events.append(event)
            kinds.add(event["type"])
            if event["type"] == "delta":
                deltas.append(event["text"])
            if event["type"] in ("done", "error"):
                break
    return kinds, "".join(deltas)


def test_status(bridge):
    data = json.loads(_get(bridge, "/status"))
    assert data["ok"] is True
    assert data["kernel"] == "offline"
    assert data["backend"] == "echo"


def test_chat_stream_terminates_with_done(bridge):
    kinds, _ = _chat_events(bridge, {
        "session_id": "t1",
        "messages": [{"role": "user", "content": "hi"}],
        "page": {},
    })
    assert {"start", "delta", "done"} <= kinds


def test_chat_includes_page_context(bridge):
    _, joined = _chat_events(bridge, {
        "session_id": "t2",
        "messages": [{"role": "user", "content": "summarize"}],
        "page": {"title": "Acme", "url": "https://acme.example", "selection": "needle"},
    })
    assert "Acme" in joined
    assert "acme.example" in joined
    assert "needle" in joined


def test_chat_text_only_message(bridge):
    _, joined = _chat_events(bridge, {
        "session_id": "t3",
        "messages": [],
        "text": "plain text prompt",
        "page": {},
    })
    assert "plain text prompt" in joined


def test_invalid_json_returns_400(bridge):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(
            urllib.request.Request(
                bridge + "/v1/chat",
                data=b"{not json",
                headers={"Content-Type": "application/json"},
            ),
            timeout=10,
        )
    assert exc.value.code == 400


@pytest.mark.parametrize("ep", ["/v1/agent", "/v1/cdp"])
def test_seams_not_implemented(bridge, ep):
    req = urllib.request.Request(
        bridge + ep,
        data=json.dumps({}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10).read()
    assert exc.value.code == 501
