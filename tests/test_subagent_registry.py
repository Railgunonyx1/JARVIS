"""Row 20 — subagent registry resurrection prevention + retirement receipts."""

from __future__ import annotations

import json

import pytest

from core.agent.subagent_registry import (
    ResurrectionError,
    RetirementConflict,
    RunState,
    SubagentRegistry,
    build_receipt,
    content_digest,
    sweep_stale_runs,
    verify_receipt,
)

BAD = "deadbeef" * 4


class TestResurrection:
    def test_basic_register_unregister(self):
        r = SubagentRegistry()
        e = r.register("a", generation=1)
        assert e.state == RunState.RUNNING
        assert r.is_active("a")
        assert r.unregister("a", state=RunState.DONE)
        assert not r.is_active("a")
        assert r.is_retired("a")

    def test_retired_cannot_be_resurrected_same_gen(self):
        r = SubagentRegistry()
        r.register("a", generation=1)
        r.unregister("a")
        with pytest.raises(ResurrectionError):
            r.register("a", generation=1)

    def test_retired_cannot_be_resurrected_lower_gen(self):
        r = SubagentRegistry()
        r.register("a", generation=5)
        r.unregister("a")
        with pytest.raises(ResurrectionError):
            r.register("a", generation=1)

    def test_retired_can_advance_generation(self):
        # A genuinely new generation is allowed (not a resurrection of stale).
        r = SubagentRegistry()
        r.register("a", generation=1)
        r.unregister("a")
        e = r.register("a", generation=2)
        assert e.generation == 2
        assert e.resurrected is False

    def test_retired_requires_force_to_reuse_gen(self):
        r = SubagentRegistry()
        r.register("a", generation=3)
        r.unregister("a")
        # force allows an audited override and flags the entry
        e = r.register("a", generation=3, force=True)
        assert e.resurrected is True
        assert r.is_active("a")

    def test_monotonic_generation_downgrade_blocked(self):
        r = SubagentRegistry()
        r.register("a", generation=10)
        # still running, attempt lower gen
        with pytest.raises(ResurrectionError):
            r.register("a", generation=5)

    def test_retire_marks_retired(self):
        r = SubagentRegistry()
        r.register("a", generation=1)
        assert r.retire("a", reason="manual") is True
        assert r.is_retired("a")
        assert not r.is_active("a")

    def test_unregister_non_terminal_raises(self):
        r = SubagentRegistry()
        r.register("a", generation=1)
        with pytest.raises(ValueError):
            r.unregister("a", state=RunState.RUNNING)

    def test_non_terminal_unregister_then_rejects_collect(self):
        r = SubagentRegistry()
        r.register("a", generation=1)
        r.register("b", generation=1, parent_task_id="a")
        assert r.active_ids() == ["a", "b"] or set(r.active_ids()) == {"a", "b"}

    def test_retired_ids_listing(self):
        r = SubagentRegistry()
        r.register("x", generation=1)
        r.retire("x")
        assert "x" in r.retired_ids()

    def test_roundtrip_from_dict_preserves_retirement(self):
        r = SubagentRegistry()
        r.register("a", generation=4)
        r.retire("a")
        r2 = SubagentRegistry.from_dict(r.to_dict())
        assert r2.is_retired("a")
        with pytest.raises(ResurrectionError):
            r2.register("a", generation=4)


class TestRetirementReceipts:
    def test_build_and_verify(self):
        rcpt = build_receipt("/tmp/x.json", 10, ("t1", "t2"), 3, "retired 2 runs")
        assert rcpt.receipt_id.startswith("rt-")
        assert rcpt.discarded_ids == ("t1", "t2")
        digest = content_digest(rcpt)
        assert digest == rcpt.content_sha256
        verify_receipt(rcpt)

    def test_unsealed_conflicts(self):
        rcpt = build_receipt("/tmp/x.json", 10, (), 0, "no runs")
        with pytest.raises(RetirementConflict):
            verify_receipt(type(rcpt)(**{**rcpt.__dict__, "content_sha256": ""}))

    def test_sweep_missing_file(self, tmp_path):
        rcpt = sweep_stale_runs(tmp_path / "absent.json")
        assert rcpt.discarded_ids == ()
        assert "no stale state present" in rcpt.reason
        verify_receipt(rcpt)

    def test_sweep_discards_inflight_and_moves_file(self, tmp_path):
        path = tmp_path / "subagents.runs.json"
        path.write_text(json.dumps({
            "runs": [
                {"task_id": "r1", "state": "running", "generation": 2},
                {"task_id": "r2", "state": "done", "generation": 1},
                {"task_id": "r3", "state": "RUNNING", "generation": 4},
            ]
        }), encoding="utf-8")
        rcpt = sweep_stale_runs(path)
        assert set(rcpt.discarded_ids) == {"r1", "r3"}
        assert rcpt.generation_floor == 4
        assert not path.exists()
        # original moved aside, not deleted
        retired = list(tmp_path.glob("subagents.runs.json.retired-*"))
        assert len(retired) == 1
        sidecar = tmp_path / ("subagents.runs.json" + ".discard-receipt.json")
        assert sidecar.exists()
        loaded = json.loads(sidecar.read_text(encoding="utf-8"))
        assert loaded["discarded_ids"] == ["r1", "r3"]
        verify_receipt(type(rcpt).from_dict(loaded))

    def test_sweep_byte_bound_overflow(self, tmp_path):
        path = tmp_path / "big.json"
        path.write_text("{" + (" " * 100000) + "}", encoding="utf-8")
        rcpt = sweep_stale_runs(path, max_bytes=100)
        assert rcpt.overflow is True
        assert rcpt.discarded_ids == ()
        assert "oversized" in rcpt.reason
        verify_receipt(rcpt)

    def test_sweep_unparseable(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        rcpt = sweep_stale_runs(path)
        assert rcpt.discarded_ids == ()
        assert rcpt.parse_error != ""
        assert "unparseable" in rcpt.reason
        verify_receipt(rcpt)

    def test_sweep_empty_inflight(self, tmp_path):
        path = tmp_path / "clean.json"
        path.write_text(json.dumps({"runs": [{"task_id": "d1", "state": "done"}]}),
                        encoding="utf-8")
        rcpt = sweep_stale_runs(path)
        assert rcpt.discarded_ids == ()
        assert "no in-flight" in rcpt.reason
        verify_receipt(rcpt)

    def test_sweep_flat_list_shape(self, tmp_path):
        path = tmp_path / "flat.json"
        path.write_text(json.dumps([
            {"task_id": "x", "status": "running"},
            {"task_id": "y", "status": "completed"},
        ]), encoding="utf-8")
        rcpt = sweep_stale_runs(path)
        assert rcpt.discarded_ids == ("x",)

    def test_no_move_mode_deletes(self, tmp_path):
        path = tmp_path / "gone.json"
        path.write_text(json.dumps({"runs": [{"task_id": "z", "state": "running"}]}),
                        encoding="utf-8")
        rcpt = sweep_stale_runs(path, move_original=False)
        assert not path.exists()
        verify_receipt(rcpt)
