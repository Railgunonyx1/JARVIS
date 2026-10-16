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

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark.receipts import (
    EvidenceReceipt,
    ReceiptConflict,
    load_receipt,
    verify_receipt,
)

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
    critique: dict[str, Any] | None = None

    def merged(self, result: VerificationResult) -> VerificationReport:
        """Return a new report with ``result`` appended (used by self-critique)."""
        results = (*self.results, result)
        passed = sum(1 for r in results if r.passed)
        return VerificationReport(
            results=results,
            all_passed=self.all_passed and result.passed,
            total_duration_ms=self.total_duration_ms + result.duration_ms,
            steps_run=len(results),
            steps_passed=passed,
            critique=self.critique,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "steps_run": self.steps_run,
            "steps_passed": self.steps_passed,
            "total_duration_ms": round(self.total_duration_ms, 1),
            "critique": self.critique,
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
                # Continue running all steps to collect all failures

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
        proc = None
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            proc = await asyncio.create_subprocess_shell(
                step.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._project_root or None,
                creationflags=creationflags,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=step.timeout_seconds,
            )
            stdout = (stdout_bytes or b"").decode(errors="replace")
            stderr = (stderr_bytes or b"").decode(errors="replace")
            duration_ms = (time.perf_counter() - start) * 1000
            passed = proc.returncode in step.success_exit_codes
            summary = ""
            if not passed:
                err_text = (stderr or stdout or "")[:300]
                summary = f"{step.name} failed (exit {proc.returncode}): {err_text}"
            return VerificationResult(
                step_name=step.name,
                passed=passed,
                exit_code=proc.returncode or -1,
                command=step.command,
                stdout=stdout[:2000],
                stderr=stderr[:2000],
                summary=summary,
                duration_ms=duration_ms,
            )
        except TimeoutError:
            duration_ms = (time.perf_counter() - start) * 1000
            if proc is not None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            return VerificationResult(
                step_name=step.name, passed=False,
                command=step.command,
                error=f"Timed out after {step.timeout_seconds}s",
                summary=f"{step.name} timed out after {step.timeout_seconds}s",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            if proc is not None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            return VerificationResult(
                step_name=step.name, passed=False,
                command=step.command,
                error=str(e)[:500],
                summary=f"{step.name} error: {str(e)[:200]}",
                duration_ms=duration_ms,
            )


EVIDENCE_STEP_NAME = "optimization_evidence"


def verify_optimization_evidence(receipt: EvidenceReceipt | str | Path,
                                 min_improvement: float = 0.0) -> VerificationResult:
    """Post-execution gate for optimization claims (flameox receipt rule).

    An optimization claim must carry a sealed receipt tying it to a hotspot
    and a measured before/after delta.  Missing, tampered, refuted, or
    below-threshold evidence fails the step with bounded recovery context;
    a supported receipt passes and reports the measured improvement.
    """
    start = time.perf_counter()

    def _fail(error: str, summary: str) -> VerificationResult:
        return VerificationResult(
            step_name=EVIDENCE_STEP_NAME, passed=False, exit_code=1,
            error=error[:500], summary=summary[:300],
            duration_ms=(time.perf_counter() - start) * 1000,
        )

    if isinstance(receipt, (str, Path)):
        try:
            loaded = load_receipt(receipt)
        except FileNotFoundError:
            return _fail(
                f"no evidence receipt at {receipt}",
                f"{EVIDENCE_STEP_NAME}: no evidence receipt at {receipt} — "
                "optimization claims require hotspot -> measured delta -> receipt",
            )
        except ReceiptConflict as exc:
            return _fail(f"receipt integrity failure: {exc}",
                         f"{EVIDENCE_STEP_NAME}: receipt integrity failure — {exc}")
        except (OSError, ValueError) as exc:
            return _fail(f"unreadable receipt: {exc}",
                         f"{EVIDENCE_STEP_NAME}: unreadable receipt — {exc}")
    else:
        loaded = receipt
        try:
            verify_receipt(loaded)
        except ReceiptConflict as exc:
            return _fail(f"receipt integrity failure: {exc}",
                         f"{EVIDENCE_STEP_NAME}: receipt integrity failure — {exc}")

    if loaded.verdict != "supported":
        detail = (f"hotspot {loaded.hotspot} verdict={loaded.verdict} "
                  f"improvement={loaded.improvement:+.2%} ratio={loaded.ratio:.3f} "
                  f"receipt={loaded.receipt_id}")
        return _fail(detail, f"{EVIDENCE_STEP_NAME}: optimization {loaded.verdict} — {detail}")

    if loaded.improvement < min_improvement:
        detail = (f"hotspot {loaded.hotspot} improvement {loaded.improvement:.2%} below "
                  f"required {min_improvement:.2%} (receipt={loaded.receipt_id})")
        return _fail(detail, f"{EVIDENCE_STEP_NAME}: {detail}")

    duration_ms = (time.perf_counter() - start) * 1000
    summary = (f"{EVIDENCE_STEP_NAME}: hotspot {loaded.hotspot} improved "
               f"{loaded.improvement:.2%} (ratio {loaded.ratio:.3f}, "
               f"n={loaded.baseline.n}->{loaded.candidate.n}); "
               "association, not causal proof")
    return VerificationResult(
        step_name=EVIDENCE_STEP_NAME, passed=True, exit_code=0,
        summary=summary, duration_ms=duration_ms,
    )
