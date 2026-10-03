"""BrowserNetworkPolicy unit tests — deny-by-default egress for the agent browser."""

from __future__ import annotations

import pytest

from jbrowser.network import BrowserNetworkPolicy, NetworkPolicyError


class TestAllowPublic:
    def test_public_https_allowed(self):
        p = BrowserNetworkPolicy.default()
        assert p.validate("https://example.com/x") == "https://example.com/x"

    def test_public_http_allowed_by_default(self):
        p = BrowserNetworkPolicy.default()
        assert p.validate("http://example.com/x") == "http://example.com/x"

    def test_public_http_denied_when_disabled(self):
        p = BrowserNetworkPolicy(allow_public_http=False)
        with pytest.raises(NetworkPolicyError):
            p.validate("http://example.com/x")


class TestDenyPrivate:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:8000/admin",
        "http://localhost:8080",
        "http://localhost",
        "http://10.0.0.5:3000",
        "http://192.168.1.1",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]:5000",
        "http://0.0.0.0:9000",
    ])
    def test_private_loopback_linklocal_denied(self, url):
        p = BrowserNetworkPolicy.default()
        with pytest.raises(NetworkPolicyError):
            p.validate(url)

    def test_allow_private_flag_permits(self):
        p = BrowserNetworkPolicy(allow_private=True)
        assert p.validate("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
        assert p.validate("http://localhost:3000") == "http://localhost:3000"

    def test_allowlist_bypasses_denial(self):
        p = BrowserNetworkPolicy(allowlist={"127.0.0.1:8080"})
        assert p.validate("http://127.0.0.1:8080/x") == "http://127.0.0.1:8080/x"
        with pytest.raises(NetworkPolicyError):
            p.validate("http://127.0.0.1:9090/x")


class TestSchemeBlocks:
    def test_bad_scheme_rejected(self):
        p = BrowserNetworkPolicy.default()
        with pytest.raises(NetworkPolicyError):
            p.validate("file:///etc/passwd")
        with pytest.raises(NetworkPolicyError):
            p.validate("javascript:alert(1)")
        with pytest.raises(NetworkPolicyError):
            p.validate("data:text/html,hi")
