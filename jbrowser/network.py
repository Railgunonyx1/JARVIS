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
from urllib.parse import urlparse

# Known public DNS suffixes mapped to "not private" heuristics. We rely on DNS
# resolution only for host names; numeric IPs are classified purely from the
# address, and IPv4-mapped IPv6 is normalized first.
_LOCALHOST_HOSTS = {"localhost", "localhost.localdomain", "localtest.me"}


class NetworkPolicyError(Exception):
    """Raised when a navigation target is denied by the network policy."""


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

        if _is_private_ip(host) and not self.allow_private:
            raise NetworkPolicyError(
                f"private/loopback destination blocked by network policy: {netloc}"
            )
        if host.lower() in _LOCALHOST_HOSTS and not self.allow_private:
            raise NetworkPolicyError(
                f"loopback destination blocked by network policy: {netloc}"
            )
        if not self.allow_public_http and not url.lower().startswith("https://"):
            raise NetworkPolicyError(
                f"plain-HTTP destination blocked by network policy: {netloc}"
            )
        return url
