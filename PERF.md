# Performance Ledger — JARVIS response path (kernel TTFT)

Metric that matters: **time-to-first-visible-token (TTFT)** of `POST /v1/chat`
measured from request write to the first SSE `delta` event, unique prompts
(no response-cache hits), live kernel on 127.0.0.1:8170.

Current steady state after the fixes below: **62–102ms TTFT, 6/6 turns served
by the fast chain head (groq)**. Synthetic gate: `tests/test_ttft_budget.py`
(budget 2000ms; steady state runs ~10x under it).

## Kept

| Idea | Baseline → Result | Verdict | Why |
|---|---|---|---|
| Shared SSL context for provider clients (`core/http_pool.py`, `openai_compat.py`, `groq_provider.py`) | Groq client ctor 1400–2652ms → ~0ms; first-turn TTFT 2143–3453ms → 122ms* | kept | `httpx.create_ssl_context()` re-loads ~120 Windows CA certs on every SDK client build; one process-wide context eliminates the class |
| Prewarm + keepalive on the engine's shared asyncio loop (`jbrowser-bridge/server.py`) | First turn after idle paid a fresh TLS reconnect (600–2100ms) → connection reused | kept | The old `asyncio.run()` prewarm warmed connections owned by a throwaway loop, useless to the message path |
| Keepalive drains the ping stream fully | Prewarmed pool still empty; first message still paid 2.2s reconnect → fixed | kept | Abandoning the SSE stream mid-flight never returns the connection to the pool |
| Live groq fallback model: `llama-3.1-8b-instant` → `openai/gpt-oss-20b` (`config/models.toml`) | Groq fallback 404 `model_not_found` (Groq retired the model, verified vs live `/models`) → fallback works | kept | A dead fallback converted any groq hiccup into a total groq outage |
| Quota-aware keepalive target (ping one provider: first in chain with ≥15 RPM and ≥5,000 RPD) | Old target = top-2 chain ≈ 480 pings/day against OpenRouter's 200/day free quota → guaranteed self-inflicted rate-limit outage | kept | Burning scarce quota to save a TLS handshake is a net loss |
| Sticky-winner TTL, 30s (`jbrowser-bridge/engine.py`) | Slow provider armed via the fallback walk probed ALONE forever (`_RACE_MAX_PROBES=1`), locking the fast chain head out: 2.5–25.4s TTFT every turn → 6/6 turns on groq at 62–102ms | kept | A claim that never lapses converts a transient fallback into a permanent regression |

\* The 122ms figure from the first fix round measured the first SSE *frame*
(server accept), not the first provider token — the lock-in regression below
was hiding behind it. The honest first-`delta` measurement is what exposed it.

## Reverted / refused

| Idea | Baseline → Result | Verdict | Why |
|---|---|---|---|
| Raising `_RACE_MAX_PROBES` back to 3 to "race everyone" | — | refused | Races of healthy providers burned hello-scale rate limits before; the sticky+TTL design keeps the fallback safety without the 3x connect cost |
| Trusting the sticky winner without a TTL | 62–102ms → 2.5–25.4s TTFT | reverted (superseded by TTL) | A slow fallback-walk winner must not monopolize the probe slot |
| Keepalive pings against OpenRouter/opencode_zen free tiers | — | reverted (superseded by quota-aware target) | ~480 req/day against a 200/day quota guarantees the outage it was meant to prevent |

## Deferred

| Idea | Why deferred |
|---|---|
| Shared HTTP transport for the gemini SDK client (`genai.Client` builds cost ~1.2s) | Boot warmup builds it off the request path and the sticky design reuses it; no measured user-facing cost today |
| Provider-health surfacing in `/status` | `/v1/models` already exposes availability per model; richer health needs a design pass |

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
