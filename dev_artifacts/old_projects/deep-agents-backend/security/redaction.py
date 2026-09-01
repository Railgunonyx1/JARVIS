"""
Redaction — privacy filter for text leaving the machine.

Applied before any text is sent to a cloud service (e.g. Edge-TTS synthesis)
so secrets that surfaced into a response never reach a third-party endpoint.
Local-only paths (Piper TTS) are exempt.

Kept dependency-free and fast: a handful of compiled regexes plus an
optional pass that strips configured API key values when they leak into text.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("jarvis.security.redaction")

_PATTERNS = [
    # JWT: three dot-separated base64url segments (header.payload.signature)
    re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    # Long base64/hex-looking tokens (>= 32 chars, word chars + dash/underscore)
    re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"),
    # key=value / key: value secret assignments
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|password|authorization|bearer)"
        r"\s*[:=]\s*[^\s,;]+"
    ),
    # Email addresses
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    # US/NA phone numbers (optional +1 / parens / dashes / dots / spaces)
    re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)"),
    # Card-like digit runs (13-19 digits, optionally separated by single dashes/spaces)
    re.compile(r"\b(?:\d[ -]?){13,18}\d\b"),
]

_configured_keys_cache: list[str] = []


def _configured_secrets() -> list[str]:
    """Real API key values from config, cached after first load."""
    global _configured_keys_cache
    if _configured_keys_cache:
        return _configured_keys_cache
    try:
        from core.api_keys import get_all_api_keys
        _configured_keys_cache = [
            str(v) for v in get_all_api_keys().values()
            if isinstance(v, str) and len(v) >= 8
        ]
    except Exception as e:
        logger.debug("Could not load API keys for redaction: %s", e)
    return _configured_keys_cache


def redact_sensitive(text: str) -> str:
    """Replace sensitive content in `text` with [REDACTED]."""
    if not text:
        return text
    out = text
    for pat in _PATTERNS:
        out = pat.sub("[REDACTED]", out)
    for secret in _configured_secrets():
        if secret in out:
            out = out.replace(secret, "[REDACTED]")
    return out
