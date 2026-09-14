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
| **GitHub Models** | github.com/settings/tokens | `GITHUB_MODELS_API_KEY` | PAT, generous |
| **LLM7.io** | llm7.io | `LLM7_API_KEY` | 10 RPM / 60 req/hr |
| **Cohere** | dashboard.cohere.com/api-keys | `COHERE_API_KEY` | 20 RPM |
| **Z AI (GLM)** | z.ai / open.bigmodel.cn | `ZAI_API_KEY` | GLM-4.7-flash free |
| **Cerebras** | cloud.cerebras.ai | `CEREBRAS_API_KEY` | 30 RPM, very fast |
| **Mistral** | console.mistral.ai/api-keys | `MISTRAL_API_KEY` | 15 RPM |
| **Kilo Code** | kilo.ai | `KILO_CODE_API_KEY` | 200 req/hr proxy |

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
                    → kilo_code → agnes → llm7 → github_models → cohere → ...
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
