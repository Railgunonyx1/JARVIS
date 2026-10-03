"""Tests for pass-12 tools: weather.get, mail.digest, snippet.store.

Hermetic: open-meteo responses are canned via a patched pooled client, IMAP
is a fake connection object (no sockets), and snippet state lives in tmp_path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.http_pool  # noqa: E402
from tools import build_default_registry  # noqa: E402
from tools import mail_digest as md  # noqa: E402
from tools import snippets as sn  # noqa: E402
from tools import weather_get as wg  # noqa: E402


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(
        __import__("core.project", fromlist=["ProjectContext"]).ProjectContext,
        "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    return tmp_path


@pytest.fixture()
def http(monkeypatch):
    responses: dict[str, str] = {}

    def fake_fetch(url, timeout=10, **kwargs):
        for pattern, body in responses.items():
            if pattern in url:
                return body
        raise OSError(f"no canned response for {url}")

    monkeypatch.setattr(core.http_pool, "fetch", fake_fetch)
    return responses


# ---------------------------------------------------------------- registry

def test_pass12_tools_registered():
    registry = build_default_registry()
    for name in ("weather.get", "mail.digest", "snippet.store"):
        tool = registry.get(name)
        assert tool is not None, f"{name} missing"
        assert tool.handler is not None


# -------------------------------------------------------------- weather.get

GEO = json.dumps({"results": [{"name": "Berlin", "country": "Germany", "latitude": 52.52, "longitude": 13.41}]})
FORECAST = json.dumps({
    "current": {"temperature_2m": 18.3, "apparent_temperature": 17.1,
                "relative_humidity_2m": 62, "weather_code": 2, "wind_speed_10m": 12.4},
    "daily": {
        "time": ["2026-09-22", "2026-09-23"],
        "temperature_2m_max": [24.1, 21.0],
        "temperature_2m_min": [13.5, 12.2],
        "precipitation_probability_max": [10, 65],
        "weather_code": [2, 63],
    },
})


def test_weather_by_place_name(workspace, http):
    http["geocoding-api.open-meteo.com"] = GEO
    http["api.open-meteo.com"] = FORECAST
    res = wg.weather_get({"location": "Berlin"})
    assert res.success, res.error
    assert "Berlin, Germany" in res.output
    assert "Partly cloudy" in res.output          # WMO code 2 translated
    assert "Moderate rain" in res.output          # WMO code 63 translated
    assert "rain 65%" in res.output
    assert "feels 17.1" in res.output


def test_weather_by_coordinates(workspace, http):
    http["api.open-meteo.com"] = FORECAST
    res = wg.weather_get({"lat": 52.52, "lon": 13.41, "label": "Home"})
    assert res.success and "Home" in res.output


def test_weather_unknown_place(workspace, http):
    http["geocoding-api.open-meteo.com"] = json.dumps({"results": []})
    res = wg.weather_get({"location": "Nowheresville"})
    assert res.success is False and "geocode" in res.error


def test_weather_requires_location(workspace, http):
    assert wg.weather_get({}).success is False


def test_weather_service_down(workspace, http):
    http["geocoding-api.open-meteo.com"] = GEO
    res = wg.weather_get({"location": "Berlin"})
    assert res.success is False and "unreachable" in res.error


# -------------------------------------------------------------- mail.digest

class FakeIMAPConn:
    """Just enough IMAP4_SSL surface for mail_digest."""

    last_instance = None

    def __init__(self, host, port):
        self.host = host
        self.logged_in = False
        self.readonly = None
        FakeIMAPConn.last_instance = self

    def login(self, user, password):
        self.logged_in = True

    def select(self, folder, readonly=False):
        self.readonly = readonly
        return ("OK", [b""])

    def search(self, charset, criteria):
        assert "UNSEEN" in criteria and "SINCE" in criteria
        return ("OK", [b"1 2 3"])

    def fetch(self, mid, spec):
        assert "HEADER.FIELDS" in spec  # headers only, never bodies
        raw = (
            f"From: Ada Lovelace <ada@analytical.example>\r\n"
            f"Subject: =?utf-8?q?Encod=C3=A9d_subject?=\r\n"
            f"Date: Tue, 22 Sep 2026 10:00:00 +0000\r\n"
        ).encode()
        return ("OK", [(b"1", raw)])

    def logout(self):
        pass


@pytest.fixture()
def fake_imap(monkeypatch):
    monkeypatch.setattr(md, "_imap_class", lambda: FakeIMAPConn)
    env = {"JARVIS_IMAP_HOST": "imap.test", "JARVIS_IMAP_USER": "me", "JARVIS_IMAP_PASSWORD": "app-pw"}
    monkeypatch.setenv("JARVIS_IMAP_HOST", env["JARVIS_IMAP_HOST"])
    monkeypatch.setenv("JARVIS_IMAP_USER", env["JARVIS_IMAP_USER"])
    monkeypatch.setenv("JARVIS_IMAP_PASSWORD", env["JARVIS_IMAP_PASSWORD"])
    return FakeIMAPConn


def test_mail_digest_disabled_by_default(workspace, monkeypatch):
    monkeypatch.delenv("JARVIS_IMAP_HOST", raising=False)
    monkeypatch.delenv("JARVIS_IMAP_USER", raising=False)
    monkeypatch.delenv("JARVIS_IMAP_PASSWORD", raising=False)
    res = md.mail_digest({})
    assert res.success is False and "not configured" in res.error


def test_mail_digest_headers_only_and_readonly(workspace, fake_imap):
    res = md.mail_digest({"days": 3})
    assert res.success, res.error
    assert "Encodéd subject" in res.output          # RFC 2047 decoded
    assert "analytical.example (3)" in res.output   # senders grouped by domain
    conn = fake_imap.last_instance
    assert conn.readonly is True                    # EXAMINE — never marks read


# ------------------------------------------------------------- snippet.store

def test_snippet_add_list_remove(workspace):
    assert sn.snippet_add({"trigger": "sig", "text": "— Aayan, JARVIS Labs"}).success
    listed = sn.snippet_list({})
    assert ":sig" in listed.output and "JARVIS Labs" in listed.output
    assert sn.snippet_add({"trigger": "sig", "text": "updated body"}).success  # update ok
    assert sn.snippet_remove({"trigger": "sig"}).success
    assert sn.snippet_remove({"trigger": "sig"}).success is False


def test_snippet_validation(workspace):
    assert sn.snippet_add({"trigger": "", "text": "x"}).success is False
    assert sn.snippet_add({"trigger": "Bad Trigger!", "text": "x"}).success is False
    assert sn.snippet_add({"trigger": "ok", "text": "  "}).success is False
    assert sn.snippet_add({"trigger": "x" * 40, "text": "x"}).success is False


def test_snippet_expand_tokens(workspace):
    sn.snippet_add({"trigger": "email", "text": "me@example.com"})
    sn.snippet_add({"trigger": "sig", "text": "Aayan"})
    new_text, expanded = sn.expand_text("contact: :email thanks, :sig")
    assert new_text == "contact: me@example.com thanks, Aayan"
    assert expanded == ["email", "sig"]


def test_snippet_expand_leaves_unknown_tokens(workspace):
    sn.snippet_add({"trigger": "known", "text": "yes"})
    new_text, expanded = sn.expand_text("time is 10:30 and :unknown stays")
    assert new_text == "time is 10:30 and :unknown stays"  # 10:30 untouched, unknown untouched
    assert expanded == []


def test_browser_type_expands_snippets(workspace, monkeypatch):
    """The espanso integration: browser.type expands :triggers before typing."""
    from tools import browser as bt

    sn.snippet_add({"trigger": "handle", "text": "@aayan"})

    captured = {}

    class FakeController:
        def type_selector(self, selector, text):
            captured["text"] = text

    monkeypatch.setattr(bt, "_controller", lambda: FakeController())
    res = bt.browser_type({"selector": "#search", "text": "ping :handle"})
    assert res.success
    assert captured["text"] == "ping @aayan"        # expanded before typing
