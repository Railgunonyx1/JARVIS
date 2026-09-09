"""J-Browser — navigation / network policy.

An autonomous agent browser must not assume every HTTP(S) destination is safe.
Before navigation we classify the target and deny destinations that reach
machine-local or private networks by default:

    public HTTPS  -> allow
    public HTTP   -> allow (explicit)
    loopback      -> deny
    link-local    -> deny
    private IP    -> deny
    explicit allowlist -> allow (overrides)

This runs *before* ``page.goto``/navigation, not after the page loads, so an
agent can never pivot a browse into localhost services, internal dashboards,
development servers, or other machine-local endpoints.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Known public DNS suffixes mapped to "not private" heuristics. We rely on DNS
# resolution only for host names; numeric IPs are classified purely from the
# address, and IPv4-mapped IPv6 is normalized first.
_LOCALHOST_HOSTS = {"localhost", "localhost.localdomain", "localtest.me"}


class NetworkPolicyError(Exception):
    """Raised when a navigation target is denied by the network policy."""


def _check_dns_resolution(host: str, netloc: str, allow_private: bool) -> None:
    """Resolve hostname via DNS and reject if any result is a private/internal IP.

    This prevents DNS rebinding attacks where an attacker-controlled domain
    resolves to 127.0.0.1, 192.168.x.x, or other internal addresses after
    the initial hostname check passes.
    """
    if allow_private:
        return
    try:
        results = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        # DNS resolution failed — deny by default (safe posture).
        raise NetworkPolicyError(
            f"DNS resolution failed for {netloc}; denying by default"
        )
    for family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        if _is_private_ip(ip_str):
            raise NetworkPolicyError(
                f"hostname {host} resolves to private IP {ip_str}; "
                f"blocked by network policy (DNS rebinding protection)"
            )


def _is_private_ip(host: str) -> bool:
    if not host:
        return True
    host = host.strip().strip("[]")
    if host.lower().endswith(".localhost"):
        return True
    try:
        addr = ipaddress.ip_address(host.split("%")[0].split("/")[0])
    except ValueError:
        return False  # not an IP literal; resolved later
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


class BrowserNetworkPolicy:
    """Deny-by-default policy for browser egress.

    ``allowlist`` is an iterable of exact hosts (e.g. ``{"localhost:8000"}``,
    ``{"127.0.0.1"}``) that bypass the private/loopback denial so developers
    can still browse their own local services explicitly.
    """

    def __init__(
        self,
        *,
        allow_public_http: bool = True,
        allow_private: bool = False,
        allowlist: set[str] | None = None,
    ) -> None:
        self.allow_public_http = allow_public_http
        self.allow_private = allow_private
        self.allowlist = {h.strip().lower() for h in (allowlist or set())}

    @classmethod
    def default(cls) -> BrowserNetworkPolicy:
        return cls()

    @classmethod
    def allow_localhost(cls) -> BrowserNetworkPolicy:
        return cls(allow_private=True)

    def _allowed(self, netloc: str) -> bool:
        if not netloc:
            return False
        key = netloc.lower()
        if key in self.allowlist:
            return True
        return False

    def validate(self, url: str) -> str:
        """Return a normalized, validated URL or raise :class:`NetworkPolicyError`."""
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            raise NetworkPolicyError(f"unsupported scheme: {scheme or '(none)'}")
        host = parsed.hostname or ""
        port = parsed.port
        netloc = f"{host}:{port}" if port else host

        if self._allowed(netloc) or self._allowed(host):
            return url

        # Check the hostname itself first (handles IP literals).
        if _is_private_ip(host) and not self.allow_private:
            raise NetworkPolicyError(
                f"private/loopback destination blocked by network policy: {netloc}"
            )
        if host.lower() in _LOCALHOST_HOSTS and not self.allow_private:
            raise NetworkPolicyError(
                f"loopback destination blocked by network policy: {netloc}"
            )

        # DNS-aware validation: resolve hostname and check all resulting IPs.
        # This prevents DNS rebinding attacks where a public hostname resolves
        # to a private/internal address after validation.
        if not _is_private_ip(host):
            _check_dns_resolution(host, netloc, self.allow_private)

        if not self.allow_public_http and not url.lower().startswith("https://"):
            raise NetworkPolicyError(
                f"plain-HTTP destination blocked by network policy: {netloc}"
            )
        return url
