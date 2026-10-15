"""Metacognition self-critique + verification-gate merge tests."""

from __future__ import annotations

from core.agent.metacognition import (
    CritiqueFinding,
    CritiqueReport,
    FindingSeverity,
    SelfCritique,
)
from core.agent.verification import VerificationReport, VerificationResult


class TestSelfCritique:
    def test_clean_answer_passes(self):
        report = SelfCritique().critique(
            goal="Explain how the router works",
            final_output="The router walks the fallback chain and records health.",
        )
        assert report.passed
        assert report.findings == ()
        assert report.confidence == 1.0

    def test_empty_output_without_work_is_warning(self):
        report = SelfCritique().critique(goal="say hi", final_output="   ")
        assert report.passed  # non-blocking
        assert [f.severity for f in report.findings] == [FindingSeverity.WARNING]

    def test_empty_output_after_work_is_blocking(self):
        report = SelfCritique().critique(
            goal="create a file",
            final_output="",
            tool_calls=[{"name": "filesystem.write"}],
        )
        assert not report.passed
        assert report.blocking[0].kind == "empty_output"

    def test_unfulfilled_promise_flagged(self):
        report = SelfCritique().critique(
            goal="fix the bug",
            final_output="I've reviewed the code. I will now apply the fix.",
        )
        kinds = {f.kind for f in report.findings}
        assert "unfulfilled_promise" in kinds
        assert report.passed  # warning only

    def test_placeholder_flagged(self):
        report = SelfCritique().critique(
            goal="implement login", final_output="Added the handler. TODO: wire the DB.",
        )
        assert any(f.kind == "unresolved_placeholder" for f in report.findings)

    def test_error_in_output_warning_then_blocking_strict(self):
        out = "Traceback (most recent call last):\n  ...\nValueError"
        lenient = SelfCritique().critique(goal="fix it", final_output=out)
        strict = SelfCritique(strict=True).critique(goal="fix it", final_output=out)
        assert lenient.passed
        assert not strict.passed
        assert any(f.kind == "error_in_output" for f in strict.blocking)

    def test_claimed_success_without_action(self):
        report = SelfCritique().critique(
            goal="implement feature X",
            final_output="Done — feature X is implemented.",
        )
        assert any(f.kind == "claimed_success_without_action" for f in report.findings)
        assert report.passed  # warning non-strict

    def test_unbalanced_code_fence(self):
        report = SelfCritique().critique(
            goal="write a script",
            final_output="Here:\n```python\nprint('hi')\n",
        )
        assert any(f.kind == "unbalanced_code_fence" for f in report.findings)

    def test_unacknowledged_errors(self):
        report = SelfCritique().critique(
            goal="run the tests",
            final_output="All good, everything works.",
            errors=["pytest: collection failed on test_x"],
        )
        assert any(f.kind == "unacknowledged_errors" for f in report.findings)

    def test_to_dict_shape(self):
        report = SelfCritique().critique(goal="x", final_output="")
        data = report.to_dict()
        assert set(data) >= {"passed", "confidence", "blocking", "warnings", "findings"}


class TestVerificationMerge:
    def test_merged_appends_and_recounts(self):
        base = VerificationReport(
            results=(VerificationResult(step_name="tests", passed=True, duration_ms=10.0),),
            all_passed=True, steps_run=1, steps_passed=1, total_duration_ms=10.0,
        )
        merged = base.merged(VerificationResult(step_name="self_critique", passed=True))
        assert merged.steps_run == 2 and merged.steps_passed == 2
        assert merged.all_passed

    def test_failing_critique_fails_report(self):
        base = VerificationReport(all_passed=True)
        merged = base.merged(VerificationResult(step_name="self_critique", passed=False))
        assert not merged.all_passed
        assert merged.critique is None

    def test_critique_field_round_trips(self):
        report = SelfCritique().critique(goal="x", final_output="")
        base = VerificationReport(critique=report.to_dict())
        merged = base.merged(VerificationResult(step_name="self_critique", passed=False))
        assert merged.critique is not None
        assert merged.critique["passed"] is True  # non-blocking findings

    def test_critique_report_summary_bounded(self):
        findings = tuple(
            CritiqueFinding(kind=f"k{i}", severity=FindingSeverity.WARNING, message=f"m{i}")
            for i in range(10)
        )
        report = CritiqueReport(findings=findings)
        assert len(report.summary(limit=3).splitlines()) == 3
