"""G1 foundation tests: DSH (bridge) stability hardening.

Covers the bridge server security foundation: loopback-only, CORS restricted
to chrome-extension origins (never ``*``), optional bearer-token auth, and the
guarantee that the /v1/cdp endpoint is permanently closed (no raw control
path).
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


def _run(host="127.0.0.1", port=0, require_auth=False, auth_token=None, backend_kind="echo"):
    httpd = serve(host=host, port=port, backend_kind=backend_kind,
                  require_auth=require_auth, auth_token=auth_token)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    return httpd, base


def _post(base, path, payload=None, origin=None, token=None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload if payload is not None else {}).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, dict(r.headers), r.read()


def _get(base, path, origin=None):
    headers = {}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(base + path, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        return dict(r.headers), r.read()


def test_cors_never_wildcard_for_extension_origin():
    httpd, base = _run()
    try:
        _, hdrs, _ = _post(base, "/v1/chat", {"text": "hi"}, origin="chrome-extension://abcdefghijklmnopabcdefghijklmnop")
        assert hdrs.get("Access-Control-Allow-Origin") == "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
        assert hdrs.get("Access-Control-Allow-Origin") != "*"
    finally:
        httpd.shutdown(); httpd.server_close()


def test_cors_origin_rejected_for_unknown_origin():
    httpd, base = _run()
    try:
        # A malicious web origin must NOT get a CORS allowance.
        _, hdrs, _ = _post(base, "/v1/chat", {"text": "hi"}, origin="https://evil.example")
        assert hdrs.get("Access-Control-Allow-Origin") not in ("*", "https://evil.example")
    finally:
        httpd.shutdown(); httpd.server_close()


def test_no_origin_gets_no_cors_allowance():
    httpd, base = _run()
    try:
        _, hdrs, _ = _post(base, "/v1/chat", {"text": "hi"})
        assert hdrs.get("Access-Control-Allow-Origin") != "*"
    finally:
        httpd.shutdown(); httpd.server_close()


def test_posts_require_token_when_auth_enabled():
    httpd, base = _run(require_auth=True, auth_token="sekret")
    try:
        # No token -> 401.
        with pytest.raises(urllib.error.HTTPError) as exc:
            _post(base, "/v1/chat", {"text": "hi"})
        assert exc.value.code == 401
    finally:
        httpd.shutdown(); httpd.server_close()


def test_bearer_token_accepted():
    httpd, base = _run(require_auth=True, auth_token="sekret")
    try:
        # Correct token -> happy path (echo backend streams done).
        status, _, body = _post(base, "/v1/chat", {"text": "hi"}, token="sekret")
        assert status == 200
        assert b"done" in body
    finally:
        httpd.shutdown(); httpd.server_close()


def test_generated_token_persisted_on_server():
    httpd, base = _run(require_auth=True)
    try:
        assert httpd.bridge_token
        status, _, body = _post(base, "/v1/chat", {"text": "hi"}, token=httpd.bridge_token)
        assert status == 200
    finally:
        httpd.shutdown(); httpd.server_close()


def test_cdp_endpoint_never_a_control_path():
    """/v1/cdp must remain sealed (no raw CDP delegation), even when the kernel
    engine is attached. Control goes only through JARVIS tools."""
    httpd, base = _run()
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            _post(base, "/v1/cdp", {"method": "Runtime.evaluate"})
        assert exc.value.code == 501
        body = exc.value.read().decode()
        assert "closed" in body
        assert "JARVIS tools" in body
    finally:
        httpd.shutdown(); httpd.server_close()
