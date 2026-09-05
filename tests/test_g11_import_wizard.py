"""G11 — import wizard: CSV password import as guidance only, no stored secrets.

Hermetic. Proves the wizard parses/validates a pasted credentials CSV and
returns a masked import plan, that no derived string anywhere carries a
password value (reports, audit store, params), and that the whole path runs
through ToolExecutionService as a low-risk auto-approved orbit tool.
"""

from __future__ import annotations

import asyncio
import re

import pytest  # noqa: F401  (fixtures)

from core.agent.permissions import PermissionEngine
from core.agent.tool_service import ToolExecutionService
from core.decision_logger import DecisionLogger
from providers.types import ToolCall
from tools.registry import ToolRegistry

from orbit.tools import build_orbit_tools
from orbit.wizard import (
    ImportPlan,
    PasswordCsvRecord,
    classify_strength,
    parse_password_csv,
    run_import_analysis,
)

SECRETS = ("S3cret-Pw!42", "hunter2", "CorrectHorse78!!")

VALID_CSV = (
    "site,url,username,password\n"
    "Example,https://example.com/login,alice,S3cret-Pw!42\n"
    "Bank,https://bank.example.com,alice,hunter2\n"
    "Webmail,https://mail.example.com,bob,\n"
    "Alt,https://example.com/login,alice,S3cret-Pw!42\n"
)


def _records(plan: ImportPlan) -> list[PasswordCsvRecord]:
    return list(plan.records)


class TestParsing:
    def test_parses_and_masks_passwords(self):
        plan = run_import_analysis(VALID_CSV)
        assert plan.total == 4
        assert plan.parse_errors == []
        records = _records(plan)
        assert records[0].site == "Example"
        assert records[0].has_password is True
        assert records[0].strength == "ok"
        assert records[1].has_password is True
        assert records[1].strength == "weak"  # hunter2 is short/no classes
        assert records[2].has_password is False
        assert records[3].duplicate is True

    def test_header_aliases_and_quoted_fields(self):
        csv_text = (
            "Name,Website,User,Pass\n"
            '"Acme, Inc.",https://acme.example,alice,abc123\n'
        )
        plan = parse_password_csv(csv_text)
        assert plan.total == 1
        record = _records(plan)[0]
        assert record.site == "Acme, Inc."
        assert record.strength == "weak"
        assert record.sensitive is False

    def test_missing_url_column_is_fatal(self):
        with pytest.raises(ValueError) as exc:
            parse_password_csv("site,username,password\nx,alice,secret\n")
        assert "url" in str(exc.value)

    def test_malformed_rows_report_errors_and_are_skipped(self):
        plan = parse_password_csv(
            "site,url,username,password\n"
            "OnlyUrl,https://ex.com,,\n"
            ",https://ex.com,bob,pw\n"
        )
        assert plan.total == 1
        assert len(plan.parse_errors) == 1

    def test_empty_csv_is_not_fatal(self):
        plan = parse_password_csv("")
        assert plan.total == 0
        assert plan.parse_errors

    def test_sensitive_sites_are_flagged(self):
        plan = run_import_analysis(
            "site,url,username,password\n"
            "Chase,https://chase.com/account,alice,secret12345\n"
            "Docs,https://docs.example.com/notes,alice,secret12345\n"
        )
        flagged = [r for r in plan.records if r.sensitive]
        assert len(flagged) == 1
        assert flagged[0].url.startswith("https://chase.com")


class TestStrength:
    def test_empty_is_missing(self):
        assert classify_strength("") == ""

    def test_weak_short_or_common(self):
        assert classify_strength("password") == "weak"
        assert classify_strength("12345678") == "weak"
        assert classify_strength("abcd1234") == "weak"  # 8 chars, 2 classes

    @pytest.mark.parametrize("pw,expected", [
        ("CorrectHorse78!!", "strong"),
        ("aF3#x!Q9mZ$kV7", "strong"),
        ("Token-pass99", "ok"),
    ])
    def test_ok_and_strong(self, pw, expected):
        assert classify_strength(pw) == expected


class TestNoSecrets:
    def _all_derived_strings(self, plan: ImportPlan) -> list[str]:
        out = [plan.to_text()]
        out += [repr(plan), str(plan)]
        records = list(plan.records)
        out += [repr(records)]
        out += [str(r) for r in records]
        out += [f"{r.site}{r.url}{r.username}{r.strength}{r.row}{r.has_password}"
                for r in records]
        return out

    def test_no_password_ever_appears_in_derived_output(self):
        plan = run_import_analysis(VALID_CSV)
        blob = "\n".join(self._all_derived_strings(plan)).lower()
        for secret in SECRETS:
            assert secret.lower() not in blob, f"leaked {secret!r}"
        assert "hunter2" not in blob

    def test_report_text_is_human_actionable(self):
        text = run_import_analysis(VALID_CSV).to_text()
        assert "Accounts: 4" in text
        assert "Add manually" in text
        assert "Weak passwords to replace" in text
        assert "Duplicates to merge" in text
        assert "guidance only" in text


class TestToolPath:
    def _service(self, logger, handler=None) -> ToolExecutionService:
        registry = ToolRegistry()
        registry.register_many(build_orbit_tools())
        permissions = PermissionEngine(
            logger, mode="agent", confirmation_handler=handler,
            fail_closed_risky=True,
        )
        return ToolExecutionService(
            registry=registry,
            permissions=permissions,
            decision_logger=logger,
            mode="agent",
        )

    @staticmethod
    def _run(service, name, args, trace="g11", session="s11"):
        return asyncio.run(service.execute_tool(
            ToolCall(name=name, arguments=args, id="call-g11"),
            trace_id=trace, session_id=session,
        ))

    def test_tool_is_low_risk_and_returns_masked_plan(self):
        registry = ToolRegistry()
        registry.register_many(build_orbit_tools())
        tool = registry.get("orbit.import_passwords")
        assert tool is not None
        assert tool.risk == "low"
        assert tool.is_destructive is False

        logger = DecisionLogger()
        result = self._run(self._service(logger), "orbit.import_passwords",
                           {"csv": VALID_CSV})
        assert result.success is True
        assert result.output.startswith("Password import plan")
        for secret in SECRETS:
            assert secret not in result.output

    def test_missing_csv_fails_with_validation_error(self):
        logger = DecisionLogger()
        result = self._run(self._service(logger), "orbit.import_passwords", {})
        assert result.success is False
        assert "csv is required" in result.error

    def test_bad_header_fails_with_validation_error(self):
        logger = DecisionLogger()
        result = self._run(self._service(logger), "orbit.import_passwords",
                           {"csv": "site,username,password\nx,alice,pw\n"})
        assert result.success is False
        assert "url" in result.error

    def test_audit_never_stores_password_values(self):
        logger = DecisionLogger()
        result = self._run(self._service(logger), "orbit.import_passwords",
                           {"csv": VALID_CSV})
        assert result.success is True
        logger.flush()
        rows = logger.audit.query_trace(trace_id="g11")
        assert rows and rows[0]["tool"] == "orbit.credentials"
        assert rows[0]["allowed"] == 1
        blob = "\n".join(str(r) for r in rows).lower()
        for secret in SECRETS:
            assert secret.lower() not in blob, f"password leaked to audit {secret!r}"
        assert re.fullmatch(r"[0-9a-f]{12}", rows[0]["params_hash"])