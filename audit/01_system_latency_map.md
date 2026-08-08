# JARVIS MK-X — System Latency Map

## End-to-End Request Timeline

> **Note:** Timings marked `[E]` are estimated. All timings should be instrumented with `perf_counter()` before optimization.

```
User speaks / types
    ↓ [0ms]
Wake Word Detection (openwakeword)     — CPU, [E] 50-100ms per frame
    ↓
Voice Activity Detection (silero-vad)   — CPU, [E] 20-50ms per frame
    ↓
STT (Groq Whisper)                      — Network, [E] 200-500ms
    │  ├── WAV header construction       — CPU, [E] ~1ms
    │  ├── asyncio.to_thread()           — Queue wait, [E] ~0-5ms
    │  ├── HTTP to Groq API              — Network, [E] 150-400ms
    │  └── Response parsing              — CPU, [E] ~1ms
    ↓
Intent Router                           — CPU, [E] 0.1-2ms
    │  ├── text.lower().strip()          — CPU, [E] ~0.01ms
    │  ├── 100+ regex patterns (precompiled) — CPU, [E] 0.1-1ms
    │  └── Entity extraction             — CPU, [E] ~0.01ms
    ↓
Deterministic Response Check            — CPU, [E] ~0.01ms (cache hit)
    │  └── 28 pre-generated responses    — HashMap lookup
    ↓ [if action]
Acknowledgement Layer                   — CPU, [E] ~0.01ms
    ↓
Action Handler                          — Variable
    │  ├── Intent dispatch               — CPU, [E] ~0.01ms
    │  ├── Tool execution                — CPU/Network/Disk, ~10ms-120s
    │  └── Result formatting             — CPU, [E] ~1ms
    ↓ [if general.chat]
Context Retrieval                       — Disk, [E] 1-5ms
    │  ├── get_messages(max_turns=50)    — CPU, [E] ~0.5ms
    │  ├── Auto-compression (>15 turns)  — CPU, [E] 2-5ms (on trigger)
    │  └── System prompt cache check     — CPU, [E] ~0.01ms (hourly)
    ↓
Memory Search (vector)                  — Disk, [E] 5-50ms
    │  ├── LRU cache check              — CPU, [E] ~0.01ms
    │  ├── Cache miss: SQLite full scan  — Disk, [E] 5-50ms
    │  ├── Per-row json.loads()          — CPU, [E] 0.1ms × n rows
    │  ├── Cosine similarity             — CPU, [E] 0.01ms × n rows
    │  └── Sort + cache store            — CPU, [E] ~0.1ms
    ↓
LLM Provider Chain                      — Network, [E] 200-3000ms
    │  ├── Provider selection            — CPU, [E] ~0.01ms
    │  ├── Message serialization         — CPU, [E] ~0.1ms
    │  ├── HTTP setup + DNS + TLS        — Network, [E] 50-200ms  ← PERSISTENT CLIENT ELIMINATES THIS
    │  ├── Queue wait (Groq)             — Variable, [E] 0-500ms
    │  ├── TTFT (Time to First Token)    — Network, [E] 100-500ms
    │  └── Token generation (streaming)  — Network, [E] 50-200ms per token
    ↓
Response Stream                         — CPU, [E] ~1ms
    │  ├── Markdown stripping            — CPU, [E] ~0.1ms (6 regex)
    │  ├── Personality styling           — CPU, [E] ~0.01ms
    │  └── Context turn logging          — Disk, [E] 1-5ms (async)
    ↓
TTS Pipeline                            — CPU/Network, [E] 100-500ms
    │  ├── Sentence splitting            — CPU, [E] ~0.1ms
    │  ├── Cache check                   — CPU, [E] ~0.01ms
    │  ├── Phrase-level chunking         — CPU, [E] ~0.1ms
    │  ├── Piper synthesis (local)       — CPU, [E] 100-200ms per phrase
    │  │   └── BLOCKING: model.synthesize() — No asyncio.to_thread!
    │  ├── Edge-TTS (cloud fallback)     — Network, [E] 200-500ms
    │  ├── WAV encoding                  — CPU, [E] ~1ms
    │  └── Base64 encoding               — CPU, [E] ~1ms  ← BASE64 ADDS 33% OVERHEAD
    ↓
SSE Delivery                            — Network, [E] 1-5ms
    │  ├── json.dumps() per token        — CPU, [E] 0.05ms × n tokens  ← BATCH INSTEAD
    │  ├── json.dumps() per TTS chunk    — CPU, [E] 0.5ms (large base64)
    │  └── Flask thread blocking         — Thread pool, [E] ~0ms (if available)
    ↓
Frontend Rendering                      — Browser, [E] 1-16ms
    │  ├── JSON.parse()                  — CPU, [E] ~0.1ms
    │  ├── DOM text update               — Browser, [E] 1-5ms  ← BATCH WITH requestAnimationFrame
    │  ├── Audio element creation        — Browser, [E] 1-5ms
    │  └── Audio playback                — Hardware, [E] ~0ms (buffered)
    ↓
User hears response
```

## Performance Budget (Targets)

| Metric | Target | Current [E] | Status |
|--------|--------|-------------|--------|
| Wake word detection | <100ms | 50-100ms | ✅ On target |
| STT (end-to-end) | <300ms | 200-500ms | ⚠️ At limit |
| Intent classification | <5ms | 0.1-2ms | ✅ Under budget |
| TTFT (Time to First Token) | <300ms | 100-500ms | ⚠️ At limit |
| First spoken word | <500ms | 300-700ms | ❌ Over budget |
| Complete short response | <1.5s | 1-2s | ⚠️ At limit |
| Vector search | <10ms | 5-50ms | ❌ Over budget |

## Percentile Targets (Post-Instrumentation)

| Metric | P50 | P90 | P99 |
|--------|-----|-----|-----|
| STT | [TBD] | [TBD] | [TBD] |
| TTFT | [TBD] | [TBD] | [TBD] |
| TTS first phrase | [TBD] | [TBD] | [TBD] |
| Total response | [TBD] | [TBD] | [TBD] |

## Bottleneck Distribution

```
Network (LLM + STT + Edge-TTS):  ~60% of total latency
CPU (TTS synthesis + regex):      ~25% of total latency
Disk (SQLite + JSON):            ~10% of total latency
Browser rendering:               ~5% of total latency
```

## Key Insight

> At this stage, the largest remaining latency sources are no longer Python execution itself. They are:
> 1. Network round trips to LLM/STT services
> 2. Full-scan semantic memory retrieval
> 3. Serialization/rendering overhead in the streaming pipeline
> 
> Those areas will yield the biggest measurable reductions in end-to-end response time.
