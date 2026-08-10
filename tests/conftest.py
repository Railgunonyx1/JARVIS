"""Shared pytest fixtures.

Isolates the process-wide audit-log singleton to a temp SQLite file for each
test, so rows never leak between tests or from ``~/.jarvis/data/audit.db``
across sessions. Any test that exercises ``get_audit_log()`` sees only the
rows it wrote itself.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_audit_log(tmp_path, monkeypatch):
    from security import audit

    monkeypatch.setattr(audit, "_audit_log", audit.AuditLog(tmp_path / "audit.db"))
    yield
    audit._audit_log = None
