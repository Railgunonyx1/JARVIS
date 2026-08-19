"""Sprint 20E -- VerificationEngine: post-execution verification.

Runs verification steps after tool execution to catch regressions.
Controlled by the harness (enable_verification=True).

Verification steps:
- Run project tests if test command is known
- Run lint if configured
- Run typecheck if configured
- Check for expected output patterns
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("jarvis.verification")


@dataclass(frozen=True)
class VerificationStep:
    name: str
    command: str
    timeout_seconds: int = 120
    success_exit_codes: tuple[int, ...] = (0,)


@dataclass
class VerificationResult:
    """Structured result of a single verification step.

    Provides bounded failure context for agent recovery:
    enough evidence to fix, but not enough to overflow the context window.
    """
    step_name: str = ""
    passed: bool = False
    exit_code: int = -1
    command: str = ""
    stdout: str = ""
    stderr: str = ""
    summary: str = ""  # bounded summary for recovery context
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class VerificationReport:
    results: tuple[VerificationResult, ...] = ()
    all_passed: bool = True
    total_duration_ms: float = 0.0
    steps_run: int = 0
    steps_passed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "steps_run": self.steps_run,
            "steps_passed": self.steps_passed,
            "total_duration_ms": round(self.total_duration_ms, 1),
            "results": [
                {
                    "name": r.step_name,
                    "passed": r.passed,
                    "exit_code": r.exit_code,
                    "duration_ms": round(r.duration_ms, 1),
                    "error": r.error or r.stderr[:200] if not r.passed else "",
                }
                for r in self.results
            ],
        }


class VerificationEngine:
    """Runs verification steps after execution.

    The harness specifies which steps to run.  Each step is a shell
    command that must exit 0 to pass.
    """

    def __init__(self, project_root: str = ""):
        self._project_root = project_root
        self._steps: list[VerificationStep] = []

    def add_step(self, step: VerificationStep) -> None:
        self._steps.append(step)

    def configure_defaults(self, has_tests: bool = True, has_lint: bool = False,
                           has_typecheck: bool = False) -> None:
        """Auto-configure common verification steps."""
        self._steps.clear()
        if has_tests:
            self._steps.append(VerificationStep(
                name="tests",
                command="python -m pytest tests/ -x -q --tb=short",
                timeout_seconds=300,
            ))
        if has_lint:
            self._steps.append(VerificationStep(
                name="lint",
                command="python -m ruff check .",
                timeout_seconds=60,
            ))
        if has_typecheck:
            self._steps.append(VerificationStep(
                name="typecheck",
                command="python -m mypy . --ignore-missing-imports",
                timeout_seconds=120,
            ))

    async def verify(self, steps: list[VerificationStep] | None = None) -> VerificationReport:
        """Run verification steps and return a report."""
        to_run = steps or self._steps
        if not to_run:
            return VerificationReport()

        results = []
        all_passed = True
        total_start = time.perf_counter()

        for step in to_run:
            result = await self._run_step(step)
            results.append(result)
            if not result.passed:
                all_passed = False
                break  # Stop on first failure

        total_ms = (time.perf_counter() - total_start) * 1000
        passed = sum(1 for r in results if r.passed)

        return VerificationReport(
            results=tuple(results),
            all_passed=all_passed,
            total_duration_ms=total_ms,
            steps_run=len(results),
            steps_passed=passed,
        )

    async def _run_step(self, step: VerificationStep) -> VerificationResult:
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                step.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=step.timeout_seconds,
                cwd=self._project_root or None,
                check=False,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            passed = proc.returncode in step.success_exit_codes
            # Build bounded summary for recovery context
            summary = ""
            if not passed:
                err_text = (proc.stderr or proc.stdout or "")[:300]
                summary = f"{step.name} failed (exit {proc.returncode}): {err_text}"
            return VerificationResult(
                step_name=step.name,
                passed=passed,
                exit_code=proc.returncode,
                command=step.command,
                stdout=proc.stdout[:2000],
                stderr=proc.stderr[:2000],
                summary=summary,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start) * 1000
            return VerificationResult(
                step_name=step.name, passed=False,
                command=step.command,
                error=f"Timed out after {step.timeout_seconds}s",
                summary=f"{step.name} timed out after {step.timeout_seconds}s",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            return VerificationResult(
                step_name=step.name, passed=False,
                command=step.command,
                error=str(e)[:500],
                summary=f"{step.name} error: {str(e)[:200]}",
                duration_ms=duration_ms,
            )
