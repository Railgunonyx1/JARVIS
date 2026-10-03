# Performance Ledger — JARVIS response path (kernel TTFT)

Metric that matters: **time-to-first-visible-token (TTFT)** of `POST /v1/chat`
measured from request write to the first SSE `delta` event, unique prompts
(no response-cache hits), live kernel on 127.0.0.1:8170.

Current steady state after the fixes below: **62–102ms TTFT, 6/6 turns served
by the fast chain head (groq)**. Synthetic gate: `tests/test_ttft_budget.py`
(budget 2000ms; steady state runs ~10x under it).

## Verified 2026-09-20: keepalive redesign holds across long idle

Fresh boot, `--verbose` bridge, all warmup stages confirmed firing
(SDK warmup → TTFT prewarm → engine-path race warm, then keepalive pings
every 25s — 26 pings logged over the session, zero misses). Measured
first-`delta` TTFT on unique prompts through the full engine path:

| Scenario | TTFT (first delta) | Total | Provider served |
|---|---|---|---|
| After 90s pinged idle | 80ms | 127ms | groq qwen3.8-27b |
| After 170s pinged idle | 68ms | 163ms | groq qwen3.8-27b |
| Back-to-back pair | 79 / 114ms | 154 / 230ms | groq qwen3.8-27b |
| **After 4min pinged idle** | **75ms** | **131ms** | groq qwen3.8-27b |

The historical ~2.1s idle penalty is fully closed: a turn after 4 minutes of
idle is indistinguishable from a back-to-back turn. Ping-first cadence
(t+10s, then every 25s) keeps the pooled connection permanently inside its
30s `keepalive_expiry`, and the boot engine-path warm means turn 1 skips the
race machinery's first-run cost as well.

## Kept

| Idea | Baseline → Result | Verdict | Why |
|---|---|---|---|
| Shared SSL context for provider clients (`core/http_pool.py`, `openai_compat.py`, `groq_provider.py`) | Groq client ctor 1400–2652ms → ~0ms; first-turn TTFT 2143–3453ms → 122ms* | kept | `httpx.create_ssl_context()` re-loads ~120 Windows CA certs on every SDK client build; one process-wide context eliminates the class |
| Prewarm + keepalive on the engine's shared asyncio loop (`jbrowser-bridge/server.py`) | First turn after idle paid a fresh TLS reconnect (600–2100ms) → connection reused | kept | The old `asyncio.run()` prewarm warmed connections owned by a throwaway loop, useless to the message path |
| Keepalive drains the ping stream fully | Prewarmed pool still empty; first message still paid 2.2s reconnect → fixed | kept | Abandoning the SSE stream mid-flight never returns the connection to the pool |
| Live groq fallback model: `llama-3.1-8b-instant` → `openai/gpt-oss-20b` (`config/models.toml`) | Groq fallback 404 `model_not_found` (Groq retired the model, verified vs live `/models`) → fallback works | kept | A dead fallback converted any groq hiccup into a total groq outage |
| Quota-aware keepalive target (ping one provider: first in chain with ≥15 RPM and ≥5,000 RPD) | Old target = top-2 chain ≈ 480 pings/day against OpenRouter's 200/day free quota → guaranteed self-inflicted rate-limit outage | kept | Burning scarce quota to save a TLS handshake is a net loss |
| Sticky-winner TTL, 30s (`jbrowser-bridge/engine.py`) | Slow provider armed via the fallback walk probed ALONE forever (`_RACE_MAX_PROBES=1`), locking the fast chain head out: 2.5–25.4s TTFT every turn → 6/6 turns on groq at 62–102ms | kept | A claim that never lapses converts a transient fallback into a permanent regression |
| Idle-gap fixes: keepalive 180s → 60s + early first cycle; `keepalive_expiry` 300s → 30s in provider SDK clients | Turn after 150s idle paid ~2.1s → 81–157ms | kept | Home-router NAT drops idle connections well before 180s; the pairing (re-ping every 25–60s, expire pooled conns at 30s) always hands the request a live connection |
| A/B attribution: direct-to-provider vs through-kernel, same moment (`tmp-ab.js`, removed) | Kernel path SSE-start 16ms, warm turns 57–115ms — kernel is FASTER than a fresh direct call | kept | Proved the remaining latency was connection hygiene, not kernel overhead; stopped client tuning there |
| Cold-stream check: fresh-process Groq streaming TTFT | 120–227ms — no provider-side cold-start exists | kept | Closed the question: the old ~2.1s idle penalty was kernel-side stale connections, not provider cold-start; client tuning is done |

\* The 122ms figure from the first fix round measured the first SSE *frame*
(server accept), not the first provider token — the lock-in regression below
was hiding behind it. The honest first-`delta` measurement is what exposed it.

## Reverted / refused

| Idea | Baseline → Result | Verdict | Why |
|---|---|---|---|
| Raising `_RACE_MAX_PROBES` back to 3 to "race everyone" | — | refused | Races of healthy providers burned hello-scale rate limits before; the sticky+TTL design keeps the fallback safety without the 3x connect cost |
| Groq head model `qwen/qwen3-8b` → `openai/gpt-oss-120b` | Pinned probe 67–157ms, but the UNPINNED engine path hard-failed and walked the chain to openrouter (10.8–22.1s turns) | reverted | A head model must survive the engine's real request shape (tool schemas), not just a pinned probe |
| Trusting the sticky winner without a TTL | 62–102ms → 2.5–25.4s TTFT | reverted (superseded by TTL) | A slow fallback-walk winner must not monopolize the probe slot |
| Keepalive pings against OpenRouter/opencode_zen free tiers | — | reverted (superseded by quota-aware target) | ~480 req/day against a 200/day quota guarantees the outage it was meant to prevent |

## Deferred

| Idea | Why deferred |
|---|---|
| Shared HTTP transport for the gemini SDK client (`genai.Client` builds cost ~1.2s) | Boot warmup builds it off the request path and the sticky design reuses it; no measured user-facing cost today |
| Provider-health surfacing in `/status` | `/v1/models` already exposes availability per model; richer health needs a design pass |
| Racing groq + deepseek in parallel (first token wins) | deepseek silently dies inside the engine's real request path (works pinned); needs the root cause fixed before a 2-way race is meaningful |

## Browser stack (2026-09-19)

Review claims verified against the local tree (the GitHub tree is far behind);
three were real and are fixed:

| Fix | Was | Now |
|---|---|---|
| `_check_playwright` verdict caching (`jbrowser/backend/playwright.py`) | Failed first probe left the driver running → later calls returned `True` → `available` lied, fallback never fired | Cached verdict reflects the actual probe result; failed probe stops its driver process; regression-tested |
| WebScraper fallback (`jbrowser/controller.py`) | Promised in two docstrings, wired nowhere — `status()` labeled the backend "web_scraper" cosmetically | Real fallback for `navigate`/`extract_text` when the engine cannot launch, sharing the engine's SSRF network policy; policy denials are NOT retried via the scraper; truthful `status()` labels |
| `browser_automation.json` risk | `"low"` while bundling HIGH-risk `browser.click`/`browser.type` | `"high"` — matches the canonical risk model in `tools/classification.py` |

Suite: 887 passed / 0 failed (was 879; +8 new regression tests).

## How to re-measure

```bash
python -m pytest tests/test_ttft_budget.py -q   # skips if the kernel is down
```

or live, with unique prompts so the response cache can never mask a regression:

```python
# POST /v1/chat, measure to first SSE event of type "delta",
# read the trailing "meta" event for provider provenance.
```

Baseline conditions: kernel booted via `JARVIS.bat`, warmup thread finished
(~20s), one throwaway turn to settle, unique one-word prompts.

## Transport + breaker pass (2026-10-01)

Three classes of residual latency/failure, all fixed:

| Fix | Was | Now | Why |
|---|---|---|---|
| SSE `Connection: close` honesty + handler `disable_nagle_algorithm` + HTTP/1.1 | SSE headers advertised keep-alive while terminating via close; Nagle could hold small SSE frames for the peer's delayed ACK (hundreds of ms, nondeterministic) | Frames ship the moment they are produced; stream end is honestly framed | Nagle-off makes first-delta latency deterministic even when token deltas are tiny |
| Drain coalescing (server.py `_drain`) | one syscall + flush per token-sized delta (dozens/sec per stream) | drains collect up to 24 already-queued events into one write; flush the moment the queue is empty | first token still ships alone instantly; dense bursts travel in one packet |
| Provider circuit-breaker half-open probe (providers/base.py) | provider latched `available=False` after 5 failures stayed dead until process restart (only success revived it; excluded providers never get one) — one transient groq 5xx burst permanently degraded chat to slow chain tails | after `_PROBE_INTERVAL_S=120s` the circuit admits ONE probe; success closes it immediately (also clears stale cooldown), failure re-latches | turns the permanent degradation into a bounded 2-minute outage |
| RAG index boot warm (server.py warmup, `wait=False`) | first knowledge-y chat turn of a process could wait up to 750ms for the TF-IDF build | index builds in background at boot; chat turns find it hot | removes the last first-turn stall added by the RAG pass |

New regression coverage: tests/test_provider_breaker_recovery.py (6 tests — latch,
no-probe-inside-interval, probe admission, close-on-success, re-latch-on-failure,
one-probe-per-interval stamping).
