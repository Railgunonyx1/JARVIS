"""Orbit import wizard — CSV password import as *guidance only* (G11).

The wizard turns a pasted site-credentials CSV into a masked import plan:
every account is validated (shape, duplicates, sensitive origins), passwords
are scored with a lightweight strength heuristic, and the output is a set of
per-site *actions* plus security guidance. **No password value is ever
persisted, returned, logged, or sent to the model** — the records keep only
presence/strength flags, and secret creation is user-mediated inside
Chromium's own saved-passwords surface.

Safety invariants (tested):
  * ``ImportPlan.to_text()`` and every ``PasswordCsvRecord`` never contain a
    password value, in any derived string.
  * The audit path stores only ``params_hash`` of the raw CSV (one-way); the
    ToolExecutionService scrubber strips any leaked value from audit text.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from security.sensitive_sites import SENSITIVE_SITES

# Header aliases (case-insensitive), preferred → aliases.
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "site": ("site", "name", "title", "label"),
    "url": ("url", "website", "web", "uri", "address"),
    "username": ("username", "user", "login", "email", "userid"),
    "password": ("password", "pass", "secret", "pw"),
}

_COMMON_PASSWORDS: frozenset[str] = frozenset({
    "password", "password1", "12345678", "123456789", "1234567890",
    "qwerty", "qwerty123", "abc123", "letmein", "iloveyou", "admin",
    "welcome", "monkey", "dragon", "login", "trustno1",
})

_CHAR_CLASSES: tuple[re.Pattern, ...] = (
    re.compile("[0-9]"),
    re.compile("[a-z]"),
    re.compile("[A-Z]"),
    re.compile(r"[^A-Za-z0-9]"),
)


def _normalize_host(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        host = ""
    return host.rstrip(".")


def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def classify_strength(password: str) -> str:
    """Return 'weak' | 'ok' | 'strong' | '' for an empty password.

    Lightweight, deterministic heuristic (length + distinct character
    classes + common-word blacklist). Guidance only — never surfaced as a
    secret or stored anywhere.
    """
    if not password:
        return ""
    pw = password
    if len(pw) < 8 or pw.lower() in _COMMON_PASSWORDS:
        return "weak"
    classes = sum(1 for cls in _CHAR_CLASSES if cls.search(pw))
    if len(pw) < 12 and classes < 3:
        return "weak"
    if len(pw) >= 14 and classes >= 3:
        return "strong"
    return "ok"


@dataclass(frozen=True)
class PasswordCsvRecord:
    """One validated account; never carries the password value."""

    site: str
    url: str
    username: str
    has_password: bool
    strength: str = ""
    sensitive: bool = False
    duplicate: bool = False
    row: int = 0


@dataclass
class ImportPlan:
    """Masked import plan: per-site actions + guidance, no secrets."""

    records: list[PasswordCsvRecord] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def needs_password(self) -> list[PasswordCsvRecord]:
        return [r for r in self.records if not r.has_password]

    @property
    def weak_passwords(self) -> list[PasswordCsvRecord]:
        return [r for r in self.records if r.strength == "weak"]

    @property
    def duplicates(self) -> list[PasswordCsvRecord]:
        return [r for r in self.records if r.duplicate]

    @property
    def sensitive_sites(self) -> list[PasswordCsvRecord]:
        return [r for r in self.records if r.sensitive]

    def to_text(self) -> str:
        """Human-readable masked plan. Never contains password values."""
        lines = [
            "Password import plan (guidance only - no secrets shown or stored)",
            f"Accounts: {self.total}",
        ]
        if self.needs_password:
            lines.append("Add manually (no password in your CSV):")
            lines += [f"  - {_mask(r)}" for r in self.needs_password]
        else:
            lines.append("Add manually: none")
        if self.weak_passwords:
            lines.append("Weak passwords to replace:")
            lines += [f"  - {_mask(r)} (strength: weak)" for r in self.weak_passwords]
        if self.duplicates:
            lines.append("Duplicates to merge:")
            lines += [f"  - {_mask(r)} (duplicate)" for r in self.duplicates]
        if self.sensitive_sites:
            lines.append("Sensitive origins - create directly in Chromium "
                         "> Passwords, never auto-imported:")
            lines += [f"  - {r.url}" for r in self.sensitive_sites]
        lines.append("Guidance:")
        if self.parse_errors:
            lines.append(f"  - {len(self.parse_errors)} row(s) skipped")
            lines += [f"    * {e[:200]}" for e in self.parse_errors[:5]]
        if not self.records:
            lines.append("  - CSV produced no valid accounts; check the header "
                         "(expected columns: site, url, username, password).")
            return "\n".join(lines)
        lines += [
            "  - Complete each account in Chromium > Passwords "
            "(your secrets stay in Chromium's storage).",
            "  - Prefer a passphrase of 14+ characters with 3+ character types.",
            "  - Remove the CSV file after import; it is not retained by JARVIS.",
        ]
        return "\n".join(lines)


def _mask(record: PasswordCsvRecord) -> str:
    user = record.username or "(unknown user)"
    site = record.site or record.url
    return f"{site} ({user})"


def parse_password_csv(text: str) -> ImportPlan:
    """Parse + validate a credentials CSV into a masked :class:`ImportPlan`.

    Recognizes common header aliases case-insensitively. A missing ``url``
    column is fatal (ValueError); malformed rows are recorded as parse errors
    and skipped. Password values are consumed only to set presence/strength
    flags and are never retained.
    """
    plan = ImportPlan()
    if not text or not text.strip():
        plan.parse_errors.append("empty CSV")
        return plan

    stream = csv.reader(io.StringIO(text))
    try:
        header = [next(stream)]
    except StopIteration:
        plan.parse_errors.append("empty CSV")
        return plan
    header = [(h or "").strip().lower() for h in header[0]]

    columns: dict[str, int] = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        idx = next((i for i, h in enumerate(header)
                    if h in aliases or h == canonical), None)
        if idx is not None and idx not in columns.values():
            columns[canonical] = idx
    if "url" not in columns:
        raise ValueError(
            "CSV must include a URL column (site, url, username, password)"
        )

    seen: set[tuple[str, str]] = set()
    for row_no, row in enumerate(stream, start=2):
        if not any((c or "").strip() for c in row):
            continue
        try:
            url = str(row[columns["url"]]).strip()
            username = str(row[columns["username"]]).strip() \
                if "username" in columns else ""
            site = str(row[columns["site"]]).strip() \
                if "site" in columns else _site_from_url(url)
            password = str(row[columns["password"]]).strip() \
                if "password" in columns else ""
        except IndexError:
            plan.parse_errors.append(f"row {row_no}: too few columns")
            continue
        if not url:
            plan.parse_errors.append(f"row {row_no}: missing url")
            continue
        if not username:
            plan.parse_errors.append(f"row {row_no}: missing username")
            continue

        key = (_normalize_host(url), _normalize_username(username))
        duplicate = key in seen
        seen.add(key)
        record = PasswordCsvRecord(
            site=site or _site_from_url(url),
            url=url,
            username=username,
            has_password=bool(password),
            strength=classify_strength(password),
            sensitive=SENSITIVE_SITES.is_sensitive(url),
            duplicate=duplicate,
            row=row_no,
        )
        plan.records.append(record)
    return plan


def _site_from_url(url: str) -> str:
    host = _normalize_host(url)
    return host or url


def run_import_analysis(csv_text: str) -> ImportPlan:
    """Convenience entry point for the tool handler."""
    return parse_password_csv(csv_text)


__all__ = [
    "ImportPlan",
    "PasswordCsvRecord",
    "classify_strength",
    "parse_password_csv",
    "run_import_analysis",
]