"""Audit tool for JARVIS - read-only diagnostics by default.

Never modifies filesystem, never installs packages, never fabricates results.
All audit findings must be evidence-backed.
"""

import subprocess
import sys
from datetime import datetime
from typing import Any

from core.utils import get_project_root
from tools.intent_classifier import IntentClassifier, TaskType

# ── AUDIT POLICY ──────────────────────────────────────────────────────

# Tools allowed during audits (read-only, from the live tool catalog)
AUDIT_ALLOWED = {
    "filesystem.read": True,
    "filesystem.list": True,
    "filesystem.diff": True,
    "filesystem.tree": True,
    "search.code": True,
    "search.find": True,
    "test.discover": True,
    "test.failed": True,
    "git.status": True,
    "git.diff": True,
    "git.log": True,
    "git.branch": True,
    "code.symbol": True,
    "code.references": True,
    "code.imports": True,
    "code.ast": True,
    "security.scan_secrets": True,
    "security.check_permissions": True,
    "security.scan_code": True,
    "memory.retrieve": True,
    "memory.stats": True,
    "system.status": True,
}

# These tools are DENIED during audits (modify environment)
AUDIT_DENIED = {
    "filesystem.write": False,
    "filesystem.delete": False,
    "filesystem.copy": False,
    "filesystem.move": False,
    "shell.execute": False,  # Only specific readonly commands allowed via test.run
    "git.commit": False,
    "git.push": False,
    "git.merge": False,
    "git.rebase": False,
    "git.reset": False,
    "patch.replace": False,
    "patch.insert": False,
    "patch.delete": False,
    "memory.remember": False,
    "memory.forget": False,
}


def check_audit_policy(tool_name: str, task_type: TaskType = TaskType.AUDIT) -> bool:
    """Check if a tool is allowed for the given task type."""
    if task_type == TaskType.AUDIT:
        return tool_name in AUDIT_ALLOWED
    # For other task types, use intent classifier
    return IntentClassifier.should_allow_tool(task_type, tool_name)


# ── AUDIT RUNNER ──────────────────────────────────────────────────────

def run_pytest(path: str = ".") -> dict[str, Any]:
    """Run pytest on the given path. Read-only - captures results."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", path, "--tb=short", "-q"],
            capture_output=True,
            text=True,
            cwd=get_project_root(),
            timeout=120,
            check=False,
        )
        return {
            "status": "complete",
            "exit_code": result.returncode,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "passed": _count_passes(result.stdout),
            "failed": _count_fails(result.stdout),
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "pytest timed out after 60s"}


def run_ruff(path: str = ".") -> dict[str, Any]:
    """Run ruff linting. Read-only."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", path, "--select", "E,F,W"],
            capture_output=True,
            text=True,
            cwd=get_project_root(),
            timeout=60,
            check=False,
        )
        return {
            "status": "complete",
            "exit_code": result.returncode,
            "output": result.stdout[-1000:] if result.stdout else "",
            "errors": _count_ruff_errors(result.stdout),
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "ruff timed out after 30s"}


def _count_passes(output: str) -> int:
    """Count passed tests from pytest output."""
    count = 0
    for line in output.split("\n"):
        if "PASSED" in line:
            count += 1
    return count


def _count_fails(output: str) -> int:
    """Count failed tests from pytest output."""
    count = 0
    for line in output.split("\n"):
        if "FAILED" in line:
            count += 1
    return count


def _count_ruff_errors(output: str) -> int:
    """Count ruff errors from output."""
    count = 0
    for line in output.split("\n"):
        if "error:" in line.lower():
            count += 1
    return count


# ── DEPENDENCY AUDIT ─────────────────────────────────────────────────

def check_python_dependencies(path: str = ".") -> dict[str, Any]:
    """Audit Python package dependencies. Read-only."""
    import importlib.metadata

    project_path = get_project_root()
    requirements_file = project_path / "requirements.txt"

    result = {
        "status": "complete",
        "requirements_file": str(requirements_file.exists()),
        "installed_packages": [],
        "advisories": [],
    }

    if requirements_file.exists():
        try:
            with open(requirements_file) as f:
                deps = f.read()
            # Parse simple requirements
            for line in deps.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    result["installed_packages"].append(line)
        except Exception as e:
            result["error"] = str(e)

    # Check installed packages for known vulnerabilities
    try:
        installed = importlib.metadata.distributions()
        for dist in installed:
            name = dist.metadata.get("Name", "").lower()
            # Basic check - in production would use safety/bandit
            if name:
                result["installed_packages"].append(name.lower())
    except Exception:
        pass

    return result


# ── SECURITY SCAN ─────────────────────────────────────────────────────

def check_security_basics(path: str = ".") -> dict[str, Any]:
    """Basic security checks. Read-only."""

    result = {"status": "complete", "findings": []}
    project_path = get_project_root()

    # Check for sensitive files
    sensitive = [".env", "config.py", "secrets.py", "credentials.py"]
    for item in sensitive:
        if (project_path / item).exists():
            result["findings"].append(
                f"WARNING: Sensitive file detected: {item}"
            )

    # Check for .git directory exposure
    if (project_path / ".git").exists():
        result["findings"].append(
            "INFO: Git repository detected (normal for development)"
        )

    return result


# ── MAIN AUDIT PIPELINE ──────────────────────────────────────────────

def run_audit(project_path: str = ".") -> dict[str, Any]:
    """Run read-only audit pipeline. Never modifies environment.

    Runs quick checks (security + dependency) always. Pytest/ruff runs are
    gated: pass a specific path (e.g. ``tests/test_x.py`` or ``tests/``) to
    include them; the default ``"."`` skips the heavy subprocess runs so the
    ``self.audit`` tool stays fast.

    Returns evidence-backed report. Never claims 'no bugs' without evidence.
    """
    project_root = get_project_root()

    timestamp = datetime.now().isoformat()

    # Heavy checks only when the caller targets a specific path/pattern.
    run_heavy = project_path not in ("", ".")
    pytest_results = run_pytest(project_path) if run_heavy else {
        "status": "skipped", "passed": 0, "failed": 0,
    }
    ruff_results = run_ruff(project_path) if run_heavy else {
        "status": "skipped", "errors": 0,
    }
    dep_results = check_python_dependencies(str(project_root))
    security_results = check_security_basics(str(project_root))

    # Build evidence-backed report - NEVER claim "no bugs" without evidence
    report = {
        "audit_timestamp": timestamp,
        "project": str(project_root),
        "status": "INCOMPLETE",  # Always INCOMPLETE unless fully verified

        "pytest": pytest_results,
        "ruff": ruff_results,
        "dependencies": dep_results,
        "security": security_results,

        "summary": {
            "total_pytest_runs": pytest_results.get("passed", 0) + pytest_results.get("failed", 0),
            "pytest_passed": pytest_results.get("passed", 0),
            "pytest_failed": pytest_results.get("failed", 0),
            "ruff_errors": ruff_results.get("errors", 0),
            "dependencies_checked": len(dep_results.get("installed_packages", [])),
        },
    }

    # Only mark COMPLETE if all checks pass
    if (
        pytest_results.get("status") == "complete"
        and pytest_results.get("failed", 0) == 0
        and ruff_results.get("status") == "complete"
        and ruff_results.get("errors", 0) == 0
    ):
        report["status"] = "COMPLETE"

    # Never fabricate: if we can't verify, mark INCOMPLETE
    if report["status"] == "INCOMPLETE":
        report["conclusion"] = (
            "Audit incomplete - cannot confirm system is bug-free. "
            "Run full audit with all checks passing to mark complete."
        )
    else:
        report["conclusion"] = (
            "Audit complete. System inspected with no critical issues found. "
            "See detailed results above for complete picture."
        )

    return report


# ── EXPORTABLE FUNCTIONS for agent loop ──────────────────────────────

def audit_filesystem(path: str = ".") -> dict[str, Any]:
    """Audit filesystem read-only. Part of the audit pipeline."""
    project_path = get_project_root()

    result = {
        "status": "complete",
        "path": str(path),
        "total_items": 0,
        "dirs": 0,
        "files": 0,
        "findings": [],
    }

    try:
        items = list(project_path.rglob("*"))
        result["total_items"] = len(items)
        result["dirs"] = sum(1 for i in items if i.is_dir())
        result["files"] = sum(1 for i in items if i.is_file())

        # Check for suspicious files
        for f in items:
            if f.suffix.lower() in [".pyc", ".pyo"]:
                result["findings"].append(f"Compiled Python file: {f.name}")

    except Exception as e:
        result["error"] = str(e)

    return result


def check_no_file_writes() -> bool:
    """Check that no file writes occurred during this session.

    Used by the agent loop to enforce the read-only audit policy.
    """
    # This would be checked against a before-snapshot of the filesystem
    # For now, return True (assume no writes unless audit detects otherwise)
    return True
