"""Row 20 — heartbeat under commitment queues."""

from __future__ import annotations

from core.agent.heartbeat import (
    HEARTBEAT_OK,
    HEARTBEAT_SKIP_BUSY,
    Commitment,
    HeartbeatCoordinator,
)


class TestBeatGating:
    def test_ok_when_idle(self):
        coord = HeartbeatCoordinator()
        ok, reason = coord.should_beat()
        assert ok is True and reason == HEARTBEAT_OK

    def test_skip_busy_and_grace_retry(self):
        busy = {"v": True}
        coord = HeartbeatCoordinator(main_busy_check=lambda: busy["v"], idle_grace=0.5)
        # busy -> skip busy
        ok, reason = coord.should_beat()
        assert ok is False and reason == HEARTBEAT_SKIP_BUSY
        # record the skip (sets grace)
        coord.skip(reason)
        busy["v"] = False
        # still in grace -> skip grace
        ok2, reason2 = coord.should_beat()
        assert ok2 is False and reason2 != HEARTBEAT_SKIP_BUSY
        assert reason2  # named reason

    def test_record_beat_schedules_next(self):
        t = [100.0]
        coord = HeartbeatCoordinator(heartbeat_interval=30.0, now=lambda: t[0])
        ok, _ = coord.should_beat()
        assert ok
        coord.record_beat()
        assert coord.last_beat == 100.0
        assert coord.next_eligible == 130.0
        # not eligible yet
        ok2, _ = coord.should_beat(now=110.0)
        assert ok2 is False
        ok3, _ = coord.should_beat(now=130.0)
        assert ok3 is True

    def test_disabled(self):
        coord = HeartbeatCoordinator()
        coord.disable()
        ok, reason = coord.should_beat()
        assert ok is False
        assert reason  # disabled reason
        coord.enable()
        ok2, _ = coord.should_beat()
        assert ok2 is True

    def test_publisher_receives_events(self):
        events = []
        coord = HeartbeatCoordinator(publisher=lambda n, p: events.append((n, p)))
        coord.record_beat(now=5.0)
        coord.skip("r", now=6.0)
        names = [e[0] for e in events]
        assert "heartbeat.beat" in names
        assert "heartbeat.skipped" in names


class TestCommitments:
    def test_submit_dedupes(self):
        coord = HeartbeatCoordinator()
        a = coord.submit("k1", {"x": 1})
        b = coord.submit("k1", {"x": 2})
        assert a is b
        assert coord.is_duplicate("k1")
        assert len(coord.pending()) == 1

    def test_settle_idempotent_and_uncertain_reported(self):
        coord = HeartbeatCoordinator()
        coord.submit("k2")
        assert coord.settle("k2", "done", uncertain=True) is True
        # second settle is no-op success
        assert coord.settle("k2", "other") is True
        c = coord.get("k2")
        assert c.outcome == "done"
        assert c.uncertain is True
        assert len(coord.report_uncertain()) == 1

    def test_unknown_settle_returns_false(self):
        coord = HeartbeatCoordinator()
        assert coord.settle("nope", "x") is False

    def test_attempt_increments(self):
        coord = HeartbeatCoordinator()
        coord.submit("k3")
        coord.attempt("k3")
        coord.attempt("k3")
        assert coord.get("k3").attempts == 2
        assert coord.attempt("missing") is None

    def test_pending_excludes_settled(self):
        coord = HeartbeatCoordinator()
        coord.submit("a")
        coord.submit("b")
        coord.settle("a", "ok")
        assert [c.dedupe_key for c in coord.pending()] == ["b"]

    def test_clear(self):
        coord = HeartbeatCoordinator()
        coord.submit("x")
        coord.clear()
        assert coord.pending() == []
        assert not coord.is_duplicate("x")


class TestHeartbeatOutcome:
    def test_commitment_dataclass_serializes(self):
        c = Commitment(dedupe_key="d", payload={"a": 1}, attempts=2, uncertain=False, outcome="ok")
        d = c.to_dict()
        assert d["dedupe_key"] == "d"
        assert d["attempts"] == 2
