"""
Credential signature scanning — high-signal detection of secret-shaped strings.

Distinct from ``redaction.py``: redaction is intentionally *blunt* (it strips
anything that looks vaguely sensitive so nothing leaves the machine). This
module is intentionally *precise* — it matches well-known credential formats by
prefix/shape so we can (a) report what kind of secret leaked, and (b) redact
only the credential itself while leaving surrounding text readable.

Single source of truth: ``tools/security.py`` imports these signatures for its
file scans, and ``redaction.py`` layers them on top of its blunt pass so a
credential that the blunt patterns miss still gets caught before persistence or
any cloud-bound call.
"""

from __future__ import annotations

import re

__all__ = [
    "CREDENTIAL_SIGNATURES",
    "find_credential_leaks",
    "has_credential_leak",
    "redact_credential_leaks",
]

# (compiled pattern, human label). Order matters only for reporting order.
# Every entry must be high-signal: a distinctive vendor prefix or a structure
# that is essentially never a legitimate identifier. Deliberately excluded:
# bare 40-char AWS secrets, raw UUIDs, and generic long tokens — too many false
# positives to auto-redact; the blunt pass in redaction.py still covers those.
CREDENTIAL_SIGNATURES: list[tuple[re.Pattern[str], str]] = [
    # --- GitHub ---
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), "GitHub fine-grained PAT"),
    # --- GitLab ---
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b"), "GitLab token"),
    # --- AWS ---
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "AWS temporary access key id"),
    # --- Stripe ---
    (re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b"), "Stripe secret key"),
    (re.compile(r"\bwhsec_[A-Za-z0-9]{20,}\b"), "Stripe webhook secret"),
    # --- Model providers (JARVIS-relevant) ---
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), "Anthropic key"),
    (re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}\b"), "OpenRouter key"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "OpenAI-style secret key"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,45}\b"), "Google API key"),
    (re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"), "Hugging Face token"),
    # --- Slack ---
    (re.compile(r"\bxox[bpasr]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"https?://hooks\.slack\.com/services/[A-Za-z0-9/_-]+"), "Slack webhook"),
    # --- Discord ---
    (
        re.compile(r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+"),
        "Discord webhook",
    ),
    # --- Twilio ---
    (re.compile(r"\bAC[0-9a-fA-F]{32}\b"), "Twilio account sid"),
    # --- Package registries ---
    (re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"), "npm token"),
    (re.compile(r"\bpypi-[A-Za-z0-9_-]{20,}\b"), "PyPI token"),
    # --- Messaging / email ---
    (re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"), "SendGrid key"),
    (re.compile(r"\bkey-[0-9a-zA-Z]{32}\b"), "Mailgun key"),
    # --- Auth headers / key material ---
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}"), "Bearer token"),
    (
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----"),
        "Private key block",
    ),
]


def find_credential_leaks(text: str) -> list[str]:
    """Return the distinct labels of credential shapes found in ``text``.

    Only labels are returned, never the matched secret itself, so the result is
    safe to log or attach to a ToolResult / BusEvent.
    """
    if not text:
        return []
    seen: list[str] = []
    for pattern, label in CREDENTIAL_SIGNATURES:
        if pattern.search(text) and label not in seen:
            seen.append(label)
    return seen


def has_credential_leak(text: str) -> bool:
    """True if ``text`` contains at least one credential-shaped string."""
    if not text:
        return False
    return any(pattern.search(text) for pattern, _ in CREDENTIAL_SIGNATURES)


def redact_credential_leaks(text: str) -> str:
    """Replace credential-shaped substrings with ``[REDACTED:<label>]``.

    Unlike ``redaction.redact_sensitive`` this leaves the surrounding text
    intact, so an operator can still read the sentence a secret leaked into.
    """
    if not text:
        return text
    out = text
    for pattern, label in CREDENTIAL_SIGNATURES:
        out = pattern.sub(f"[REDACTED:{label}]", out)
    return out
