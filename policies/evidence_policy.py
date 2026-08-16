"""Evidence requirement policy for JARVIS agent.

RULE: JARVIS must never claim "no bugs" or "system is bug-free" 
unless an audit actually completed with all checks passing.

Instead:
- If audit COMPLETE: provide evidence summary
- If audit INCOMPLETE: explicitly state what's unknown and why
- Never fabricate audit results
"""

from tools.audit import run_audit
from tools.intent_classifier import TaskType


# ── AUDIT EVIDENCE POLICY ────────────────────────────────────────────

AUDIT_POLICY = {
    "require_evidence": True,
    "never_fabricate_results": True,
    "min_checks_for_complete": {
        "pytest_passing": 0,  # All must pass
        "ruff_errors": 0,  # Zero errors
        "dependencies_audited": True,
    },
    "conclusion_templates": {
        "complete": (
            "AUDIT STATUS: COMPLETE\n\n"
            "Tests: {pytest_passed} passed, {pytest_failed} failed\n"
            "Lint: {ruff_errors} errors found\n"
            "Dependencies: {deps_checked} checked\n"
            "Conclusion: System inspected with issues identified. "
            "See detailed results above."
        ),
        "incomplete": (
            "AUDIT STATUS: INCOMPLETE\n\n"
            "Reason: {reason}\n\n"
            "I cannot conclude that the system is bug-free. "
            "Additional investigation required."
        ),
    },
}


def evaluate_audit_report(report: dict) -> dict:
    """Evaluate an audit report against the evidence policy.
    
    Returns a policy-compliant summary that never fabricates results.
    """
    if report.get("status") == "COMPLETE":
        # Provide evidence-backed summary
        deps = report.get("dependencies", {})
        pytest = report.get("pytest", {})
        ruff = report.get("ruff", {})
        
        summary = {
            "status": "COMPLETE",
            "evidence_provided": True,
            "conclusion": AUDIT_POLICY["conclusion_templates"]["complete"].format(
                pytest_passed=pytest.get("passed", 0),
                pytest_failed=pytest.get("failed", 0),
                ruff_errors=ruff.get("errors", 0),
                deps_checked=deps.get("checked", 0),
            ),
            "details": {
                "pytest_passed": pytest.get("passed", 0),
                "pytest_failed": pytest.get("failed", 0),
                "ruff_errors": ruff.get("errors", 0),
                "dependencies_checked": deps.get("checked", 0),
                "security_findings": report.get("security", {}).get("findings", []),
            },
        }
        
        # But still be honest: if there were any failures, note them
        if pytest.get("failed", 0) > 0:
            summary["conclusion"] += "\nNote: Some tests failed - review detailed results."
        if ruff.get("errors", 0) > 0:
            summary["conclusion"] += "\nNote: Lint errors found - review detailed results."
        
        return summary
    
    # INCOMPLETE case - never fabricate
    elif report.get("status") == "INCOMPLETE":
        reason = report.get("conclusion", "Audit did not complete all checks")
        return {
            "status": "INCOMPLETE",
            "evidence_provided": False,
            "conclusion": AUDIT_POLICY["conclusion_templates"]["incomplete"].format(
                reason=reason,
            ),
            "details": {
                "reason": reason,
                "what_unknown": _get_unknowns(report),
            },
        }
    
    # Fallback - never claim bug-free without evidence
    return {
        "status": "UNKNOWN",
        "evidence_provided": False,
        "conclusion": (
            "Audit could not be completed. Insufficient evidence to "
            "confirm or deny system quality. Run full audit for evaluation."
        ),
        "details": {"issue": "audit_status_unknown"},
    }


def _get_unknowns(report: dict) -> list[str]:
    """List what is unknown about the system quality."""
    unknowns = []
    
    if report.get("status") != "COMPLETE":
        unknowns.append("pytest results not all passing")
    
    if report.get("status") == "INCOMPLETE":
        unknowns.append("audit was marked incomplete")
    
    # Check if specific modules were not run
    if "pytest" not in str(report):
        unknowns.append("pytest not run")
    
    if "ruff" not in str(report):
        unknowns.append("linting not run")
    
    if "dependencies" not in str(report):
        unknowns.append("dependency audit not run")
    
    return unknowns


# ── EXAMPLE USAGE ────────────────────────────────────────────────────

def example_usage():
    """Demonstrate policy-compliant audit evaluation."""
    
    # Case 1: Complete audit with passing tests
    complete_report = {
        "status": "COMPLETE",
        "pytest": {"passed": 188, "failed": 0},
        "ruff": {"errors": 0},
        "dependencies": {"checked": 25},
    }
    result = evaluate_audit_report(complete_report)
    print("=== Case 1: Complete audit ===")
    print(f"Status: {result['status']}")
    print(f"Evidence provided: {result['evidence_provided']}")
    print(f"Conclusion: {result['conclusion'][:80]}...")
    print()
    
    # Case 2: Incomplete audit (some tests failed)
    incomplete_report = {
        "status": "INCOMPLETE",
        "conclusion": "3 tests failed due to timing issues",
    }
    result = evaluate_audit_report(incomplete_report)
    print("=== Case 2: Incomplete audit ===")
    print(f"Status: {result['status']}")
    print(f"Evidence provided: {result['evidence_provided']}")
    print(f"Conclusion: {result['conclusion'][:80]}...")
    print()
    
    # Case 3: Unknown status (audit not run)
    unknown_report = {}
    result = evaluate_audit_report(unknown_report)
    print("=== Case 3: Unknown status ===")
    print(f"Status: {result['status']}")
    print(f"Evidence provided: {result['evidence_provided']}")
    print(f"Conclusion: {result['conclusion'][:80]}...")


if __name__ == "__main__":
    example_usage()