# JARVIS MK-X — Metrics Baseline

## Current Performance Baseline (Pre-Optimization)

> **Note:** All timings marked `[E]` are estimated. Instrument every stage with `perf_counter()` to get real distributions.

---

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

---

## Percentile Targets (Post-Instrumentation)

| Metric | P50 | P90 | P99 |
|--------|-----|-----|-----|
| STT | [TBD] | [TBD] | [TBD] |
| TTFT | [TBD] | [TBD] | [TBD] |
| TTS first phrase | [TBD] | [TBD] | [TBD] |
| Total response | [TBD] | [TBD] | [TBD] |

---

## End-to-End Response Time

### Text Chat (Typical)

| Stage | Min [E] | Typical [E] | Max [E] |
|-------|---------|-------------|---------|
| STT | 200ms | 350ms | 800ms |
| Intent Router | 0.1ms | 1ms | 2ms |
| Deterministic Response | 0ms | 0ms | 0ms |
| Context + Memory | 1ms | 5ms | 50ms |
| LLM (first token) | 200ms | 400ms | 2000ms |
| LLM (generation) | 100ms | 300ms | 1000ms |
| TTS (first phrase) | 100ms | 175ms | 500ms |
| SSE + Rendering | 5ms | 10ms | 20ms |
| **TOTAL (first audio)** | **~600ms** | **~1250ms** | **~4300ms** |

### Voice Mode (Typical)

| Stage | Min [E] | Typical [E] | Max [E] |
|-------|---------|-------------|---------|
| Wake Word | 50ms | 100ms | 200ms |
| VAD (silence detect) | 300ms | 800ms | 2000ms |
| STT | 200ms | 350ms | 800ms |
| Intent + Context | 1ms | 6ms | 52ms |
| LLM (first token) | 200ms | 400ms | 2000ms |
| LLM (generation) | 100ms | 300ms | 1000ms |
| TTS (first phrase) | 100ms | 175ms | 500ms |
| **TOTAL (voice, end-to-end)** | **~1s** | **~2.1s** | **~6.5s** |

---

## Component Latency Baselines

### STT (Speech-to-Text)

| Component | Min [E] | Typical [E] | Max [E] |
|-----------|---------|-------------|---------|
| Groq Whisper | 200ms | 350ms | 800ms |
| Local fallback | 500ms | 1000ms | 2000ms |
| WAV header construction | ~1ms | ~1ms | ~1ms |
| Queue wait | 0ms | 2ms | 5ms |

### Intent Router

| Component | Min [E] | Typical [E] | Max [E] |
|-----------|---------|-------------|---------|
| Pattern matching | 0.1ms | 0.5ms | 1ms |
| Entity extraction | 0.01ms | 0.02ms | 0.05ms |
| **Total classify** | **0.1ms** | **0.5ms** | **2ms** |

### Context Engine

| Component | Min [E] | Typical [E] | Max [E] |
|-----------|---------|-------------|---------|
| History retrieval | 0.5ms | 1ms | 2ms |
| Auto-compression (triggered) | 2ms | 3ms | 5ms |
| Turn logging | 1ms | 2ms | 5ms |

### Vector Store

| Component | Min [E] | Typical [E] | Max [E] |
|-----------|---------|-------------|---------|
| LRU cache hit | 0.01ms | 0.01ms | 0.01ms |
| SQLite query | 5ms | 20ms | 50ms |
| Similarity computation | 0.5ms | 1ms | 2ms |
| **Total search** | **5ms** | **21ms** | **52ms** |

### LLM Provider Chain

| Component | Min [E] | Typical [E] | Max [E] |
|-----------|---------|-------------|---------|
| DNS lookup | 1ms | 5ms | 20ms |
| TCP/TLS handshake | 10ms | 30ms | 100ms |
| Request upload | 5ms | 10ms | 20ms |
| Provider queue | 0ms | 50ms | 500ms |
| First token | 100ms | 300ms | 1000ms |
| Token generation | 50ms | 100ms | 200ms per token |

### TTS (Text-to-Speech)

| Component | Min [E] | Typical [E] | Max [E] |
|-----------|---------|-------------|---------|
| Piper synthesis | 100ms | 150ms | 200ms per sentence |
| Edge-TTS | 200ms | 350ms | 500ms per sentence |
| WAV encoding | ~1ms | ~1ms | ~1ms |
| Base64 encoding | ~1ms | ~1ms | ~1ms |

### SSE Delivery

| Component | Min [E] | Typical [E] | Max [E] |
|-----------|---------|-------------|---------|
| json.dumps (text token) | 0.05ms | 0.05ms | 0.1ms |
| json.dumps (TTS chunk) | 0.5ms | 0.5ms | 1ms |
| Network delivery | 1ms | 2ms | 5ms |

### Browser Rendering

| Component | Min [E] | Typical [E] | Max [E] |
|-----------|---------|-------------|---------|
| JSON.parse | 0.1ms | 0.1ms | 0.2ms |
| DOM update | 1ms | 2ms | 5ms |
| Audio playback | 0ms | 0ms | 0ms (buffered) |

---

## Resource Usage Baselines

### Memory (RAM)

| State | Usage [E] |
|-------|-----------|
| Idle | 200-300MB |
| Active (text chat) | 400-500MB |
| Active (voice + vision) | 600-800MB |
| Peak | ~900MB |

### CPU

| State | Usage [E] |
|-------|-----------|
| Idle | 5-10% |
| Active (text chat) | 20-40% |
| Active (voice) | 40-60% |
| Active (vision + voice) | 70-90% |

### Disk I/O

| Operation | Latency [E] |
|-----------|-------------|
| SQLite read | 0.1-1ms |
| SQLite write | 1-5ms |
| Config reload | 10-50ms |
| Model loading | 100-500ms |

### Network

| Service | RTT [E] |
|---------|---------|
| Groq API | 50-200ms |
| OpenRouter API | 100-300ms |
| Edge-TTS | 100-400ms |
| Local (Ollama) | 1-5ms |

---

## Concurrency Baselines

| Resource | Current Limit [E] |
|----------|-------------------|
| SSE streams | 1-3 concurrent |
| LLM requests | 1-2 concurrent (queue limited) |
| TTS synthesis | 1-3 concurrent (phrase-level) |
| WebSocket connections | 1-5 concurrent |
| Thread pool (STT) | 1 thread |
| Thread pool (TTS) | 1 thread |
| Thread pool (File I/O) | 1-2 threads |
| Flask workers | 4-8 threads |

---

## Cache Efficiency Baselines

| Cache | Hit Rate [E] | Miss Penalty |
|-------|--------------|--------------|
| LRU (Vector Store) | 60-80% | 5-50ms |
| Response Cache (Deterministic) | 100% | 0.01ms |
| System Prompt Cache | 100% | 100-200ms (hourly refresh) |

---

## Reliability Baselines

| Metric | Target | Current [E] |
|--------|--------|-------------|
| Uptime | 99% | ~95% |
| LLM failure rate | <5% | 5-10% |
| TTS failure rate | <1% | 1-2% |
| STT failure rate | <2% | 2-5% |
| Action failure rate | <5% | 10-20% |
| LLM fallback time | <1s | 1-3s |
| TTS fallback time | <0.5s | 0.5-1s |
| STT fallback time | <2s | 2-5s |
| Full restart time | <3s | 5-10s |

---

## Instrumentation Requirements

### Every Stage Must Measure

```python
import time

async def process_text_streaming(self, text: str, ...):
    metrics = {}
    
    # STT
    t0 = time.perf_counter()
    # ... STT processing ...
    metrics["stt_ms"] = (time.perf_counter() - t0) * 1000
    
    # Intent
    t0 = time.perf_counter()
    intent = await self._intent_router.classify(text)
    metrics["intent_ms"] = (time.perf_counter() - t0) * 1000
    
    # Context
    t0 = time.perf_counter()
    context = await self._context_engine.get_history()
    metrics["context_ms"] = (time.perf_counter() - t0) * 1000
    
    # Memory
    t0 = time.perf_counter()
    memory = await self._memory.search_similar(text)
    metrics["memory_ms"] = (time.perf_counter() - t0) * 1000
    
    # LLM TTFT
    t0 = time.perf_counter()
    first_token = await llm.generate(messages)
    metrics["llm_ttft_ms"] = (time.perf_counter() - t0) * 1000
    
    # TTS first phrase
    t0 = time.perf_counter()
    first_audio = await tts.synthesize(first_sentence)
    metrics["tts_first_ms"] = (time.perf_counter() - t0) * 1000
    
    # Total
    metrics["total_ms"] = (time.perf_counter() - start) * 1000
    
    return metrics
```

### Report Percentiles

After collecting 100+ requests:

```python
def report_metrics(metrics: dict):
    for key, values in metrics.items():
        sorted_values = sorted(values)
        n = len(sorted_values)
        print(f"{key}:")
        print(f"  P50: {sorted_values[n // 2]:.1f}ms")
        print(f"  P90: {sorted_values[int(n * 0.9)]:.1f}ms")
        print(f"  P99: {sorted_values[int(n * 0.99)]:.1f}ms")
```

---

## Validation Test Scenarios

1. **Cold start:** First request after system boot
2. **Warm steady-state:** 10 minutes of continuous use
3. **Peak load:** 100 rapid requests in 1 minute
4. **Endurance:** 1 hour continuous operation
5. **Recovery:** Service restart after crash

---

## Next Steps

1. **Instrument all stages** with `perf_counter()`
2. **Collect 100+ requests** to get real distributions
3. **Update baselines** with measured values
4. **Set up continuous monitoring** for regression detection
5. **Establish alert thresholds** for resource exhaustion
