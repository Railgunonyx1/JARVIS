"""Browser request-boundary network enforcement (audit Phase 1, issue 3).

A pre-navigation hostname/DNS check is not enough: redirects and subresources
introduce new destinations. These tests prove the Playwright backend validates
every intercepted HTTP(S) request and aborts denied ones *before* they leave the
browser. Hermetic — no Playwright driver, no external DNS.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jbrowser.backend.playwright import PlaywrightBackend  # noqa: E402
from jbrowser.network import NetworkPolicyError  # noqa: E402


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeRoute:
    def __init__(self, url: str) -> None:
        self.request = _FakeRequest(url)
        self.aborted = False
        self.fell_back = False
        self.continued = False

    def abort(self, *args, **kwargs) -> None:
        self.aborted = True

    def fallback(self) -> None:
        self.fell_back = True

    def continue_(self) -> None:
        self.continued = True


@pytest.fixture()
def backend() -> PlaywrightBackend:
    return PlaywrightBackend(headless=True)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",
    "http://localhost:8170/",
    "http://10.0.0.5/internal",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://metadata.google.internal/",
    "http://[::ffff:127.0.0.1]/",   # IPv4-mapped loopback
    "http://example.com:99999/",    # malformed port -> policy denial
])
def test_denied_requests_are_aborted(backend, url):
    route = _FakeRoute(url)
    backend._network_route_handler(route)
    assert route.aborted is True
    assert route.fell_back is False


@pytest.mark.parametrize("url", [
    "https://93.184.216.34/",          # globally routable IP literal
    "data:text/html,hi",
    "blob:https://example.com/uuid",
    "about:blank",
    "devtools://devtools/bundled/x.js",
])
def test_allowed_requests_fall_through(backend, url):
    route = _FakeRoute(url)
    backend._network_route_handler(route)
    assert route.aborted is False
    assert route.fell_back is True


def test_enforce_request_raises_on_private_and_allows_public(backend):
    with pytest.raises(NetworkPolicyError):
        backend._enforce_request("http://10.0.0.5/")
    # Public IP literal: no external DNS required.
    backend._enforce_request("https://93.184.216.34/")
    # WS(S) is validated under its HTTP(S) form (literals only: hermetic).
    with pytest.raises(NetworkPolicyError):
        backend._enforce_request("ws://127.0.0.1:9222/devtools")
    backend._enforce_request("wss://93.184.216.34/socket")
    # Non-HTTP schemes are not egress.
    backend._enforce_request("data:text/plain,x")


def test_handler_aborts_on_unexpected_policy_error(backend, monkeypatch):
    class _Boom:
        def validate(self, url):
            raise RuntimeError("unexpected")

    monkeypatch.setattr(backend, "_network", _Boom())
    route = _FakeRoute("https://93.184.216.34/")
    backend._network_route_handler(route)
    assert route.aborted is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
