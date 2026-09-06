"""Sensitive-site policy for browser navigation consent (JARVIS Orbit).

Some destinations carry identity, payment, or account-consequence weight that a
low-risk ``navigate`` label alone should not auto-approve. The central
PermissionEngine consults this policy before any navigation-style tool
(permission ending in ``.open``) may proceed: a matching destination ALWAYS
requires explicit operator consent (fail closed when no consent channel is
wired), regardless of mode.

Matching is host-based: a URL matches if its host equals an entry or is a
subdomain of one (e.g. ``idp.chase.com`` matches ``chase.com``). The list is a
conservative allowlist of well-known banking / webmail / code-account / login-
heavy origins and is intentionally free of path heuristics so behavior stays
deterministic and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

_SENSITIVE_HOSTS = frozenset({
    # Banking / payments / money movement
    "chase.com", "bankofamerica.com", "wellsfargo.com", "citi.com",
    "capitalone.com", "hsbc.com", "barclays.com", "paypal.com",
    "stripe.com", "squareup.com", "venmo.com", "coinbase.com",
    # Webmail / identity / personal data
    "gmail.com", "outlook.com", "yahoo.com", "proton.me", "icloud.com",
    "zoho.com", "mailchimp.com",
    # Code / cloud console accounts
    "github.com", "gitlab.com", "aws.amazon.com", "azure.microsoft.com",
    "console.cloud.google.com",
    # Login-heavy consumer accounts (social / shopping / streaming)
    "facebook.com", "instagram.com", "x.com", "twitter.com", "linkedin.com",
    "reddit.com", "tiktok.com", "snapchat.com", "amazon.com", "netflix.com",
    "apple.com",
})


@dataclass(frozen=True)
class SensitiveSitePolicy:
    """Deterministic host allowlist matcher for sensitive destinations."""

    hosts: frozenset = _SENSITIVE_HOSTS

    def match(self, url: str) -> bool:
        """Return True when ``url`` targets a sensitive origin."""
        if not url:
            return False
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        if not host:
            return False
        return any(host == h or host.endswith("." + h) for h in self.hosts)

    def is_sensitive(self, url: str) -> bool:
        return self.match(url)


SENSITIVE_SITES = SensitiveSitePolicy()