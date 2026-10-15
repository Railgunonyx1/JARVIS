"""Metacognition — deterministic self-critique that feeds the verification gate.

The verification gate (``core/agent/verification.py``) runs external checks
(tests, lint). This module adds an *internal* check: the agent critiques its own
final answer against the goal and the work it actually performed, and the
critique is merged into the same post-execution ``VerificationReport``.

The critique is deterministic (no extra LLM call, no latency/cost surprise) and
conservative: findings are advisory by default so a legitimate answer never
forces a recovery loop. Only unambiguous defects are BLOCKING — and only in
``strict`` mode do heuristic findings escalate to blocking. A future LLM-backed
critic can emit BLOCKING findings through the same structure.

Failure classes stay deterministic (see ``core/agent/state.py``); this module
never invents a new one — a blocking critique simply fails the verification
gate, exactly like a failing test step.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = [
    "FindingSeverity",
    "CritiqueFinding",
    "CritiqueReport",
    "SelfCritique",
]


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


_ACTION_VERBS: tuple[str, ...] = (
    "implement", "create", "add", "fix", "write", "refactor", "build",
    "update", "remove", "delete", "migrate", "generate", "edit", "modify",
    "change", "install", "configure", "set up", "setup", "rename", "move",
)

_SUCCESS_CLAIMS: tuple[str, ...] = (
    "done", "completed", "implemented", "created", "fixed", "added",
    "updated", "refactored", "i've", "i have", "successfully",
)

_PROMISE_MARKERS: tuple[str, ...] = (
    "i will", "i'll", "i am going to", "i'm going to",
    "next, i", "now i will", "let me now", "next i will",
)

_PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "todo:", "fixme", "not implemented", "<insert", "your code here",
    "placeholder for",
)

_ERROR_MARKERS: tuple[str, ...] = (
    "traceback (most recent call last)",
    "command not found",
    "permission denied",
)


@dataclass(frozen=True)
class CritiqueFinding:
    kind: str
    severity: FindingSeverity
    message: str
    evidence: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "severity": self.severity.value,
            "message": self.message,
            "evidence": self.evidence[:200],
        }


@dataclass
class CritiqueReport:
    findings: tuple[CritiqueFinding, ...] = ()
    confidence: float = 1.0

    @property
    def blocking(self) -> tuple[CritiqueFinding, ...]:
        return tuple(f for f in self.findings if f.severity is FindingSeverity.BLOCKING)

    @property
    def warnings(self) -> tuple[CritiqueFinding, ...]:
        return tuple(f for f in self.findings if f.severity is FindingSeverity.WARNING)

    @property
    def passed(self) -> bool:
        return not self.blocking

    def summary(self, limit: int = 5) -> str:
        """Bounded, human-readable summary of the most severe findings."""
        ordered = list(self.blocking) + list(self.warnings)
        if not ordered:
            return ""
        lines = [f"- {f.message}" for f in ordered[:limit]]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "confidence": round(self.confidence, 2),
            "blocking": [f.to_dict() for f in self.blocking],
            "warnings": [f.to_dict() for f in self.warnings],
            "findings": [f.to_dict() for f in self.findings],
        }


class SelfCritique:
    """Deterministic self-critique of a completed agent turn.

    ``strict`` escalates heuristic findings (error text, success-claim with no
    action) from WARNING to BLOCKING. Default is non-strict so ordinary answers
    never fail the gate; unambiguous defects are blocking in either mode.
    """

    def __init__(self, *, strict: bool = False) -> None:
        self._strict = strict

    def critique(
        self,
        *,
        goal: str = "",
        final_output: str = "",
        tool_calls: Any = (),
        files_changed: Any = (),
        errors: Any = (),
    ) -> CritiqueReport:
        output = (final_output or "").strip()
        tool_calls = list(tool_calls or ())
        files_changed = list(files_changed or ())
        errors = list(errors or ())

        findings: list[CritiqueFinding] = []

        did_work = bool(tool_calls or files_changed)
        actionable_goal = self._is_actionable(goal)

        # 1. Empty final answer after doing work is unambiguously deficient.
        if not output:
            severity = (
                FindingSeverity.BLOCKING if did_work else FindingSeverity.WARNING
            )
            findings.append(CritiqueFinding(
                kind="empty_output",
                severity=severity,
                message="final answer is empty",
                evidence=f"tool_calls={len(tool_calls)} files_changed={len(files_changed)}",
            ))
            return self._finalize(findings, base_confidence=0.3)

        # 2. Answer ends mid-plan with a promise instead of a result.
        if self._ends_with_promise(output):
            findings.append(CritiqueFinding(
                kind="unfulfilled_promise",
                severity=self._escalate(),
                message="answer ends with a promise of future action, not a result",
                evidence=self._last_line(output),
            ))

        # 3. Unfilled scaffold markers in the answer.
        marker = self._find_marker(output, _PLACEHOLDER_MARKERS)
        if marker:
            findings.append(CritiqueFinding(
                kind="unresolved_placeholder",
                severity=FindingSeverity.WARNING,
                message=f"answer contains an unresolved placeholder ({marker!r})",
                evidence=marker,
            ))

        # 4. Raw error/traceback text surfaced without resolution.
        err_marker = self._find_marker(output, _ERROR_MARKERS)
        if err_marker:
            findings.append(CritiqueFinding(
                kind="error_in_output",
                severity=self._escalate(),
                message=f"answer surfaces an unresolved failure ({err_marker!r})",
                evidence=err_marker,
            ))

        # 5. Claims success on an actionable goal but performed no action.
        if actionable_goal and not did_work and self._claims_success(output):
            findings.append(CritiqueFinding(
                kind="claimed_success_without_action",
                severity=self._escalate(),
                message="answer claims completion but no tool ran and no file changed",
                evidence=self._first_success_claim(output),
            ))

        # 6. Unbalanced code fence — answer was cut off mid-block.
        if output.count("```") % 2 == 1:
            findings.append(CritiqueFinding(
                kind="unbalanced_code_fence",
                severity=self._escalate(),
                message="answer contains an unbalanced code fence (possible truncation)",
            ))

        # 7. Prior errors in state that the answer never acknowledges.
        if errors and not self._mentions_any(output, errors):
            findings.append(CritiqueFinding(
                kind="unacknowledged_errors",
                severity=FindingSeverity.WARNING,
                message=f"{len(errors)} prior error(s) recorded but not addressed in the answer",
                evidence=str(errors[-1])[:200],
            ))

        return self._finalize(findings, base_confidence=1.0)

    # ── helpers ────────────────────────────────────────────────────────

    def _escalate(self) -> FindingSeverity:
        return FindingSeverity.BLOCKING if self._strict else FindingSeverity.WARNING

    @staticmethod
    def _is_actionable(goal: str) -> bool:
        low = (goal or "").lower()
        return any(v in low for v in _ACTION_VERBS)

    @staticmethod
    def _claims_success(output: str) -> bool:
        low = output.lower()
        return any(c in low for c in _SUCCESS_CLAIMS)

    @staticmethod
    def _first_success_claim(output: str) -> str:
        low = output.lower()
        for c in _SUCCESS_CLAIMS:
            idx = low.find(c)
            if idx >= 0:
                return output[max(0, idx - 20):idx + len(c) + 20]
        return ""

    @staticmethod
    def _find_marker(output: str, markers: tuple[str, ...]) -> str:
        low = output.lower()
        for m in markers:
            if m in low:
                return m
        return ""

    @staticmethod
    def _last_line(output: str) -> str:
        lines = [ln for ln in output.splitlines() if ln.strip()]
        return lines[-1].strip()[:200] if lines else ""

    @staticmethod
    def _ends_with_promise(output: str) -> bool:
        last = SelfCritique._last_line(output).lower()
        return any(last.startswith(m) or f". {m}" in last for m in _PROMISE_MARKERS)

    @staticmethod
    def _mentions_any(output: str, errors: list) -> bool:
        low = output.lower()
        for e in errors:
            token = str(e).strip().lower()[:24]
            if token and token in low:
                return True
        return False

    @staticmethod
    def _finalize(findings: list[CritiqueFinding], base_confidence: float) -> CritiqueReport:
        weights = {FindingSeverity.BLOCKING: 0.4, FindingSeverity.WARNING: 0.15,
                   FindingSeverity.INFO: 0.05}
        penalty = sum(weights[f.severity] for f in findings)
        confidence = max(0.0, min(1.0, base_confidence - penalty))
        return CritiqueReport(findings=tuple(findings), confidence=confidence)
