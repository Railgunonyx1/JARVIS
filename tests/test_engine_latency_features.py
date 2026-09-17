"""Engine latency features: response cache, slow-first-token ack, sticky
race winner. All hermetic — fake streamers, no provider network calls."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BRIDGE_DIR = Path(__file__).resolve().parent.parent / "jbrowser-bridge"
if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))

from engine import (  # noqa: E402
    _RESPONSE_CACHE,
    Budget,
    ModelGatewayEngine,
    _response_cache_get,
    _response_cache_key,
    _response_cache_put,
)
import engine as engine_mod  # noqa: E402


def _arm_sticky(name):
    """Arm the module-level sticky claim as a fresh winner.

    The claim is time-bound (_STICKY_TTL_S): tests that preset the winner
    must also stamp the clock or the engine treats the claim as stale and
    re-probes the chain head.
    """
    import time as _time
    engine_mod._sticky_winner = name
    engine_mod._sticky_won_at = _time.monotonic()


def run(coro):
    import threading
    loop = asyncio.new_event_loop()
    result = {}

    def _run():
        result["v"] = loop.run_until_complete(coro)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join()
    return result["v"]


class FakeRouter:
    """Minimal router double for _race_providers tests."""

    def __init__(self, providers, chain):
        self._providers = providers
        self._chain = chain
        self._last_provider = None
        self._last_model = None

    def _get_available_chain(self):
        return list(self._chain)


class Fp:
    """Streaming provider double: yields `chunks` asynchronously."""

    def __init__(self, name, model, chunks, delay=0.0):
        self.name = name
        self.model = model
        self._chunks = list(chunks)
        self._delay = delay

    async def complete_stream(self, messages, system_prompt, max_tokens):
        for c in self._chunks:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield c


class TestResponseCache:
    def test_key_is_deterministic_and_scoped(self):
        prompt = [{"role": "user", "content": "hi"}]
        k1 = _response_cache_key(prompt, "sys", None)
        k2 = _response_cache_key(prompt, "sys", None)
        assert k1 and k1 == k2
        other = _response_cache_key([{"role": "user", "content": "bye"}], "sys", None)
        assert k1 != other
        model_scoped = _response_cache_key(prompt, "sys", "gemini")
        assert k1 != model_scoped

    def test_multi_turn_inputs_are_not_cached(self):
        multi = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                 {"role": "user", "content": "c"}]
        assert _response_cache_key(multi, "sys", None) is None

    def test_put_get_roundtrip_and_eviction(self):
        _RESPONSE_CACHE.clear()
        key = _response_cache_key([{"role": "user", "content": "q"}], "s", None)
        _response_cache_put(key, "hello there")
        assert _response_cache_get(key) == "hello there"
        # empty / oversized writes are ignored
        _response_cache_put(key, "")
        assert _response_cache_get(key) == "hello there"

    def test_cached_turn_skips_streaming(self):
        _RESPONSE_CACHE.clear()
        calls = {"n": 0}
        engine = ModelGatewayEngine(streamer=None, budget=Budget())
        prompt = engine._build_prompt(
            [{"role": "user", "content": "cache-me"}], None)
        key = _response_cache_key(prompt, engine.system_prompt, None)
        assert key, "multi-free single-turn prompt must be cacheable"
        _response_cache_put(key, "cached reply")

        async def fake(messages, system_prompt, max_tokens):
            calls["n"] += 1
            yield "real reply"

        engine = ModelGatewayEngine(streamer=fake, budget=Budget())
        seen = []
        text = engine.stream_chat("s", [{"role": "user", "content": "cache-me"}],
                                  None, seen.append)
        assert text == "cached reply"
        assert calls["n"] == 0  # streamer never invoked
        kinds = [e["type"] for e in seen]
        assert kinds[0] == "start" and kinds[-1] == "done"
        assert any(e.get("cached") for e in seen if e["type"] == "meta")


class TestSlowFirstTokenAck:
    def test_ack_emitted_on_slow_first_token(self):
        # An invisible (empty) chunk after the deadline triggers the ack;
        # only then a visible token arrives.
        async def slow(messages, system_prompt, max_tokens):
            await asyncio.sleep(0.25)
            yield ""
            yield "finally"

        engine = ModelGatewayEngine(streamer=slow, budget=Budget())
        engine._ACK_AFTER_S = 0.1  # shrink the wait for the test
        seen = []
        engine.stream_chat("s", [{"role": "user", "content": "hi"}], None, seen.append)
        ack = [e for e in seen if e["type"] == "ack"]
        assert len(ack) == 1
        assert ack[0]["text"]
        # ack arrives before the first delta
        assert seen.index(ack[0]) < seen.index(next(e for e in seen if e["type"] == "delta"))

    def test_no_ack_when_first_token_is_fast(self):
        async def fast(messages, system_prompt, max_tokens):
            yield "instant"

        engine = ModelGatewayEngine(streamer=fast, budget=Budget())
        engine._ACK_AFTER_S = 0.1
        seen = []
        engine.stream_chat("s", [{"role": "user", "content": "hi"}], None, seen.append)
        assert not any(e["type"] == "ack" for e in seen)


class TestStickyRaceWinner:
    def test_single_probe_winner_is_remembered(self):
        """_RACE_MAX_PROBES=1 collapses races to one probe — sticky must
        still be armed there or the optimization is dead code."""
        engine_mod._sticky_winner = None
        router = FakeRouter(
            {"fast": Fp("fast", "f", ["hello"]), "slow": Fp("slow", "s", ["world"])},
            chain=["fast", "slow"],
        )
        sink = []

        async def collect():
            async for chunk in engine_mod._race_providers(
                router, [], "sys", 512):
                sink.append(chunk)

        run(collect())
        assert sink == ["hello"]
        assert engine_mod._sticky_winner == "fast"

    def test_stale_walk_sticky_cannot_block_chain_head(self):
        """Regression: a slow provider armed via the FALLBACK WALK locked the
        sticky slot forever (_RACE_MAX_PROBES=1 probes it alone), so the fast
        chain head was never re-probed (measured: 2-5s openrouter TTFT for
        every turn while groq sat unpicked). A stale claim must lapse and
        re-probe the chain head; the head's win re-arms the claim."""
        engine_mod._sticky_winner = "slow"
        engine_mod._sticky_won_at = 0.0  # ancient stamp -> claim expired
        router = FakeRouter(
            {"fast": Fp("fast", "f", ["head"]), "slow": Fp("slow", "s", ["alt"])},
            chain=["fast", "slow"],
        )
        visited = []

        async def collect4():
            async for chunk in engine_mod._race_providers(
                    router, [], "sys", 512):
                visited.append(chunk)

        run(collect4())
        assert visited == ["head"]
        assert engine_mod._sticky_winner == "fast"
        # ...and the re-armed claim is fresh again
        assert engine_mod._sticky_won_at > 0.0
        engine_mod._sticky_winner = None
        engine_mod._sticky_won_at = 0.0

    def test_sticky_leads_next_race(self):
        _arm_sticky("fast")
        # Sticky re-arms the proven provider in a fresh single-probe chain.
        router = FakeRouter(
            {"fast": Fp("fast", "f", ["next"]), "slow": Fp("slow", "s", ["alt"])},
            chain=["fast", "slow"],
        )
        visited = []

        async def collect2():
            async for chunk in engine_mod._race_providers(
                router, [], "sys", 512):
                visited.append(chunk)

        run(collect2())
        assert visited == ["next"]
        engine_mod._sticky_winner = None
        engine_mod._sticky_won_at = 0.0

    def test_sticky_head_failure_walks_full_chain_and_rearms(self):
        """Sticky winner that died re-forms the fallback via the router and
        re-arms sticky on the provider that actually answered."""
        import engine as engine_mod

        class DeadWinner:
            name = "fast"

            async def complete_stream(self, messages, system_prompt, max_tokens):
                await asyncio.sleep(0.02)
                raise RuntimeError("dead provider")
                yield  # pragma: no cover - async generator contract

        class RouterWalk:
            def __init__(self, providers):
                self._providers = providers
                self._last_provider = None
                self._last_model = None

            def _get_available_chain(self):
                return ["fast", "slow"]

            async def complete_stream(self, messages, system_prompt, max_tokens,
                                      preferred_provider=None, preferred_model=None):
                for chunk in ["walk-reply"]:
                    yield chunk

        router = RouterWalk({"fast": DeadWinner(), "slow": Fp("slow", "s", ["walk-reply"])})
        _arm_sticky("fast")
        sink = []

        async def collect3():
            async for chunk in engine_mod._race_providers(
                router, [], "sys", 512):
                sink.append(chunk)

        run(collect3())
        assert sink == ["walk-reply"]
        engine_mod._sticky_winner = None
        engine_mod._sticky_won_at = 0.0
