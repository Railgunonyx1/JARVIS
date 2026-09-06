"""G9 — Orbit security + audit (hermetic, no browser needed).

Proves the fail-closed gates from G5 are *traceable end-to-end*: every
orbit.* tool run through ToolExecutionService leaves an AuditLog row with the
request verdict, and raw parameters never reach the store (only a hash).
Each test gets an isolated SQLite audit DB via the shared conftest fixture.
"""

from __future__ import annotations

import asyncio
import re

from core.agent.permissions import PermissionEngine
from core.agent.tool_service import ToolExecutionService
from core.decision_logger import DecisionLogger
from providers.types import ToolCall
from tools.registry import ToolRegistry

from orbit import tools as orbit_tools
from orbit.tools import build_orbit_tools


def _service(logger, handler=None) -> ToolExecutionService:
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


async def _run(service, name, args, trace="t9", session="s9"):
    return await service.execute_tool(
        ToolCall(name=name, arguments=args, id="call-1"),
        trace_id=trace, session_id=session,
    )


def _audit_rows(logger, trace="t9"):
    logger.flush()
    return logger.audit.query_trace(trace_id=trace)


class TestAuditTrail:
    def test_allowed_navigation_is_audited(self, monkeypatch):
        logger = DecisionLogger()

        class FakeController:
            def navigate(self, url, tab_id=None):
                return {"url": url, "title": "Example", "tab_id": "tab_x"}

        monkeypatch.setattr(orbit_tools, "get_orbit_controller",
                            lambda *a, **k: FakeController())
        service = _service(logger)
        result = asyncio.run(_run(service, "orbit.navigate",
                                  {"url": "https://example.com/"}))

        assert result.success is True
        rows = _audit_rows(logger)
        assert rows and rows[0]["tool"] == "orbit.browser.open"
        assert rows[0]["allowed"] == 1
        assert rows[0]["success"] == 1
        assert rows[0]["session_id"] == "s9"

    def test_sensitive_denial_is_audited_allowed_zero(self):
        logger = DecisionLogger()
        service = _service(logger)  # no consent channel -> fail closed
        result = asyncio.run(_run(service, "orbit.navigate",
                                  {"url": "https://chase.com/account"}))
        assert result.permission_denied is True
        rows = _audit_rows(logger)
        assert rows and rows[0]["tool"] == "orbit.browser.open"
        assert rows[0]["allowed"] == 0
        assert "sensitive" in (rows[0]["error"] or "").lower()

    def test_high_risk_mutation_denied_without_consent_is_audited(self):
        logger = DecisionLogger()
        service = _service(logger)
        result = asyncio.run(_run(service, "orbit.execute_script",
                                  {"script": "document.title='x'"}))
        assert result.permission_denied is True
        rows = _audit_rows(logger)
        assert rows and rows[0]["tool"] == "orbit.browser.script"
        assert rows[0]["allowed"] == 0

    def test_consent_run_allows_and_audits_high_risk(self, monkeypatch):
        logger = DecisionLogger()

        def approve(tool_name, args):
            return "run"

        service = _service(logger, handler=approve)

        class FakeController:
            def execute_script(self, script, tab_id=None):
                return "document.title='x' executed"

        monkeypatch.setattr(orbit_tools, "get_orbit_controller",
                            lambda *a, **k: FakeController())
        result = asyncio.run(_run(service, "orbit.execute_script",
                                  {"script": "document.title='x'"}))

        assert result.success is True
        rows = _audit_rows(logger)
        assert rows[0]["allowed"] == 1

    def test_raw_params_never_reach_audit_store(self, monkeypatch):
        logger = DecisionLogger()

        class FakeController:
            def navigate(self, url, tab_id=None):
                return {"url": url, "title": "Bank", "tab_id": "tab_x"}

        # Never touch the real controller singleton (hermetic): the raw URL
        # must stay out of the audit store even when navigation succeeds.
        monkeypatch.setattr(orbit_tools, "get_orbit_controller",
                            lambda *a, **k: FakeController())
        service = _service(logger)
        secret_url = "https://checking.bank.example/transfers?to=attacker"
        asyncio.run(_run(service, "orbit.navigate", {"url": secret_url}))
        rows = _audit_rows(logger)
        assert rows
        blob = str(rows[0])
        assert secret_url.split("?")[0] not in blob
        assert re.fullmatch(r"[0-9a-f]{12}", rows[0]["params_hash"])


class TestScanGate:
    def test_forbidden_patterns_are_rejected(self):
        from security.code_scan import FORBIDDEN_CODE_PATTERNS, check_generated_code

        assert len(FORBIDDEN_CODE_PATTERNS) >= 5
        for snippet in ("os.system('rm -rf /')",
                        "import subprocess; subprocess.Popen(['sh'])",
                        "eval(user_input)"):
            try:
                check_generated_code(snippet)
                assert False, f"should have rejected: {snippet}"
            except RuntimeError:
                pass

    def test_benign_code_passes_scan(self):
        from security.code_scan import check_generated_code

        check_generated_code("for i in range(10): print(i)")  # must not raise

    def test_generated_code_off_by_default(self, monkeypatch):
        import security.code_scan as cs

        monkeypatch.delenv("JARVIS_ENABLE_GENERATED_CODE", raising=False)
        assert cs.generated_code_enabled() is False