"""BrowserNetworkPolicy unit tests — deny-by-default egress for the agent browser."""

from __future__ import annotations

import socket

import pytest

from jbrowser.network import (
    BrowserNetworkPolicy,
    NetworkPolicyError,
    _is_private_ip,
    enforce_request_url,
)


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


class TestNonGlobalAddressSpace:
    @pytest.mark.parametrize("ip", [
        "100.64.0.1",     # CGNAT / shared address space (not is_private in Python)
        "100.127.255.254",
        "198.18.0.1",     # benchmarking
        "192.0.2.1",      # TEST-NET-1
        "203.0.113.1",    # TEST-NET-3
        "240.0.0.1",      # reserved (class E)
    ])
    def test_non_global_ipv4_denied(self, ip):
        assert _is_private_ip(ip) is True
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate(f"http://{ip}/")

    def test_ipv4_mapped_ipv6_denied(self):
        assert _is_private_ip("::ffff:127.0.0.1") is True
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate("http://[::ffff:127.0.0.1]/")

    @pytest.mark.parametrize("host", ["metadata", "metadata.google.internal", "instance-data", "fd00:ec2::254"])
    def test_metadata_hosts_denied(self, host):
        assert _is_private_ip(host) is True

    def test_global_addresses_allowed(self):
        p = BrowserNetworkPolicy.default()
        assert p.validate("https://8.8.8.8/") == "https://8.8.8.8/"
        assert p.validate("https://[2001:4860:4860::8888]/") == "https://[2001:4860:4860::8888]/"

    def test_allow_private_still_permits_localhost(self):
        p = BrowserNetworkPolicy(allow_private=True)
        assert p.validate("http://127.0.0.1:8000") == "http://127.0.0.1:8000"


class TestMalformedAuthority:
    @pytest.mark.parametrize("url", [
        "http://example.com:notaport/",   # non-numeric port
        "http://example.com:99999/",      # out-of-range port
        "http://[::1/",                   # unterminated IPv6 bracket
        "http:///path",                   # empty authority
    ])
    def test_malformed_urls_raise_policy_error_not_valueerror(self, url):
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate(url)


class TestDnsRebindingHermetic:
    """getaddrinfo is stubbed -- these never touch live DNS."""

    @staticmethod
    def _stub(monkeypatch, answers=None, error=None):
        def fake_getaddrinfo(host, *args, **kwargs):
            if error is not None:
                raise error
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))
                for ip in (answers or [])
            ]
        monkeypatch.setattr("jbrowser.network.socket.getaddrinfo", fake_getaddrinfo)

    def test_public_host_resolving_to_loopback_is_denied(self, monkeypatch):
        self._stub(monkeypatch, answers=["127.0.0.1"])
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate("https://rebind.example.com/")

    def test_public_host_resolving_to_rfc1918_is_denied(self, monkeypatch):
        self._stub(monkeypatch, answers=["10.1.2.3"])
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate("https://rebind.example.com/")

    def test_dns_failure_denies_by_default(self, monkeypatch):
        self._stub(monkeypatch, error=socket.gaierror("no such host"))
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate("https://nope.example.com/")

    def test_public_host_resolving_public_ip_is_allowed(self, monkeypatch):
        self._stub(monkeypatch, answers=["93.184.216.34"])
        p = BrowserNetworkPolicy.default()
        assert p.validate("https://example.com/x") == "https://example.com/x"

    def test_allow_private_mode_skips_resolution(self, monkeypatch):
        def explode(host, *args, **kwargs):
            raise AssertionError("getaddrinfo must not run when allow_private")
        monkeypatch.setattr("jbrowser.network.socket.getaddrinfo", explode)
        p = BrowserNetworkPolicy(allow_private=True)
        assert p.validate("http://devbox.internal/") == "http://devbox.internal/"

    def test_ip_literals_classified_hermetically(self, monkeypatch):
        def literal_only(host, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, 0))]
        monkeypatch.setattr("jbrowser.network.socket.getaddrinfo", literal_only)
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate("http://[::ffff:10.0.0.1]/")
        assert (BrowserNetworkPolicy.default().validate("https://93.184.216.34/")
                == "https://93.184.216.34/")

    def test_obfuscated_numeric_host_denied_via_resolution(self, monkeypatch):
        self._stub(monkeypatch, answers=["127.0.0.1"])
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate("http://2130706433/")

    def test_empty_dns_answers_denied(self, monkeypatch):
        self._stub(monkeypatch, answers=[])
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate("https://empty.example.com/")

    def test_mixed_public_and_private_answers_denied(self, monkeypatch):
        self._stub(monkeypatch, answers=["93.184.216.34", "10.10.10.10"])
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate("https://mixed.example.com/")

    def test_mixed_answers_denied_regardless_of_order(self, monkeypatch):
        self._stub(monkeypatch, answers=["10.10.10.10", "93.184.216.34"])
        with pytest.raises(NetworkPolicyError):
            BrowserNetworkPolicy.default().validate("https://mixed2.example.com/")


class TestEnforceRequestUrl:
    def test_http_private_denied_public_allowed(self):
        p = BrowserNetworkPolicy.default()
        with pytest.raises(NetworkPolicyError):
            enforce_request_url(p, "http://10.0.0.5/")
        enforce_request_url(p, "https://93.184.216.34/")

    def test_ws_and_wss_validated_under_http_form(self):
        p = BrowserNetworkPolicy.default()
        with pytest.raises(NetworkPolicyError):
            enforce_request_url(p, "ws://127.0.0.1:9222/devtools")
        with pytest.raises(NetworkPolicyError):
            enforce_request_url(p, "wss://192.168.1.5/socket")
        enforce_request_url(p, "wss://93.184.216.34/socket")

    def test_non_network_schemes_pass_through(self):
        p = BrowserNetworkPolicy.default()
        for url in ("data:text/plain,x", "blob:https://example.com/1",
                    "about:blank", "devtools://devtools/x"):
            enforce_request_url(p, url)
