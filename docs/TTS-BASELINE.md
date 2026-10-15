# TTS Baseline — Kokoro-82M on i5-10210U (4C/8T)

**Date:** 2026-09-22
**Method:** `python scripts/bench_tts.py` — real production path
(`voice.tts()`, tuned ONNX session, numpy PCM, WAV framing), 3 trials ×
3 texts (short ack / medium / long), caches cleared between trials,
CPU load sampled during runs.

## Results (quiet machine)

| text   | audio  | mean rtf | p50  | min  | max  |
|--------|--------|----------|------|------|------|
| short  | 1.01s  | 1.04     | 1.02 | 1.00 | 1.09 |
| medium | 5.99s  | 0.68     | 0.68 | 0.66 | 0.71 |
| long   | 18.92s | 0.67     | 0.63 | 0.63 | 0.74 |
| **all**|        | **0.80** | **0.71** | 0.63 | 1.09 |

**Verdict: real-time capable.** p50 rtf 0.71; only the 1-second ack sits
at ~1.0 (fixed per-call overhead dominates at that length, and the ack
cache + sentence streaming already cover it in practice).

Context: the previous "4× slower than real-time" reading was taken under
heavy background load; this is the same code on a quiet machine.

## Thread sweep (same machine, same script)

| threads | ALL mean rtf | ALL p50 | notes |
|---------|--------------|---------|-------|
| 2       | 1.32         | 1.17    | starved — underprovisioned |
| **4**   | **0.80**     | **0.71**| **= physical cores; validated as default** |
| 8       | 1.54         | 1.47    | 100% CPU the whole run; HT contention |

8 threads pinned the machine at 100% load and was still 2× worse than 4.
The physical-core default (psutil-derived, `JARVIS_TTS_THREADS` override)
is confirmed correct in both quiet and loaded conditions.

## Engine notes

- Warmup (model load + first synthesis): 3.9–6.8s cold → eliminated at
  runtime by the bridge's background `prewarm()` at startup.
- Repeat text is 0ms via the audio LRU; re-phonemization of seen text is
  skipped via the phoneme LRU.
- int8 Kokoro was previously benchmarked ~10× slower than fp32 on this
  CPU — fp32 remains the default.
- Long replies: sentence-streaming in `orbit-browser/src/js/voice.js`
  overlaps synthesis with playback, so perceived latency ≈ one sentence.

## Rerun

```bash
python scripts/bench_tts.py                 # default (4 threads)
JARVIS_TTS_THREADS=8 python scripts/bench_tts.py   # any thread count
```
