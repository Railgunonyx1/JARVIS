# Free LLM API Keys — JARVIS Setup Guide

Based on the [awesome-freellm-apis](https://github.com/open-free-llm-api/awesome-freellm-apis) directory (freellm.net, daily-refreshed data).

JARVIS's provider router automatically activates any provider whose API key
exists in `config/.env`. You don't need all of them — each key you add makes
the fallback chain wider and rate-limit-proof. **Groq + Gemini are already
configured**; the rest are optional depth.

## How it works

```
config/.env  ──►  core/api_keys.py  ──►  providers/router.py  ──►  config/models.toml
 (keys)           (ENV → key name)       (activates provider)     (rate limits, models)
```

Add a key → restart JARVIS → the provider joins the race automatically.

## Tier 1 — recommended, no credit card, <1 min

| Provider | Get key at | Env name for config/.env | Free limits |
|---|---|---|---|
| **Groq** | console.groq.com/keys | `GROQ_API_KEY` (+`_2`) | 30 RPM |
| **Google Gemini** | aistudio.google.com/apikey | `GEMINI_API_KEY` (+`_2`) | 15 RPM / 1500 RPD |
| **OpenRouter** | openrouter.ai/keys | `OPENROUTER_API_KEY` (+`_2`..`_4`) | :free models |
| **LLM7.io** | llm7.io | `LLM7_API_KEY` | 10 RPM / 60 req/hr |
| **Cohere** | dashboard.cohere.com/api-keys | `COHERE_API_KEY` | 20 RPM |
| **Z AI (GLM)** | z.ai / open.bigmodel.cn | `ZAI_API_KEY` | GLM-4.7-flash free |
| **Cerebras** | cloud.cerebras.ai | `CEREBRAS_API_KEY` | 30 RPM, very fast |
| **Mistral** | console.mistral.ai/api-keys | `MISTRAL_API_KEY` | free plan ≈ $10/mo credits |
| **Kilo Code** | kilo.ai | `KILO_CODE_API_KEY` | 200 req/hr proxy |

> GitHub Models was removed from this list and from `config/models.toml`:
> the service retired 2026-07-30.

## Tier 2 — registration required, still free

| Provider | Get key at | Env name | Free limits |
|---|---|---|---|
| **NVIDIA NIM** | build.nvidia.com (phone verify) | `NVIDIA_NIM_API_KEY` | 130 models, 40 RPM |
| **Agnes AI** | apihub.agnes-ai.com | `AGNES_API_KEY` | 30 RPM |
| **Scaleway** | console.scaleway.com | `SCALEWAY_API_KEY` | fair use |
| **SambaNova** | cloud.sambanova.ai | `SAMBANOVA_API_KEY` | 20 RPM / 20 RPD |
| **OpenCode Zen** | opencode.ai/zen | `OPENCODE_ZEN_API_KEY` | 1M ctx free models |
| **Cloudflare AI** | dash.cloudflare.com → API tokens | `CLOUDFLARE_API_TOKEN` | 10K neurons/day |
| **Hugging Face** | huggingface.co/settings/tokens | `HF_API_KEY` | credit-metered |

## Example: adding two keys in 60 seconds

Edit `config/.env`:

```env
LLM7_API_KEY=free-token-from-llm7.io
COHERE_API_KEY=your-key-from-dashboard.cohere.com
```

Restart JARVIS. The router log will now show:

```
Router initialized: groq → gemini → cerebras → openrouter → opencode_zen
                    → kilo_code → agnes → llm7 → cohere → ...
```

## Rate-limit behavior (already configured)

Rate limits for every provider live in `config/models.toml` as
`requests_per_minute` / `requests_per_day`. JARVIS:

- **Races** the top 3 healthy providers in parallel — first visible token wins
- **Sticks** to the last winner so a slow head doesn't gate replies
- **Rotates** numbered key variants (`GROQ_API_KEY_2`, ...) on 429s
- **Cools down** providers that hit limits instead of hammering them
- **Falls back** through the whole chain — more keys = fewer user-visible errors

## DeepSeek key warning

The current `DEEPSEEK_API_KEY` in `config/.env` is an **OpenRouter key**
(`sk-or-v1-...`). The router now detects and disables it with an error log.
Either get a real key at platform.deepseek.com or delete the line.

## Keeping models current

Default models per provider come from freellm.net's daily snapshot
(2026-09). When a model retires, edit the `model = "..."` line in the
matching `[provider]` section of `config/models.toml` — or check
freellm.net for the current best free model per provider.

## Tiny local lane — Cactus Needle (the "14 MB tool-call model")

[Needle](https://github.com/cactus-compute/needle) (Cactus Compute) is a
26M-parameter automation foundation model shipped as a single 8–29 MB
binary (Needle 3 is sliceable, 2–20 layers). It does three things locally,
CPU-only: **tool calling** (picks tools, fills args, returns an empty list
for off-topic asks instead of guessing), **structured extraction**
(grammar-constrained JSON), and **text embeddings** — all from one model.

Validated on this machine (Windows, CPU, 2026-09-20):

- `pip install cactus-needle` — installs and imports cleanly
- Full tool loop (call → execute → respond) verified with two tools
- ~1–2s init after weights cached, ~0.7–1.4s per turn
- 128 tok/s decode, 48 tok/s prefill, ~100 MB peak RAM
- Responses carry a calibrated `confidence` and `suppressed_calls` —
  low-confidence calls are withheld, not hallucinated

```python
import needle

@needle.tool
def get_weather(city: str):
    "Get the current weather for a city."
    return {"city": city, "temp_c": 27, "sky": "clear"}

agent = needle.Needle(tools=[get_weather])
agent.run("what's it like in Lagos right now?")
```

Set `NEEDLE_TELEMETRY=0` and `DO_NOT_TRACK=1` to disable its telemetry.
It is listed (commented) in `requirements.txt` under Optional. Planned
JARVIS fit: the tiny intent/router lane (command classification, memory
query reformulation, tool selection) — replacing nothing that works today,
adding a sub-second local option where qwen2.5:1.5b via Ollama is currently
the smallest choice (~1 GB).

---

## llm7.io — verified KEYLESS (2026-09-20)

No signup at all: JARVIS ships llm7 pre-configured with the anonymous token
"unused". Verified live that **GLM-5.3-Flash** and **codestral-latest** work
keyless (including streaming). Most other menu entries (GPT/Claude/Gemini/
Grok/DeepSeek big models) now require a free token from <https://token.llm7.io> —
if you get one, set `LLM7_API_KEY=<token>` in `config/.env` and the whole menu
unlocks at 10 RPM / 800 RPD.

Open question solved: llm7's old default `gpt-oss-20b` was removed from the
live menu (every call returned model_unavailable); config now pins the
verified-working `GLM-5.3-Flash`.

## Sakana Fugu (Ultra v2 / Max) — PAID, optional

Sakana AI's Fugu is a multi-agent **orchestration system** delivered behind
one OpenAI-compatible API: the model itself delegates subtasks to a pool of
expert models. Fugu Ultra v2 (2026-09-11) targets peak multi-step capability;
Fugu Max targets the cost-performance Pareto frontier.

- Console: https://console.sakana.ai (create key, shown once)
- Base URL: `https://api.sakana.ai/v1` — fully OpenAI-compatible
- Pricing: $5 / 1M input, $30 / 1M output (Ultra v2), 1M context
- Also listed on OpenRouter as `sakana/fugu-ultra` (same key you already have)

JARVIS is pre-wired: a `sakana` provider exists in `config/models.toml` and
`providers/sakana_provider.py`. Add `SAKANA_API_KEY=...` to `config/.env` and
it activates automatically. It is intentionally **not** in the race/fallback
chain until latency is pinned — orchestration adds provider-side hops, so
measure before promoting (see PERF.md).
