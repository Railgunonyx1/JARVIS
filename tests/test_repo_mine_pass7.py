"""Tests for repo-mine pass-7 tools: rclone remote transfers, bruno API collections.

Hermetic: rclone is never invoked (availability faked), HTTP runs against
local tmp fixtures only via parser unit tests, and the shared client is
monkeypatched for api.run so no real network egress happens.
"""

from __future__ import annotations

import json
import sys
import urllib.request
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_default_registry  # noqa: E402


def test_pass7_tools_registered():
    registry = build_default_registry()
    for name in ("remote.status", "remote.transfer", "api.parse", "api.run"):
        tool = registry.get(name)
        assert tool is not None, f"{name} missing"
        assert tool.handler is not None


# ------------------------------------------------------------------ fixtures


@pytest.fixture()
def api_root(tmp_path, monkeypatch):
    """Project root with a two-request .bru collection."""
    (tmp_path / "apis").mkdir()
    (tmp_path / "apis" / "get_user.bru").write_text(
        "meta {\n  name: get-user\n}\n\n"
        "get {\n  url: https://api.example.com/users/{{user_id}}\n}\n\n"
        "headers {\n  accept: application/json\n}\n\n"
        "query {\n  verbose: true\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "apis" / "create_user.bru").write_text(
        "post {\n  url: https://api.example.com/users\n}\n\n"
        "headers {\n  content-type: application/json\n  authorization: Bearer {{API_TOKEN}}\n}\n\n"
        "body:json {\n  {\"name\": \"Ada\"}\n}\n",
        encoding="utf-8",
    )
    from core.project import ProjectContext

    fake = type("C", (), {"root_path": tmp_path})
    monkeypatch.setattr(ProjectContext, "discover", staticmethod(lambda cwd=None: fake()))
    return tmp_path


# --------------------------------------------------------------------- .bru parser


def test_parse_bru_get_request(api_root):
    from tools.api_collections import _parse_bru

    req = _parse_bru((api_root / "apis" / "get_user.bru").read_text(encoding="utf-8"))
    assert req["method"] == "GET"
    assert req["url"] == "https://api.example.com/users/{{user_id}}"
    assert req["headers"]["accept"] == "application/json"
    assert req["query"]["verbose"] == "true"
    assert req["meta"]["name"] == "get-user"


def test_parse_bru_post_with_body(api_root):
    from tools.api_collections import _parse_bru

    req = _parse_bru((api_root / "apis" / "create_user.bru").read_text(encoding="utf-8"))
    assert req["method"] == "POST"
    assert req["headers"]["authorization"] == "Bearer {{API_TOKEN}}"
    assert '"name": "Ada"' in req["body_json"]


# ------------------------------------------------------------------- api.run


class _StubResponse:
    def __init__(self, status=200, content=b"ok"):
        self.status_code = status
        self.content = content


def test_api_run_collection_with_stub_client(api_root, monkeypatch):
    """Stub the shared httpx client; assert both requests fire and are reported."""
    from tools import api_collections as ac

    calls = []

    class StubClient:
        def request(self, method, url, **kw):
            calls.append({"method": method, "url": url, "headers": kw.get("headers"),
                          "params": kw.get("params"), "content": kw.get("content")})
            return _StubResponse(200 if "get_user" not in str(kw) else 200)

    import core.http_pool as hp
    monkeypatch.setattr(hp, "get_client", lambda: StubClient())

    res = ac.api_run({"path": "apis", "vars": {"user_id": "42"}, "allow_private": False})
    assert res.success, res.output
    assert res.metadata["total"] == 2 and res.metadata["ok"] == 2
    assert len(calls) == 2
    get_call = next(c for c in calls if c["method"] == "GET")
    assert get_call["url"] == "https://api.example.com/users/42"
    assert get_call["params"] == {"verbose": "true"}
    post_call = next(c for c in calls if c["method"] == "POST")
    assert post_call["content"] == b'{"name": "Ada"}'


def test_api_run_env_secret_interpolates_but_not_in_output(api_root, monkeypatch):
    from tools import api_collections as ac

    monkeypatch.setenv("API_TOKEN", "super-secret-value-123")
    seen = {}

    class StubClient:
        def request(self, method, url, **kw):
            seen.update(kw.get("headers") or {})
            return _StubResponse(200)

    import core.http_pool as hp
    monkeypatch.setattr(hp, "get_client", lambda: StubClient())

    res = ac.api_run({"path": "apis/create_user.bru"})
    assert res.success
    assert seen.get("authorization") == "Bearer super-secret-value-123"
    assert "super-secret-value-123" not in res.output  # secret never echoes


def test_api_run_blocks_private_targets(api_root, monkeypatch):
    from tools import api_collections as ac

    (api_root / "apis" / "internal.bru").write_text(
        "get {\n  url: http://192.168.1.1/admin\n}\n", encoding="utf-8"
    )
    fired = []

    class StubClient:
        def request(self, *a, **kw):
            fired.append(True)
            return _StubResponse(200)

    import core.http_pool as hp
    monkeypatch.setattr(hp, "get_client", lambda: StubClient())

    res = ac.api_run({"path": "apis/internal.bru"})
    assert "blocked" in res.output and not fired


def test_api_run_allow_private_override(api_root, monkeypatch):
    from tools import api_collections as ac

    (api_root / "apis" / "local.bru").write_text(
        "get {\n  url: http://127.0.0.1:9999/health\n}\n", encoding="utf-8"
    )
    fired = []

    class StubClient:
        def request(self, *a, **kw):
            fired.append(kw)
            return _StubResponse(200)

    import core.http_pool as hp
    monkeypatch.setattr(hp, "get_client", lambda: StubClient())

    res = ac.api_run({"path": "apis/local.bru", "allow_private": True})
    assert res.success and fired


# ------------------------------------------------------------- remote.status


def test_remote_status_reports_missing_rclone(monkeypatch):
    from tools import remote_sync as rs

    monkeypatch.setattr(rs, "_rclone_path", lambda: None)
    res = rs.remote_status({})
    assert not res.success
    assert "winget install Rclone.Rclone" in res.error


def test_remote_status_lists_remotes(monkeypatch):
    from tools import remote_sync as rs

    class R:
        def __init__(self, out):
            self.stdout, self.stderr, self.exit_code, self.success = out, "", 0, True
            self.blocked = False

    calls = []

    def fake_execute(req):
        calls.append(req.args[0] if req.args else "")
        if req.args[:1] == ["version"]:
            return R("rclone v1.67.0\n- os/version: microsoft_windows_11")
        if req.args[:1] == ["listremotes"]:
            return R("gdrive:\ns3-backup:\n")
        return R("")

    from security import executor as ex
    monkeypatch.setattr(ex, "get_secure_executor", lambda: type("E", (), {"execute": staticmethod(fake_execute)})())

    monkeypatch.setattr(rs, "_rclone_path", lambda: "C:/tools/rclone.exe")
    res = rs.remote_status({})
    assert res.success
    assert res.metadata["remotes"] == ["gdrive", "s3-backup"]
    assert "v1.67.0" in res.output


# ------------------------------------------------------------ remote.transfer


def test_remote_transfer_sync_requires_confirmation(monkeypatch):
    from tools import remote_sync as rs

    monkeypatch.setattr(rs, "_rclone_path", lambda: "C:/tools/rclone.exe")
    res = rs.remote_transfer({"mode": "sync", "source": "gdrive:x", "dest": "D:/x"})
    assert not res.success
    assert "dry_run" in res.error and "confirm" in res.error


def test_remote_transfer_dry_run_then_confirm(monkeypatch):
    from tools import remote_sync as rs

    sent = []

    class R:
        def __init__(self):
            self.stdout, self.stderr, self.exit_code, self.success = "Transferred: 5 / 5", "", 0, True
            self.blocked = False

    def fake_execute(req):
        sent.append(list(req.args))
        return R()

    from security import executor as ex
    monkeypatch.setattr(ex, "get_secure_executor", lambda: type("E", (), {"execute": staticmethod(fake_execute)})())
    monkeypatch.setattr(rs, "_rclone_path", lambda: "C:/tools/rclone.exe")

    dry = rs.remote_transfer({"mode": "sync", "source": "gdrive:x", "dest": "D:/x", "dry_run": True})
    assert dry.success and sent[0][0] == "sync" and "--dry-run" in sent[0]

    confirm = rs.remote_transfer({"mode": "sync", "source": "gdrive:x", "dest": "D:/x", "confirm": True})
    assert confirm.success and "--dry-run" not in sent[1]


def test_remote_transfer_missing_rclone(monkeypatch):
    from tools import remote_sync as rs

    monkeypatch.setattr(rs, "_rclone_path", lambda: None)
    res = rs.remote_transfer({"mode": "copy", "source": "a", "dest": "b"})
    assert not res.success
    assert "not installed" in res.error
