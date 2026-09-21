"""Tests for repo-mine pass-3 tools: task pulse, watch rules, secret refs.

All effects are hermetic: state files are redirected into tmp_path via
monkeypatched ProjectContext, outbound pushes are stubbed, and the
environment is restored after every secret test.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pulse(monkeypatch, tmp_path):
    """task_pulse with state rooted in tmp_path."""
    monkeypatch.setattr(
        "core.project.ProjectContext.discover",
        lambda: type("C", (), {"root_path": tmp_path})(),
    )
    return importlib.import_module("tools.task_pulse")


@pytest.fixture()
def rules(monkeypatch, tmp_path):
    """watch_rules with state rooted in tmp_path and pushes captured."""
    monkeypatch.setattr(
        "core.project.ProjectContext.discover",
        lambda: type("C", (), {"root_path": tmp_path})(),
    )
    wr = importlib.import_module("tools.watch_rules")

    from tools.schema import ToolResult

    calls: list[dict] = []

    def fake_notify(args):
        calls.append(args)
        return ToolResult(success=True, output="pushed")

    return wr, calls, fake_notify


@pytest.fixture()
def secrets(monkeypatch, tmp_path):
    """secret_ref with index in tmp_path."""
    monkeypatch.setattr(
        "core.project.ProjectContext.discover",
        lambda: type("C", (), {"root_path": tmp_path})(),
    )
    return importlib.import_module("tools.secret_ref")


# ---------------------------------------------------------------------------
# task.ping / task.alert (healthchecks.io semantics)
# ---------------------------------------------------------------------------

class TestTaskPulse:
    def test_ping_registers_and_counts(self, pulse):
        r1 = pulse.task_ping({"name": "Nightly Backup", "expect_minutes": 90})
        assert r1.success
        assert r1.metadata["pings"] == 1
        r2 = pulse.task_ping({"name": "Nightly Backup"})
        assert r2.metadata["pings"] == 2
        # slug is stable across capitalization/spaces
        assert r2.metadata["slug"] == r1.metadata["slug"]

    def test_ping_requires_name(self, pulse):
        assert not pulse.task_ping({"name": "  "}).success

    def test_alert_all_healthy(self, pulse):
        pulse.task_ping({"name": "job", "expect_minutes": 60})
        res = pulse.task_alert({"notify": False})
        assert res.success
        assert res.metadata["overdue"] == 0
        assert res.metadata["healthy"] == 1

    def test_alert_detects_silence(self, pulse, monkeypatch):
        pulse.task_ping({"name": "job", "expect_minutes": 1})
        # Simulate the last ping happening 2 hours ago.
        state = pulse._load()
        slug = next(iter(state))
        state[slug]["last_ping"] -= 2 * 3600
        pulse._save(state)
        res = pulse.task_alert({"notify": False})
        assert res.metadata["overdue"] == 1
        assert "OVERDUE" in res.output
        assert "job" in res.output

    def test_alert_pushes_once_per_silence_episode(self, pulse, monkeypatch):
        import types

        from tools.schema import ToolResult

        sent = []
        tp = importlib.import_module("tools.task_pulse")
        fake_notify = types.SimpleNamespace(
            send_notification=lambda args: (
                sent.append(args),
                ToolResult(success=True, output="ok"),
            )[1]
        )
        monkeypatch.setitem(sys.modules, "tools.notify", fake_notify)

        pulse.task_ping({"name": "job", "expect_minutes": 1})
        state = pulse._load()
        state[next(iter(state))]["last_ping"] -= 2 * 3600
        pulse._save(state)

        r1 = pulse.task_alert({"notify": True})
        assert r1.metadata["notified"] is True
        assert len(sent) == 1
        # Second sweep within the same silence: no duplicate spam.
        r2 = pulse.task_alert({"notify": True})
        assert len(sent) == 1
        assert "OVERDUE" in r2.output
        # A fresh ping re-arms the alert.
        pulse.task_ping({"name": "job"})
        pulse.task_alert({"notify": True})
        assert len(sent) == 1  # healthy again -> no push


# ---------------------------------------------------------------------------
# watch.rule / watch.run (huginn agents)
# ---------------------------------------------------------------------------

class TestWatchRules:
    def test_add_requires_url(self, rules):
        wr, _, _ = rules
        res = wr.watch_rule({"url": "ftp://x"})
        assert not res.success
        res = wr.watch_rule({})
        assert not res.success

    def test_add_lists_and_removes(self, rules):
        wr, _, _ = rules
        added = wr.watch_rule({"url": "https://x.test/a", "trigger": "changed"})
        assert added.success
        rid = added.metadata["rule_id"]

        listing = wr.watch_rule({"action": "list"})
        assert listing.metadata["count"] == 1
        assert "https://x.test/a" in listing.output

        removed = wr.watch_rule({"action": "remove", "rule_id": rid[:8]})
        assert removed.success
        assert wr.watch_rule({"action": "list"}).metadata["count"] == 0

    def test_run_fires_notify_on_change(self, rules, monkeypatch):
        wr, calls, fake_notify = rules
        wr.watch_rule({"url": "https://x.test/page", "trigger": "changed",
                       "then": "notify", "message": "page moved"})

        from tools.schema import ToolResult

        monkeypatch.setattr(
            "tools.page_watch.page_watch",
            lambda args: ToolResult(success=True, output="CHANGED",
                                    metadata={"changed": True}),
        )
        res = wr.watch_run({}, send_notification_fn=fake_notify)
        assert res.metadata["fired"] == 1
        assert len(calls) == 1
        assert calls[0]["message"] == "page moved"
        # fired bookkeeping persisted
        stored = wr._load()
        assert next(iter(stored.values()))["fired_count"] == 1

    def test_run_quiet_when_unchanged(self, rules, monkeypatch):
        wr, calls, fake_notify = rules
        wr.watch_rule({"url": "https://x.test/quiet", "trigger": "changed"})

        from tools.schema import ToolResult

        monkeypatch.setattr(
            "tools.page_watch.page_watch",
            lambda args: ToolResult(success=True, output="unchanged",
                                    metadata={"changed": False}),
        )
        res = wr.watch_run({}, send_notification_fn=fake_notify)
        assert res.metadata["fired"] == 0
        assert res.metadata["quiet"] == 1
        assert calls == []

    def test_run_no_rules(self, rules):
        wr, _, _ = rules
        res = wr.watch_run({})
        assert res.success
        assert res.metadata["fired"] == 0

    def test_trigger_validation(self, rules):
        wr, _, _ = rules
        res = wr.watch_rule({"url": "https://x.test/b", "trigger": "sometimes"})
        assert not res.success
        res = wr.watch_rule({"url": "https://x.test/b", "then": "shout"})
        assert not res.success


# ---------------------------------------------------------------------------
# secret.ref / secret.status (Infisical-style indirection)
# ---------------------------------------------------------------------------

class TestSecretRef:
    def test_register_then_resolve_returns_handle_not_value(self, secrets, monkeypatch):
        monkeypatch.setenv("JARVIS_TEST_SECRET_XY", "super-secret-value-123")
        reg = secrets.secret_ref({"action": "register", "name": "JARVIS_TEST_SECRET_XY"})
        assert reg.success
        assert "super-secret-value-123" not in reg.output

        res = secrets.secret_ref({"name": "JARVIS_TEST_SECRET_XY"})
        assert res.success
        assert "super-secret-value-123" not in res.output
        assert res.metadata["handle"].startswith("secret:JARVIS_TEST_SECRET_XY#")

    def test_resolve_unregistered_is_denied(self, secrets):
        res = secrets.secret_ref({"name": "DEFINITELY_NOT_SET_ZZ"})
        assert not res.success
        assert "cannot enumerate" in res.error

    def test_register_missing_env_fails(self, secrets, monkeypatch):
        monkeypatch.delenv("JARVIS_TEST_SECRET_AB", raising=False)
        res = secrets.secret_ref({"action": "register", "name": "JARVIS_TEST_SECRET_AB"})
        assert not res.success

    def test_name_validation(self, secrets, monkeypatch):
        monkeypatch.setenv("lower_case_name", "x")
        assert not secrets.secret_ref({"action": "register", "name": "lower_case_name"}).success
        assert not secrets.secret_ref({"action": "register", "name": "A;B"}).success

    def test_status_masks_and_reports_missing(self, secrets, monkeypatch):
        monkeypatch.setenv("JARVIS_TEST_SECRET_OK", "value-abcd")
        monkeypatch.setenv("JARVIS_TEST_SECRET_GONE", "gone-xyz")
        secrets.secret_ref({"action": "register", "name": "JARVIS_TEST_SECRET_OK"})
        secrets.secret_ref({"action": "register", "name": "JARVIS_TEST_SECRET_GONE"})
        monkeypatch.delenv("JARVIS_TEST_SECRET_GONE")

        res = secrets.secret_status({})
        assert res.success
        assert "value-abcd" not in res.output  # never the value
        assert "JARVIS_TEST_SECRET_OK" in res.output
        assert "[MISSING]" in res.output  # registered but unset is visible

    def test_forget(self, secrets, monkeypatch):
        monkeypatch.setenv("JARVIS_TEST_SECRET_F1", "v")
        secrets.secret_ref({"action": "register", "name": "JARVIS_TEST_SECRET_F1"})
        assert secrets.secret_ref({"action": "forget", "name": "JARVIS_TEST_SECRET_F1"}).success
        assert not secrets.secret_ref({"name": "JARVIS_TEST_SECRET_F1"}).success
