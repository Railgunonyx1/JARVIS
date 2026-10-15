"""Tests for the shared credential-signature scanner.

Offline and hermetic — no network, no config load. Covers detection precision,
label-only reporting (never the secret), readable redaction, and the fact that
blunt redaction now layers the precise pass first.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


SAMPLES = [
    ("ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R", "GitHub token"),
    ("github_pat_" + "11ABCDEFG0aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd", "GitHub fine-grained PAT"),
    ("glpat-" + "Wj9Xk2mN4pQr6sT8uV0wXyZ", "GitLab token"),
    ("AKIA" + "IOSFODNN7EXAMPLE", "AWS access key id"),
    ("ASIA" + "IOSFODNN7EXAMPLE", "AWS temporary access key id"),
    ("sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc", "Stripe secret key"),
    ("whsec_" + "c2VjcmV0c2VjcmV0c2VjcmV0", "Stripe webhook secret"),
    ("sk-ant-api03-" + "a1b2c3d4e5f6g7h8i9j0k1l2m3n4", "Anthropic key"),
    ("sk-or-v1-" + "1234567890abcdef1234567890abcdef", "OpenRouter key"),
    ("sk-proj-abcdefghijklmnopqrstuvwxyz012345", "OpenAI-style secret key"),
    ("AIza" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6q", "Google API key"),
    ("hf_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "Hugging Face token"),
    ("xoxb-" + "123456789012-abcdefghijklmnop", "Slack token"),
    ("https://hooks.slack.com" + "/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX", "Slack webhook"),
    ("https://discord.com/api/webhooks/1234567890/AbCdEfGhIjKlMnOpQrStUvWxYz", "Discord webhook"),
    ("AC" + "1234567890abcdef1234567890abcdef", "Twilio account sid"),
    ("npm_" + "1234567890abcdef1234567890abcdef1234", "npm token"),
    ("pypi-" + "AaBbCcDdEeFfGgHhIiJjKkLlMnOoPp", "PyPI token"),
    ("SG." + "aaaaaaaaaaaaaaaaaaaaaa" + "." + "bbbbbbbbbbbbbbbbbbbbbb", "SendGrid key"),
    ("key-" + "1234567890abcdef1234567890abcdef", "Mailgun key"),
    ("Bearer " + "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop", "Bearer token"),
    ("-----BEGIN RSA PRIVATE KEY-----", "Private key block"),
]


def test_detects_all_sample_credential_formats():
    from security.credentials import find_credential_leaks

    for value, label in SAMPLES:
        leaks = find_credential_leaks(f"config: token = {value}")
        assert label in leaks, f"expected {label!r} in {leaks}"


def test_has_credential_leak_is_true_for_secrets():
    from security.credentials import has_credential_leak

    assert has_credential_leak("export GITHUB_TOKEN=ghp_" + "a" * 36)
    assert not has_credential_leak("the quick brown fox jumps over the lazy dog")


def test_clean_text_reports_nothing():
    from security.credentials import find_credential_leaks, has_credential_leak

    clean = "JARVIS browses the web via CDP at 127.0.0.1:8170 and streams BusEvents."
    assert find_credential_leaks(clean) == []
    assert not has_credential_leak(clean)


def test_find_returns_labels_not_secrets():
    from security.credentials import find_credential_leaks

    secret = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R"
    leaks = find_credential_leaks(f"leaked {secret} in a log line")
    assert leaks == ["GitHub token"]
    assert secret not in " ".join(leaks)


def test_redaction_keeps_surrounding_text_readable():
    from security.credentials import redact_credential_leaks

    secret = "glpat-" + "Wj9Xk2mN4pQr6sT8uV0wXyZ"
    out = redact_credential_leaks(f"the deploy token is {secret} ; retrying now")
    assert secret not in out
    assert "[REDACTED:GitLab token]" in out
    assert out.startswith("the deploy token is ")
    assert out.endswith(" ; retrying now")


def test_redaction_does_not_touch_plain_prose():
    from security.credentials import redact_credential_leaks

    prose = "Use the CDP websocket to attach to the Orbit Chromium instance."
    assert redact_credential_leaks(prose) == prose


def test_sensitive_redaction_layers_precise_pass_first():
    from security.redaction import redact_sensitive

    secret = "sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    out = redact_sensitive(f"key {secret} used for the gateway")
    assert secret not in out


def test_sensitive_redaction_still_blunt_passes():
    from security.redaction import redact_sensitive

    # Bare long token with no vendor prefix: precise pass skips it, blunt pass
    # still strips it, which is the documented division of labour.
    bare = "a" * 40
    out = redact_sensitive(f"session {bare} expired")
    assert bare not in out


def test_tools_security_patterns_include_vendor_table():
    from security.credentials import CREDENTIAL_SIGNATURES
    from tools.security import _SECRET_PATTERNS

    shared = {(p.pattern, label) for p, label in CREDENTIAL_SIGNATURES}
    ours = {(p.pattern, label) for p, label in _SECRET_PATTERNS}
    assert shared <= ours


def test_scan_line_reports_vendor_labels():
    from tools.security import _SECRET_PATTERNS

    line = "TOKEN = 'ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R'"
    labels = [label for p, label in _SECRET_PATTERNS if p.search(line)]
    assert "GitHub token" in labels
