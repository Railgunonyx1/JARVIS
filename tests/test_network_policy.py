"""BrowserNetworkPolicy unit tests — deny-by-default egress for the agent browser."""

from __future__ import annotations

import pytest

from jbrowser.network import BrowserNetworkPolicy, NetworkPolicyError, _is_private_ip


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
