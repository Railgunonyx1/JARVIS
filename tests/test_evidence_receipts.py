"""Round 16 — optimization-evidence receipts (hotspot -> delta -> gate).

Hermetic. Proves the sign-correct delta math, deterministic verdicts
(supported/refuted/inconclusive), content-addressed sealing with tamper
detection, idempotent persistence, deterministic hotspot ranking, and the
post-execution verification gate that binds claims to receipts.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from benchmark.receipts import (
    HIGHER_IS_BETTER,
    LOWER_IS_BETTER,
    EvidenceReceipt,
    ReceiptConflict,
    SeriesSummary,
    build_receipt,
    compare_series,
    content_digest,
    load_receipt,
    rank_hotspots,
    verify_receipt,
    write_receipt,
)
from core.agent.verification import VerificationReport, verify_optimization_evidence

BASE = [100.0] * 50
BETTER = [90.0] * 50
WORSE = [110.0] * 50
TINY = [99.5] * 50


class TestDeltaMath:
    def test_lower_is_better_improvement_sign(self):
        rec = build_receipt("orbit.dispatch_ms", BASE, BETTER)
        assert rec.ratio == pytest.approx(0.9)
        assert rec.improvement == pytest.approx(0.1)
        assert rec.verdict == "supported"

    def test_regression_never_reads_as_improvement(self):
        rec = build_receipt("orbit.dispatch_ms", BASE, WORSE)
        assert rec.improvement == pytest.approx(-0.1)
        assert rec.verdict == "refuted"

    def test_higher_is_better_direction(self):
        good = build_receipt("cache.hit_rate", [10.0] * 20, [12.0] * 20,
                             direction=HIGHER_IS_BETTER)
        assert good.improvement == pytest.approx(0.2)
        assert good.verdict == "supported"
        bad = build_receipt("cache.hit_rate", [10.0] * 20, [9.0] * 20,
                            direction=HIGHER_IS_BETTER)
        assert bad.improvement == pytest.approx(-0.1)
        assert bad.verdict == "refuted"

    def test_min_effect_boundary(self):
        tiny = build_receipt("orbit.memory_ms", BASE, TINY)
        assert tiny.improvement == pytest.approx(0.005)
        assert tiny.verdict == "inconclusive"
        noisy = build_receipt("orbit.memory_ms", BASE, TINY, min_effect=0.0)
        assert noisy.verdict == "supported"

    def test_zero_threshold_less_than_min_effect_boundary(self):
        zero = build_receipt("orbit.memory_ms", BASE, BASE)
        assert zero.improvement == 0.0
        assert zero.verdict == "inconclusive"

    def test_empty_or_unmatched_series_inconclusive(self):
        assert build_receipt("orbit.memory_ms", [], BETTER).verdict == "inconclusive"
        assert build_receipt("orbit.memory_ms", BASE, []).verdict == "inconclusive"

    def test_incomplete_measurement_inconclusive(self):
        rec = build_receipt("orbit.memory_ms", BASE, BETTER, candidate_complete=False)
        assert rec.verdict == "inconclusive"
        assert "measurement incomplete" in rec.limitations

    def test_direction_mismatch_raises(self):
        base = SeriesSummary.from_samples("x", BASE, LOWER_IS_BETTER)
        cand = SeriesSummary.from_samples("x", BETTER, HIGHER_IS_BETTER)
        with pytest.raises(ValueError):
            compare_series(base, cand)

    def test_unknown_direction_raises(self):
        with pytest.raises(ValueError):
            SeriesSummary.from_samples("x", BASE, "sideways")


class TestSealing:
    def test_receipt_id_is_content_addressed_ignoring_created_at(self):
        first = build_receipt("h", BASE, BETTER, created_at="2020-01-01T00:00:00Z")
        second = build_receipt("h", BASE, BETTER, created_at="2026-06-06T06:06:06Z")
        assert first.receipt_id == second.receipt_id
        assert first.content_sha256 == second.content_sha256
        assert first.created_at != second.created_at

    def test_different_evidence_different_id(self):
        a = build_receipt("h", BASE, BETTER)
        b = build_receipt("h", BASE, WORSE)
        assert a.receipt_id != b.receipt_id
        assert a.content_sha256 != b.content_sha256

    def test_verify_sealed_receipt_ok(self):
        rec = build_receipt("h", BASE, BETTER)
        assert content_digest(rec) == rec.content_sha256
        verify_receipt(rec)

    def test_unsealed_receipt_conflicts(self):
        rec = build_receipt("h", BASE, BETTER)
        with pytest.raises(ReceiptConflict):
            verify_receipt(dataclasses.replace(rec, content_sha256=""))

    def test_forged_receipt_id_conflicts(self):
        rec = build_receipt("h", BASE, BETTER)
        forged = dataclasses.replace(rec, receipt_id="rcpt-0000000000000000")
        with pytest.raises(ReceiptConflict):
            verify_receipt(forged)


class TestPersistence:
    def test_roundtrip_and_idempotent_write(self, tmp_path):
        rec = build_receipt("h", BASE, BETTER, change="commit abc123")
        path = write_receipt(rec, tmp_path)
        assert path.name == f"{rec.receipt_id}.json"
        loaded = load_receipt(path)
        assert loaded.receipt_id == rec.receipt_id
        assert loaded.verdict == rec.verdict
        assert loaded.change == "commit abc123"
        assert loaded.limitations == rec.limitations
        assert write_receipt(rec, tmp_path) == path
        assert len(list(tmp_path.glob("*.json"))) == 1

    def test_tampered_receipt_rejected_on_load(self, tmp_path):
        rec = build_receipt("h", BASE, BETTER)
        path = write_receipt(rec, tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["candidate"]["mean"] = 1.0
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ReceiptConflict):
            load_receipt(path)

    def test_malformed_json_rejected(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError):
            load_receipt(path)


class TestHotspotRanking:
    def test_worst_first_lower_is_better(self):
        metrics = {"b": 2.0, "a": 2.0, "c": 5.0}
        assert rank_hotspots(metrics) == ["c", "a", "b"]

    def test_smallest_first_higher_is_better(self):
        metrics = {"b": 2.0, "a": 2.0, "c": 5.0}
        assert rank_hotspots(metrics, HIGHER_IS_BETTER) == ["a", "b", "c"]

    def test_unknown_direction_raises(self):
        with pytest.raises(ValueError):
            rank_hotspots({}, "diagonal")


class TestVerificationGate:
    def test_supported_receipt_passes(self):
        rec = build_receipt("orbit.dispatch_ms", BASE, BETTER)
        result = verify_optimization_evidence(rec)
        assert result.passed is True
        assert result.exit_code == 0
        assert "improved" in result.summary
        assert "orbit.dispatch_ms" in result.summary

    def test_receipt_path_accepted(self, tmp_path):
        rec = build_receipt("orbit.dispatch_ms", BASE, BETTER)
        path = write_receipt(rec, tmp_path)
        assert verify_optimization_evidence(path).passed is True
        assert verify_optimization_evidence(str(path)).passed is True

    def test_refuted_receipt_fails_with_evidence(self):
        rec = build_receipt("orbit.dispatch_ms", BASE, WORSE)
        result = verify_optimization_evidence(rec)
        assert result.passed is False
        assert result.exit_code == 1
        assert "refuted" in result.summary
        assert "orbit.dispatch_ms" in result.error

    def test_inconclusive_receipt_fails(self):
        rec = build_receipt("orbit.dispatch_ms", BASE, TINY)
        result = verify_optimization_evidence(rec)
        assert result.passed is False
        assert "inconclusive" in result.summary

    def test_below_required_threshold_fails(self):
        rec = build_receipt("orbit.dispatch_ms", BASE, BETTER)
        result = verify_optimization_evidence(rec, min_improvement=0.5)
        assert result.passed is False
        assert "below required" in result.summary

    def test_missing_receipt_fails_closed(self, tmp_path):
        result = verify_optimization_evidence(tmp_path / "absent.json")
        assert result.passed is False
        assert "no evidence receipt" in result.summary

    def test_tampered_receipt_fails_integrity(self, tmp_path):
        rec = build_receipt("orbit.dispatch_ms", BASE, BETTER)
        path = write_receipt(rec, tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["improvement"] = 9.99
        path.write_text(json.dumps(data), encoding="utf-8")
        result = verify_optimization_evidence(path)
        assert result.passed is False
        assert "integrity" in result.summary

    def test_unsealed_object_fails_integrity(self):
        rec = build_receipt("orbit.dispatch_ms", BASE, BETTER)
        result = verify_optimization_evidence(dataclasses.replace(rec, content_sha256=""))
        assert result.passed is False
        assert "integrity" in result.summary

    def test_gate_result_merges_into_report(self):
        good = verify_optimization_evidence(build_receipt("h", BASE, BETTER))
        bad = verify_optimization_evidence(build_receipt("h", BASE, WORSE))
        report = VerificationReport().merged(good).merged(bad)
        assert report.steps_run == 2
        assert report.steps_passed == 1
        assert report.all_passed is False
        assert report.to_dict()["results"][0]["name"] == "optimization_evidence"


class TestReceiptModelEdges:
    def test_receipt_dict_roundtrip(self):
        rec = build_receipt("h", BASE, BETTER, change="c1", limitations=("custom",))
        clone = EvidenceReceipt.from_dict(rec.to_dict())
        assert clone == rec
        assert "custom" in clone.limitations
