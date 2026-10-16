"""Optimization-evidence receipts (Round 7 — flameox pattern).

An optimization claim is only accepted with evidence: an identified hotspot,
a measured before/after delta, and a verdict that survives the verification
gate.  Receipts never claim causality — ratios establish association only,
and that limitation is recorded inside the receipt.

Math follows the sign rule from gbrain's trajectory model (``delta =
(new - old) / |old|``) so a worsening metric can never read as an
improvement:

    lower_is_better : improvement = -(new - old) / |old|
    higher_is_better: improvement =  (new - old) / |old|

Receipts are content-addressed: ``receipt_id`` and ``content_sha256`` are
derived from a canonical JSON payload (``created_at`` excluded, like reef's
canonicalized retry content), so re-measuring the same evidence yields the
same id and a hand-edited receipt fails verification on load.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOWER_IS_BETTER = "lower_is_better"
HIGHER_IS_BETTER = "higher_is_better"
DIRECTIONS = (LOWER_IS_BETTER, HIGHER_IS_BETTER)

MIN_EFFECT = 0.02
SCHEMA = "jarvis.evidence_receipt/1"

_BASE_LIMITATIONS = (
    "ratios establish association, not causal improvement",
    "timings are machine-specific unless baseline artifacts are pinned",
)


class ReceiptConflict(ValueError):
    """A receipt's stored content does not match its content hash."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _samples_sha256(samples: Sequence[float]) -> str:
    canonical = json.dumps([float(s) for s in samples], separators=(",", ":"))
    return _sha256(canonical)


@dataclass(frozen=True)
class SeriesSummary:
    """Pre- or post-change measurement series, summarized deterministically."""

    name: str
    direction: str
    n: int
    mean: float
    samples_sha256: str
    complete: bool = True

    @classmethod
    def from_samples(cls, name: str, samples: Sequence[float], direction: str,
                     complete: bool = True) -> SeriesSummary:
        if direction not in DIRECTIONS:
            raise ValueError(f"unknown direction {direction!r}")
        values = [float(s) for s in samples]
        mean = sum(values) / len(values) if values else 0.0
        return cls(name=name, direction=direction, n=len(values), mean=mean,
                   samples_sha256=_samples_sha256(values), complete=complete)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction,
            "n": self.n,
            "mean": self.mean,
            "samples_sha256": self.samples_sha256,
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeriesSummary:
        direction = str(data["direction"])
        if direction not in DIRECTIONS:
            raise ValueError(f"unknown direction {direction!r}")
        return cls(name=str(data["name"]), direction=direction, n=int(data["n"]),
                   mean=float(data["mean"]), samples_sha256=str(data["samples_sha256"]),
                   complete=bool(data.get("complete", True)))


@dataclass(frozen=True)
class EvidenceReceipt:
    """Hotspot -> measured delta -> verdict, sealed with a content hash."""

    receipt_id: str
    hotspot: str
    baseline: SeriesSummary
    candidate: SeriesSummary
    ratio: float
    improvement: float
    verdict: str
    min_effect: float
    limitations: tuple[str, ...]
    change: str = ""
    created_at: str = ""
    content_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "receipt_id": self.receipt_id,
            "hotspot": self.hotspot,
            "change": self.change,
            "baseline": self.baseline.to_dict(),
            "candidate": self.candidate.to_dict(),
            "ratio": self.ratio,
            "improvement": self.improvement,
            "verdict": self.verdict,
            "min_effect": self.min_effect,
            "limitations": list(self.limitations),
            "created_at": self.created_at,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceReceipt:
        return cls(
            receipt_id=str(data["receipt_id"]),
            hotspot=str(data["hotspot"]),
            baseline=SeriesSummary.from_dict(data["baseline"]),
            candidate=SeriesSummary.from_dict(data["candidate"]),
            ratio=float(data["ratio"]),
            improvement=float(data["improvement"]),
            verdict=str(data["verdict"]),
            min_effect=float(data["min_effect"]),
            limitations=tuple(str(x) for x in data.get("limitations", [])),
            change=str(data.get("change", "")),
            created_at=str(data.get("created_at", "")),
            content_sha256=str(data["content_sha256"]),
        )


def compare_series(baseline: SeriesSummary,
                   candidate: SeriesSummary) -> tuple[float, float]:
    """Return ``(improvement, ratio)`` for a series pair (direction-aware)."""
    if baseline.direction != candidate.direction:
        raise ValueError("baseline and candidate directions differ")
    if baseline.n == 0 or candidate.n == 0 or baseline.mean == 0.0:
        return 0.0, 0.0
    ratio = candidate.mean / baseline.mean
    raw = (candidate.mean - baseline.mean) / abs(baseline.mean)
    improvement = -raw if baseline.direction == LOWER_IS_BETTER else raw
    return improvement, ratio


def classify_verdict(improvement: float, baseline: SeriesSummary, candidate: SeriesSummary,
                     min_effect: float) -> str:
    """Deterministic verdict: supported / refuted / inconclusive."""
    if baseline.n == 0 or candidate.n == 0 or baseline.mean == 0.0:
        return "inconclusive"
    if not (baseline.complete and candidate.complete):
        return "inconclusive"
    if improvement < 0.0:
        return "refuted"
    if improvement < min_effect:
        return "inconclusive"
    return "supported"


def _as_summary(value: Sequence[float] | SeriesSummary, name: str, direction: str,
                complete: bool) -> SeriesSummary:
    if isinstance(value, SeriesSummary):
        return value
    return SeriesSummary.from_samples(name=name, samples=value, direction=direction,
                                      complete=complete)


def build_receipt(hotspot: str,
                  baseline: Sequence[float] | SeriesSummary,
                  candidate: Sequence[float] | SeriesSummary,
                  *,
                  direction: str = LOWER_IS_BETTER,
                  change: str = "",
                  min_effect: float = MIN_EFFECT,
                  baseline_complete: bool = True,
                  candidate_complete: bool = True,
                  created_at: str | None = None,
                  limitations: Sequence[str] = ()) -> EvidenceReceipt:
    """Seal a hotspot measurement pair into a content-addressed receipt."""
    base = _as_summary(baseline, hotspot, direction, baseline_complete)
    cand = _as_summary(candidate, hotspot, direction, candidate_complete)
    improvement, ratio = compare_series(base, cand)
    verdict = classify_verdict(improvement, base, cand, min_effect)
    notes = list(_BASE_LIMITATIONS)
    if not (base.complete and cand.complete):
        notes.append("measurement incomplete")
    if base.n == 0 or cand.n == 0:
        notes.append("empty series")
    if verdict == "inconclusive" and 0.0 <= improvement < min_effect:
        notes.append(f"effect below minimum meaningful threshold (min_effect={min_effect:.2%})")
    notes.extend(str(x) for x in limitations)
    stamp = created_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    receipt = EvidenceReceipt(
        receipt_id="", hotspot=hotspot, baseline=base, candidate=cand,
        ratio=ratio, improvement=improvement, verdict=verdict,
        min_effect=min_effect, limitations=tuple(notes), change=change,
        created_at=stamp,
    )
    digest = content_digest(receipt)
    return EvidenceReceipt(
        receipt_id=f"rcpt-{digest[:16]}", hotspot=hotspot, baseline=base,
        candidate=cand, ratio=ratio, improvement=improvement, verdict=verdict,
        min_effect=min_effect, limitations=tuple(notes), change=change,
        created_at=stamp, content_sha256=digest,
    )


def _payload(receipt: EvidenceReceipt) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "hotspot": receipt.hotspot,
        "change": receipt.change,
        "baseline": receipt.baseline.to_dict(),
        "candidate": receipt.candidate.to_dict(),
        "ratio": receipt.ratio,
        "improvement": receipt.improvement,
        "verdict": receipt.verdict,
        "min_effect": receipt.min_effect,
        "limitations": list(receipt.limitations),
    }


def content_digest(receipt: EvidenceReceipt) -> str:
    """Canonical sha256 over everything except ``created_at`` and the seal."""
    canonical = json.dumps(_payload(receipt), sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return _sha256(canonical)


def verify_receipt(receipt: EvidenceReceipt) -> None:
    """Raise :class:`ReceiptConflict` when the seal does not match content."""
    if not receipt.content_sha256:
        raise ReceiptConflict("unsealed receipt (missing content_sha256)")
    digest = content_digest(receipt)
    if digest != receipt.content_sha256:
        raise ReceiptConflict(
            f"content_sha256 mismatch for {receipt.receipt_id}: "
            f"stored {receipt.content_sha256[:12]}… recomputed {digest[:12]}…")
    expected_id = f"rcpt-{digest[:16]}"
    if receipt.receipt_id != expected_id:
        raise ReceiptConflict(
            f"receipt_id {receipt.receipt_id} does not match content ({expected_id})")


def default_receipt_dir() -> Path:
    return Path(__file__).resolve().parent / "receipts"


def write_receipt(receipt: EvidenceReceipt, directory: str | Path | None = None) -> Path:
    """Persist a receipt under ``<directory>/<receipt_id>.json`` (idempotent)."""
    verify_receipt(receipt)
    target_dir = Path(directory) if directory is not None else default_receipt_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{receipt.receipt_id}.json"
    if path.exists():
        existing = load_receipt(path)
        if existing.content_sha256 != receipt.content_sha256:
            raise ReceiptConflict(f"receipt {receipt.receipt_id} exists with different content")
        return path
    path.write_text(json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def load_receipt(path: str | Path) -> EvidenceReceipt:
    """Load and verify a receipt file (raises on tamper or malformed JSON)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ReceiptConflict(f"receipt {path} is not a JSON object")
    receipt = EvidenceReceipt.from_dict(data)
    verify_receipt(receipt)
    return receipt


def rank_hotspots(metrics: dict[str, float], direction: str = LOWER_IS_BETTER) -> list[str]:
    """Deterministic worst-first ranking (ties break on name ascending)."""
    if direction not in DIRECTIONS:
        raise ValueError(f"unknown direction {direction!r}")
    if direction == LOWER_IS_BETTER:
        return sorted(metrics, key=lambda name: (-metrics[name], name))
    return sorted(metrics, key=lambda name: (metrics[name], name))
