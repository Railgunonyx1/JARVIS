"""Row 18 — credential pool (hermes failover)."""

from __future__ import annotations

import time

import pytest

from providers.credential_pool import (
    CredentialPool,
    FailoverReason,
    PoolExhausted,
    RotationStrategy,
    clear_pools,
    classify_failure,
    get_pool,
    resolve_runtime_pool_key,
)


class TestClassification:
    def test_quota(self):
        assert classify_failure(Exception("insufficient_quota"), status_code=402) == FailoverReason.QUOTA

    def test_rate_limit(self):
        assert classify_failure(Exception("Rate limit exceeded"), status_code=429) == FailoverReason.RATE_LIMIT

    def test_auth(self):
        assert classify_failure(Exception("invalid api key"), status_code=401) == FailoverReason.AUTH

    def test_model_scoped(self):
        assert classify_failure(Exception("model not found"), model_scoped=True) == FailoverReason.MODEL

    def test_transient(self):
        assert classify_failure(Exception("connection reset"), status_code=503) == FailoverReason.TRANSIENT
        assert classify_failure(Exception("request timed out")) == FailoverReason.TRANSIENT

    def test_fatal(self):
        assert classify_failure(Exception("bad request"), status_code=400) == FailoverReason.FATAL

    def test_status_code_attribute(self):
        class E(Exception):
            status_code = 429
        assert classify_failure(E("whatever")) == FailoverReason.RATE_LIMIT


class TestResolution:
    def test_identity_then_endpoint(self):
        a = resolve_runtime_pool_key("groq", "https://api.groq.com/")
        b = resolve_runtime_pool_key("groq", "https://api.groq.com")
        assert a == b
        c = resolve_runtime_pool_key("groq", "https://x/")
        assert a != c
        d = resolve_runtime_pool_key("openai", "https://api.groq.com/")
        assert a != d


class TestPoolBasics:
    def setup_method(self):
        clear_pools()

    def test_add_size_strategy(self):
        p = CredentialPool(provider="p", base_url="https://x/", strategy=RotationStrategy.FILL_FIRST)
        e1 = p.add("secret1")
        e2 = p.add("secret2")
        assert p.size() == 2
        l = p.acquire()
        assert l.entry.key_id == e1.key_id
        l.release()

    def test_fill_first_always_first_alive(self):
        p = CredentialPool(provider="p", base_url="https://x/", strategy=RotationStrategy.FILL_FIRST)
        a = p.add("a"); b = p.add("b")
        for _ in range(5):
            lease = p.acquire()
            assert lease.entry.key_id == a.key_id
            lease.release()

    def test_round_robin_cycles(self):
        p = CredentialPool(provider="p", base_url="https://x/", strategy=RotationStrategy.ROUND_ROBIN)
        a = p.add("a"); b = p.add("b")
        seen = []
        for _ in range(4):
            lease = p.acquire()
            seen.append(lease.entry.key_id)
            lease.release()
        assert seen == [a.key_id, b.key_id, a.key_id, b.key_id]

    def test_least_used_picks_lowest_total(self):
        p = CredentialPool(provider="p", base_url="https://x/", strategy=RotationStrategy.LEAST_USED)
        a = p.add("a"); b = p.add("b")
        p.record_success(a.key_id)  # a total=1
        lease = p.acquire()
        assert lease.entry.key_id == b.key_id
        lease.release()

    def test_remove(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        assert p.remove(e.key_id) is True
        assert p.size() == 0
        assert p.remove("nope") is False

    def test_exhausted_raises(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        p.disable(e.key_id)
        with pytest.raises(PoolExhausted):
            p.acquire()


class TestFailoverReasons:
    def setup_method(self):
        clear_pools()

    def test_quota_marks_dead_and_rotate(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        res = p.record_failure(e.key_id, FailoverReason.QUOTA)
        assert res["action"] == "rotate"
        assert e.dead is True
        assert e.dead_reason == "quota_exhausted"

    def test_auth_marks_dead(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        res = p.record_failure(e.key_id, FailoverReason.AUTH)
        assert res["action"] == "rotate"
        assert e.dead is True

    def test_rate_limit_retries_once_then_rotates(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        r1 = p.record_failure(e.key_id, FailoverReason.RATE_LIMIT)
        assert r1["action"] == "retry_once"
        # same key now marked rate-limited; second 429 rotates
        r2 = p.record_failure(e.key_id, FailoverReason.RATE_LIMIT)
        assert r2["action"] == "rotate"

    def test_model_scoped_cooldown_only(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        res = p.record_failure(e.key_id, FailoverReason.MODEL, model="m1")
        assert res["action"] == "cooldown_model"
        assert e.dead is False
        # model cooldown recorded
        assert p._model_cooldowns[(e.key_id, "m1")] > time.time()

    def test_transient_cooldowns_key(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        res = p.record_failure(e.key_id, FailoverReason.TRANSIENT)
        assert res["action"] == "retry_once"
        assert e.cooldown_until > time.time()

    def test_fatal_propagates_no_rotation(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        res = p.record_failure(e.key_id, FailoverReason.FATAL)
        assert res["action"] == "propagate"
        assert e.dead is False

    def test_success_clears_rate_limited_flag(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        p.record_failure(e.key_id, FailoverReason.RATE_LIMIT)  # retry_once
        assert e.key_id in p._rate_limited_once
        p.record_success(e.key_id)
        assert e.key_id not in p._rate_limited_once


class TestRotation:
    def setup_method(self):
        clear_pools()

    def test_rotate_after_returns_next(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        a = p.add("a"); b = p.add("b")
        # mark a dead
        p.record_failure(a.key_id, FailoverReason.QUOTA)
        nxt = p.rotate_after(a.key_id)
        assert nxt == b.key_id

    def test_no_recovery_guard_for_just_marked(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        a = p.add("a"); b = p.add("b")
        p.record_failure(a.key_id, FailoverReason.QUOTA)
        p.disable(b.key_id)
        # no selectable peers remain and a was just marked -> no_recovery
        nxt = p.rotate_after(a.key_id)
        assert nxt == "no_recovery"

    def test_rotation_bounded_no_selectable(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        a = p.add("a")
        p.disable(a.key_id)
        assert p.rotate_after(a.key_id) == "no_recovery"

    def test_revive(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        p.disable(e.key_id)
        assert e.dead is True
        assert p.revive(e.key_id) is True
        assert e.dead is False
        assert p.revive("nope") is False

    def test_lease_count(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        e = p.add("a")
        lease = p.acquire()
        assert e.lease_count == 1
        lease.release()
        assert e.lease_count == 0


class TestIdentityCache:
    def setup_method(self):
        clear_pools()

    def test_get_pool_singleton_by_key(self):
        p1 = get_pool("groq", "https://api.groq.com/")
        p2 = get_pool("groq", "https://api.groq.com")
        assert p1 is p2
        p3 = get_pool("groq", "https://other/")
        assert p3 is not p1

    def test_pool_status_no_secret_leak(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        p.add("SUPERSECRET")
        st = p.status()
        text = str(st)
        assert "SUPERSECRET" not in text
        assert st["size"] == 1


class TestPoolExhaustedAndModelCooldown:
    def setup_method(self):
        clear_pools()

    def test_model_cooldown_excludes_entry_for_model(self):
        t = [100.0]
        p = CredentialPool(provider="p", base_url="https://x/", now=lambda: t[0])
        e = p.add("a")
        p.record_failure(e.key_id, FailoverReason.MODEL, model="m1")
        # m1 cooled down -> not eligible for m1
        assert p._eligible("m1") == []
        # other model still eligible
        assert len(p._eligible("m2")) == 1

    def test_status_counts(self):
        p = CredentialPool(provider="p", base_url="https://x/")
        a = p.add("a"); b = p.add("b")
        p.disable(b.key_id)
        st = p.status()
        assert st["alive"] == 1 and st["dead"] == 1
