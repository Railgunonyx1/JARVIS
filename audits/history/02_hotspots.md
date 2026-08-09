# JARVIS MK-X — Latency Hotspots

## Ranked by Estimated Impact (Highest First)

---

### 🔴 1. Persistent HTTP Connections Missing
**Impact:** 50-200ms saved per LLM/STT/TTS request
**Evidence:** Each request recreates TCP + TLS + DNS. For Groq alone, that's 50-150ms overhead per call.
**Fix:** Use `httpx.AsyncClient()` or `aiohttp.ClientSession()` for application lifetime. Initialize once at startup.

---

### 🔴 2. Vector Store O(n) Full Scan
**Impact:** 5-50ms now, will become seconds with 1000+ memories
**Evidence:** Every query runs `SELECT *` → `json.loads()` per row → cosine similarity → sort. Scales linearly.
**Fix:** Migrate to FAISS, sqlite-vec, or ChromaDB. Load embeddings into memory at startup, search O(log n).

---

### 🔴 3. `_piper()` Blocks Event Loop
**Impact:** 100-200ms per sentence, blocks all concurrent operations
**Evidence:** `model.synthesize()` is synchronous CPU-bound inside `async def`. Freezes streaming, memory saves, health checks.
**Fix:** `await asyncio.to_thread(model.synthesize, ...)` — dedicated worker, not parallel synthesis.

---

### 🟠 4. Sequential TTS Without Prebuffer
**Impact:** 3-8 seconds for long responses
**Evidence:** Current pipeline: Sentence 1 → TTS → play → Sentence 2 → TTS → play. Audio sits idle between sentences.
**Fix:** Pre-synthesize 1-2 sentences ahead. Keep audio queue fed so playback never stalls.

---

### 🟠 5. Base64 Audio Over SSE
**Impact:** 33% payload size increase, encoding/decoding overhead
**Evidence:** WAV → Base64 → JSON → SSE → decode → play. Base64 inflates every audio chunk.
**Fix:** Binary WebSocket frames for audio. Or at minimum, keep audio chunks small and batch.

---

### 🟠 6. Markdown Cleanup Per Token
**Impact:** 6 regex runs per token during streaming
**Evidence:** `_strip_md()` runs on every token yield. Unnecessary during streaming.
**Fix:** Strip markdown only at end of response, not per token. Or skip entirely during streaming.

---

### 🟠 7. Blocking Retry Loops in `open_app.py`
**Impact:** 300ms-7s wasted per failed app launch
**Evidence:** `time.sleep(0.3)` in 10-iteration loops with synchronous waits. Up to 3 loops per lookup.
**Fix:** Replace with async event-driven waits. Use `asyncio.wait_for()` with timeout.

---

### 🟠 8. Frontend Token-by-Token DOM Updates
**Impact:** Multiple browser repaints per response
**Evidence:** Each token triggers DOM mutation → layout → paint. Dozens of repaints per response.
**Fix:** Buffer tokens for 16-25ms, then update DOM once with `requestAnimationFrame()`.

---

### 🟡 9. Heavy Module Imports at Startup
**Impact:** 500-2000ms added to startup, 50-200MB RAM when loaded
**Evidence:** `cv2`, `mediapipe`, `PIL`, `sounddevice`, `mss` imported at module level.
**Fix:** Lazy imports inside functions that use them. Load only when mode requires them.

---

### 🟡 10. Context JSON Roundtrip Per Turn
**Impact:** 0.5-2ms per turn, scales with history size
**Evidence:** `json.loads()` + `json.dumps()` on entire history dict on every `add_turn()`.
**Fix:** Keep history as in-memory list. Only serialize on debounced save (already partially implemented).

---

### 🟡 11. Fire-and-Forget Logging Without Queue
**Impact:** Hundreds of tiny thread jobs per conversation
**Evidence:** `asyncio.create_task(asyncio.to_thread(...))` per log call creates unbounded thread churn.
**Fix:** Async queue → background writer → SQLite. One writer thread, bounded queue.

---

### 🟢 12. Process Sorting with `sorted()`
**Impact:** Negligible for <100 processes
**Evidence:** `sorted(all_procs, key=...)[:n]` full sort when only top-N needed.
**Fix:** `heapq.nlargest(n, all_procs, key=...)` — O(n) selection.

---

## Summary Matrix

| # | Hotspot | Impact | Location | Fix Difficulty |
|---|---------|--------|----------|----------------|
| 1 | No persistent HTTP | 🔴 HIGH | `providers/*.py` | Medium |
| 2 | Vector O(n) scan | 🔴 HIGH | `vector_store.py` | High |
| 3 | `_piper()` blocks loop | 🔴 HIGH | `tts.py:143` | Easy |
| 4 | Sequential TTS | 🟠 MED-HIGH | `tts.py:86` | Medium |
| 5 | Base64 audio | 🟠 MED-HIGH | `tts.py` + `server.py` | Medium |
| 6 | Markdown per token | 🟠 MED | `jarvis.py` | Easy |
| 7 | Blocking retries | 🟠 MED | `open_app.py:55` | Easy |
| 8 | Token-by-token DOM | 🟠 MED | `index.html` | Medium |
| 9 | Heavy imports | 🟡 LOW-MED | Multiple | Medium |
| 10 | Context JSON | 🟡 LOW | `context.py:80` | Medium |
| 11 | Unbounded logging | 🟡 LOW | `jarvis.py:591` | Medium |
| 12 | Process sorting | 🟢 MINIMAL | `process_manager.py:36` | Trivial |
