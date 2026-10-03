# Voice Engines

JARVIS can speak and listen through several engines. You configure them with
environment variables; nothing needs a code change, and nothing needs an
account for the two local/keyless paths.

`GET /v1/voice/status` reports every engine with a live `available` flag and,
when it is unavailable, the exact `reason` and the `key_env` that would turn
it on. The Orbit picker renders that list directly: unavailable engines are
greyed out with the reason as their tooltip, never silently hidden.

---

## Text to speech

| Engine | Needs | Free tier | Quality |
|---|---|---|---|
| **elevenlabs** | `ELEVENLABS_API_KEY` | 10k credits/mo | Most natural; free plan is **non-commercial** |
| **azure** | `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` | 500k chars/mo (F0, card required) | Very good, 100+ locales |
| **polly** | AWS credentials + `pip install boto3` | 12mo of 5M std / 1M neural chars/mo **for AWS accounts created before 15 Jul 2025**; newer accounts get $200 credit | Very good |
| **google** | `GOOGLE_API_KEY` | 1M chars/mo Chirp 3 HD, 4M WaveNet/Standard (billing must be enabled) | Very good, SSML support |
| **edge** | nothing (`pip install edge-tts`) | Unlimited | Good; unofficial Microsoft endpoint |
| **kokoro** | nothing (`kokoro-onnx` in requirements) | Unlimited | Good; local, offline, benchmarks at rtf 0.71 |
| **sapi** | nothing (Windows) | Unlimited | Robotic; the guaranteed last resort |

### Choosing

`voice_model: "auto"` walks every **available** engine, best quality first:
ElevenLabs → Azure → Polly → Google → Edge → Kokoro → SAPI. If one fails
mid-turn the next one is tried, so a flaky network provider cannot leave you
without a voice. SAPI closes the chain, so a machine with no keys and no
network still speaks.

Pinning `voice_model` runs **only** that engine, so an explicit choice
surfaces its real error instead of quietly answering from a different one.

### Benchmarks

Kokoro-82M on an i5-10210U (4C/8T): p50 real-time factor 0.71, meaning
synthesis runs faster than real time. See [TTS-BASELINE.md](TTS-BASELINE.md).
Override the thread count with `JARVIS_TTS_THREADS`.

---

## Speech to text

**STT has no local default.** With no keys configured, push-to-talk returns
503 and names the variables that would fix it. This is the one part of the
voice stack that needs an account.

| Engine | Needs | Free tier |
|---|---|---|
| **groq** | `GROQ_API_KEY` | 20 req/min, 2,000/day, 7,200 audio-sec/hour, 28,800/day, 25 MB, 10s minimum billed |
| **deepgram** | `DEEPGRAM_API_KEY` | $200 account credit on signup |
| **elevenlabs** | `ELEVENLABS_API_KEY` | Shares the 10k TTS credit pool |

`GROQ_API_KEY` is already a first-class key in this project — it heads the
provider router's default fallback chain — so it is the cheapest way to make
push-to-talk work without a new signup. When `engine` is not specified the
server picks the first available engine.

`POST /v1/stt` accepts an optional `engine` field (`groq`, `deepgram`,
`elevenlabs`). Pinning to an unconfigured engine names *that* engine's missing
variable rather than falling back to another provider silently.

---

## Setup

Add whichever keys you want to your environment (no `.env` loader is
required — the process reads them directly):

```bash
# Zero config: Edge TTS + Kokoro already work out of the box.
# Cheapest STT:
export GROQ_API_KEY=gsk_...

# Optional cloud TTS:
export ELEVENLABS_API_KEY=...       # best quality, non-commercial on free tier
export GOOGLE_API_KEY=...           # 1M chars/mo free (enable billing)
export AZURE_SPEECH_KEY=...         # both of these, or neither works
export AZURE_SPEECH_REGION=eastus
```

Restart the bridge and check what it sees:

```bash
curl -s -X POST http://127.0.0.1:8170/v1/voice/status | python -m json.tool
```

---

## Free-tier caveats

These allowances are **published vendor numbers as of 2026-09, not
contractual capacity.** Rate limits bite before monetary limits do:

- Groq counts a **minimum of 10 seconds** per request, so many two-second
  voice commands burn allowance faster than their real duration.
- Amazon's 12-month Polly tier only applies to accounts created **before
  15 July 2025**. Newer accounts get $200 of AWS credits instead.
- Google's free STT minutes apply to Speech-to-Text **V1 only** — V2 is
  billed from the first minute.
- Azure's F0 quota is a development allowance, not a production capacity
  promise.
- Edge TTS uses an undocumented Microsoft endpoint. It is excellent for
  personal use but can break without notice, which is why it is never the
  only thing standing between you and silence.

Recheck before depending on any of these.