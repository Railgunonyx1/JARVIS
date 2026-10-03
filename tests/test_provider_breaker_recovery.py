"""Provider circuit-breaker recovery (half-open probe).

Before this fix, a provider latched unavailable after 5 consecutive
failures stayed dead until process restart: only a successful request
reset health, but unavailable providers were excluded from the chain and
never received one — one transient groq 5xx burst permanently degraded
chat to the slower chain tails (measured: /v1/models showed the fast head
``available: false`` while the pinned provider succeeded in a fresh
process). The breaker now admits ONE probe per interval (half-open);
success closes it, failure re-latches for another interval.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.base import LLMProvider  # noqa: E402


class _BareProvider(LLMProvider):
    """Concrete provider that exercises health bookkeeping only."""

    def __init__(self):
        super().__init__("fake", {"model": "fake"})

    async def complete(self, messages, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def complete_stream(self, messages, **kwargs):  # pragma: no cover
        raise NotImplementedError
        yield  # pragma: no cover — makes this an async generator


@pytest.fixture()
def provider():
    return _BareProvider()


def test_latch_after_five_failures(provider):
    for _ in range(4):
        provider.record_failure("boom")
    # Failure 3+ arms a cooldown (check_quota blocks), but the circuit
    # itself is still closed — health.available remains True.
    assert provider.health.available is True
    provider.record_failure("boom")  # 5th
    assert provider.health.available is False  # LATCHED
    assert provider.is_available is False


def test_latched_provider_never_probes_before_interval(provider):
    for _ in range(5):
        provider.record_failure("boom")
    # A few "turns" pass well inside the probe interval: still dead.
    time.sleep(0.01)
    assert provider.is_available is False
    assert provider.is_available is False
    assert provider.is_available is False


def test_half_open_probe_admitted_after_interval(provider):
    for _ in range(5):
        provider.record_failure("boom")
    assert provider.is_available is False
    # Simulate the passage of _PROBE_INTERVAL_S since the latch.
    provider.health.last_check -= provider._PROBE_INTERVAL_S + 1
    assert provider.is_available is True  # probe admitted


def test_successful_probe_closes_circuit(provider):
    for _ in range(5):
        provider.record_failure("boom")
    provider.health.last_check -= provider._PROBE_INTERVAL_S + 1
    assert provider.is_available is True  # the probe turn
    provider.record_success(42.0)
    assert provider.health.available is True
    # Closed circuit: steady availability with no probe machinery needed.
    assert provider.is_available is True


def test_failed_probe_relatches_for_full_interval(provider):
    for _ in range(5):
        provider.record_failure("boom")
    provider.health.last_check -= provider._PROBE_INTERVAL_S + 1
    assert provider.is_available is True  # probe goes out
    provider.record_failure("still broken")
    assert provider.is_available is False  # re-latched
    # Another immediate turn is refused: no hammering.
    assert provider.is_available is False


def test_probe_stamps_last_check(provider):
    """The probe decision is STICKY: the interval is stamped once (first
    is_available after the window), and repeated reads neither re-arm nor
    re-delay the probe — read-only observation must not push recovery to
    the next interval. The router consumes the probe via consume_probe()
    when it admits real traffic."""
    for _ in range(5):
        provider.record_failure("boom")
    provider.health.last_check -= provider._PROBE_INTERVAL_S + 1
    before = provider.health.last_check
    assert provider.is_available is True
    assert provider.health.last_check > before
    # Sticky: a second read does not re-stamp last_check.
    stamped = provider.health.last_check
    assert provider.is_available is True
    assert provider.health.last_check == stamped
    # The router consumes the probe; only then is admission spent.
    provider.consume_probe()
    assert provider.is_available is False
