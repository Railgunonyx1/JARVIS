# JARVIS MK-X — Phase 0 Baseline Metrics

**Date:** 2026-07-27
**Environment:** Windows 10, 8GB RAM, i5-10210U, Python 3.11.9

## Startup

| Metric | Value |
|--------|-------|
| Total cold start | 13.37s |
| Module imports | 1,548ms |
| Construction | 1,097ms |
| Startup() call | 10,729ms |
| RSS before | 27MB |
| RSS after startup | 230MB |
| RSS delta | +198MB |
| Threads before | 4 |
| Threads after | 17 |

### Slowest module imports
| Module | Time |
|--------|------|
| web.server | 818ms |
| core.jarvis | 572ms |
| core.config | 150ms |
| memory.vector_store | 7ms |

## Memory

| Stage | RSS | tracemalloc |
|-------|-----|-------------|
| Baseline (empty) | 26MB | 0MB |
| After construction | 82MB | 23MB |
| After startup | 284.6MB | 68.6MB |
| Idle 5s | 291.5MB | 68.6MB |
| Idle 30s | 294.3MB | 68.6MB |

**Idle growth:** +2.9MB (potential leak)
**Top allocations:** importlib (26MB), abc (4MB), typing_extensions (2MB), pydantic (1.5MB)

## Latency

| Metric | Value |
|--------|-------|
| TTFT avg | 700ms |
| TTFT P50 | 1ms (deterministic) |
| TTFT P95 | 4,285ms (LLM) |
| Intent classification | 1ms |
| Token throughput | 458 tok/s |
| Total response avg | 1,851ms |

## Voice

| Metric | Value |
|--------|-------|
| TTS warmup | 7,203ms |
| TTS first audio avg | 1,448ms |
| TTS first audio best | 948ms |
| TTS first audio worst | 2,891ms |
| TTS full synthesis avg | 1,724ms |
| TTS precache | 5,744ms |

## Telemetry

| Metric | Value |
|--------|-------|
| System stats collection | 162ms/call |
| Telemetry overhead | 6.27ms/call |
| JSON serialization | 0.022ms |
| CPU overhead | 0% |

## Priority Optimization Targets

1. **TTS warmup (7.2s)** — lazy-load on first voice request → saves 7s startup
2. **TTS precache (5.7s)** — defer to background after UI ready → saves 5.7s
3. **web.server import (818ms)** — lazy import in startup → saves 0.8s
4. **Idle RAM (294MB)** — lazy voice pipeline → saves ~400MB
5. **TTS first audio (1448ms)** — streaming synthesis + pre-warmed cache → target <500ms
6. **Telemetry overhead (162ms)** — cache system stats, reduce poll frequency → target <50ms
