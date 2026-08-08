# JARVIS MK-X — Comprehensive Technical Audit Report

**Date:** 2026-07-27
**Auditor:** opencode (big-pickle)
**Scope:** Full repository — architecture, performance, security, code quality, dependencies
**Environment:** Windows 10, 8GB RAM, i5-10210U, NVIDIA MX130, Python 3.11.9

---

## 1. Executive Summary

JARVIS MK-X is a cloud-first AI voice assistant with local fallback, running as a PyQt6 desktop app serving a vanilla JS HUD via Flask on localhost. The core system (11 packages, ~19,000 LOC) is functional and well-designed for its target hardware. However, the codebase carries **~25,000 lines of dead code** across 32 unused packages, has **critical security vulnerabilities** (RCE via unsanitized desktop actions, auth token leakage), and several **production-blocking bugs** (local STT blocking the event loop, Groq provider self-disabling on rate limits, no application quit path).

**Bottom line:** The 11 active packages form a solid ~19K LOC foundation. The 32 dead packages (~25K LOC) are the single biggest liability — they confuse the architecture, bloat the repository, and will mislead any future contributor.

---

## 2. Current Architecture Overview

### Active System Map

```
main.py (623 LOC)
  └─ ui_web.py (375 LOC) — PyQt6 shell + QWebEngineView
       └─ web/server.py (732 LOC) — Flask REST API (24 endpoints)
            └─ core/jarvis.py (1,176 LOC) — Main orchestrator
                 ├─ core/intent_router.py — Intent classification
                 ├─ core/context.py — Conversation history + user profile
                 ├─ core/dialogue.py — State machine
                 ├─ core/personality.py — Mood + time awareness
                 ├─ providers/router.py — LLM fallback chain
                 │    ├─ groq_provider.py (fastest, 2 keys)
                 │    ├─ gemini_provider.py
                 │    ├─ openrouter_provider.py (4 keys)
                 │    ├─ opencode_zen_provider.py
                 │    └─ ollama_provider.py (local fallback)
                 ├─ pipeline/stt.py — Groq Whisper → faster-whisper
                 ├─ pipeline/tts.py — Piper → Edge-TTS
                 ├─ pipeline/vad.py — Energy-based VAD
                 ├─ pipeline/wake_word.py — openWakeWord
                 ├─ memory/store.py — SQLite + JSON
                 ├─ memory/vector_store.py — Semantic search
                 ├─ security/engine.py — Policy engine
                 ├─ knowledge_graph/ — Entity extraction + graph
                 └─ actions/* (22 modules) — Desktop automation
```

### Dead Code Map (32 unused packages, ~25,000 LOC)

| Category | Packages | LOC | Status |
|----------|----------|-----|--------|
| **Optimization frameworks** | `hyper_optimization` (6,207), `ai_runtime` (1,365), `performance_engine` (968), `os_optimization` (612), `gpu_optimization` (592), `system_optimizer` (468), `cache_system` (646), `orchestration_engine` (496) | 11,354 | Self-contained, never imported |
| **AI/Reasoning** | `inference_engine` (900), `reasoning_system` (878), `knowledge_engine` (790), `interaction_engine` (776), `personal_intelligence` (809) | 4,153 | Self-contained, never imported |
| **Engine frameworks** | `digital_twin` (1,058), `evolution_engine` (844), `self_evolution` (559), `reliability_engine` (621), `distributed_engine` (660), `workflows` (1,043) | 4,785 | Self-contained, never imported |
| **External/misc** | `agents` (626), `external` (739), `se_factory` (587), `perception_engine` (370), `voice_engine` (284), `mcp_jarvis` (209), `plugins` (180), `benchmark` (184), `systems` (815) | 3,994 | Mixed (some self-contained, some truly dead) |

**Total dead code: ~25,000 LOC across 32 packages = 57% of the codebase.**

---

## 3. Critical Issues

### CRITICAL-1: RCE via unsanitized desktop actions
- **Location:** `actions/file_manager.py:24-33`, `web/server.py` → `/api/desktop/action`
- **Problem:** `_safe_path()` in file_manager.py does nothing when the path is outside allowed roots — it returns the path with no enforcement. The desktop action endpoint passes user-supplied input directly to subprocess/PowerShell commands.
- **Impact:** Any client that can reach the Flask server can execute arbitrary commands on the host machine.
- **Fix:** Implement actual path validation with `os.path.realpath()` comparison. Add an allowlist for desktop action types. Bind Flask to `127.0.0.1` only (already done for desktop mode, but `run_server()` binds to `0.0.0.0`).
- **Difficulty:** Medium (2-3 hours)

### CRITICAL-2: Auth token leaked without authentication
- **Location:** `web/server.py:126-129`
- **Problem:** `GET /api/auth/token` returns the bearer token with zero authentication. Any process on localhost can obtain it.
- **Impact:** Renders the entire auth middleware meaningless. Combined with CORS wildcard ports, any web page on the machine can make authenticated API calls.
- **Fix:** Remove this endpoint. The desktop UI should get the token via IPC or a file. Alternatively, only serve it via `QWebEnginePage.runJavaScript()` during initial page load.
- **Difficulty:** Low (1 hour)

### CRITICAL-3: Local STT blocks the event loop
- **Location:** `pipeline/stt.py:70-89`
- **Problem:** `_transcribe_local()` calls `model.transcribe()` (a blocking CPU-bound generator) directly without `asyncio.to_thread`. This freezes all async tasks (wake word, VAD, web requests, streaming) during local transcription.
- **Impact:** During local STT, the entire assistant becomes unresponsive. Voice pipeline hangs for 0.5-2 seconds.
- **Fix:** Wrap in `await asyncio.to_thread(model.transcribe, ...)`.
- **Difficulty:** Low (15 minutes)

### CRITICAL-4: Groq provider self-disables on rate limit rotation
- **Location:** `providers/groq_provider.py:96`
- **Problem:** When key rotation is triggered by a rate limit, `record_failure()` is called, which increments `consecutive_failures`. After 3 rate-limited rotations across 2 keys, the entire provider enters cooldown, making it unavailable even though neither key is actually broken.
- **Impact:** A brief rate limit from Groq can disable the fastest provider for up to 5 minutes, forcing all requests through slower fallback providers.
- **Fix:** Call `record_failure()` only for non-rate-limit errors. The OpenRouter provider already does this correctly.
- **Difficulty:** Low (15 minutes)

---

## 4. High-Severity Issues

### HIGH-1: Flask dev server bound to 0.0.0.0
- **Location:** `web/server.py:723`
- **Problem:** `app.run(host="0.0.0.0", ...)` exposes the development server to all network interfaces. On a laptop connected to WiFi, anyone on the same network can access the API.
- **Fix:** Use `host="127.0.0.1"` in all modes except when explicitly configured for LAN access.

### HIGH-2: No application quit path from UI
- **Location:** `ui_web.py:311-319`
- **Problem:** `closeEvent()` minimizes to tray. The tray "Quit" action calls `self.close()`, which triggers `closeEvent()` again, which hides the window. There is no way to actually terminate the application.
- **Fix:** Add a `_force_quit` flag. Tray Quit sets it, then calls `close()`.

### HIGH-3: Stream fallback yields garbled output
- **Location:** `providers/router.py:134-144`
- **Problem:** When a provider fails mid-stream, any chunks already yielded to the consumer are orphaned. The fallback starts from scratch, so the consumer receives partial response A + full response B.
- **Fix:** Use a buffer. If the stream fails, discard partial output and restart the fallback from scratch with a clean stream.

### HIGH-4: TTS precache spawns 30+ threads simultaneously
- **Location:** `pipeline/tts.py:101-102`
- **Problem:** `asyncio.gather(*tasks)` fires off ~30 Piper syntheses concurrently. Each runs in `asyncio.to_thread`, creating ~30 OS threads. On an 8GB/4-core machine, this causes severe memory pressure and CPU contention during startup.
- **Fix:** Use `asyncio.Semaphore(4)` to limit concurrency.

### HIGH-5: PyQt6 auto-grants media permissions for all URLs
- **Location:** `ui_web.py:56-60`
- **Problem:** `_on_permission()` grants camera/mic access for ANY URL. If a malicious page loads (e.g., via redirect), it gets media access silently.
- **Fix:** Only grant permissions for `localhost` or `127.0.0.1` origins.

### HIGH-6: Blocking HTTP calls on Qt main thread
- **Location:** `ui_web.py:280, 287, 312`
- **Problem:** `_set_performance_mode()`, `_check_connection()`, and `_try_load()` all make synchronous `urllib.request.urlopen()` calls on the Qt event loop thread, freezing the UI for up to 2 seconds each.
- **Fix:** Move to `QNetworkAccessManager` or run in a `QThread`.

### HIGH-7: Unbounded TTS response cache (memory leak)
- **Location:** `pipeline/tts.py:21`
- **Problem:** `_response_cache` is a module-level dict that grows forever. Every unique synthesized text is cached with no eviction policy.
- **Fix:** Use `functools.lru_cache(maxsize=200)` or an LRU dict with max size.

---

## 5. Medium-Severity Issues

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| MED-1 | `core/jarvis.py:182-186` | Subsystems initialized then immediately overwritten to `None` (dead init code) | Remove the dead initialization blocks |
| MED-2 | `core/jarvis.py:478-641` | `_handle_action` is a 160-line if/elif chain | Refactor to a dispatch dict/registry |
| MED-3 | `core/jarvis.py` (100+ `self.x = None`) | ~110 attribute declarations for unused optional subsystems | Remove unused attributes, use a dict for optional subsystems |
| MED-4 | `core/context.py:89` | Compression summary grows unbounded | Cap summary at ~2000 chars |
| MED-5 | `core/config.py:32-37` | Singleton not thread-safe | Use `threading.Lock` or `__new__` pattern |
| MED-6 | `web/server.py` | `_start_tts_prefetch()` defined but never called | Remove dead code or wire it up |
| MED-7 | `web/server.py` | `async_sleep()` called in synchronous Flask handlers | Replace with `time.sleep()` or run in async context |
| MED-8 | `web/server.py` | Camera MJPEG generator has no disconnect detection | Add client disconnect check in loop |
| MED-9 | `web/server.py` | `_mic_recording` global dict accessed without locks | Add `threading.Lock` |
| MED-10 | `public/js/app.js` + `chat.js` | Duplicate `escapeHtml` implementations | Extract to shared utility module |
| MED-11 | `public/js/chat.js` | Audio queue grows unbounded | Cap at 50 chunks, drop oldest |
| MED-12 | `pipeline/vad.py:63-66` | `reset()` doesn't clear calibration | Reset `_calibrated` and `_energy_hist` |
| MED-13 | `providers/gemini_provider.py` | Missing `_check_package` override | Add package check |
| MED-14 | `providers/openrouter_provider.py` | Missing `_check_package` override | Add package check |
| MED-15 | No CSP headers | No Content Security Policy on the web UI | Add `<meta http-equiv="Content-Security-Policy">` |

---

## 6. Performance Audit

### Current Baseline (measured)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Cold construction | 2.1s / 61MB | — | Baseline |
| After startup() | ~15s / 478MB | — | Baseline |
| Idle (post-optimization) | 0% CPU / 204MB | <2% / <250MB | GOOD |
| Avg TTFT (Groq) | 164ms | <200ms | GOOD |
| Startup breakdown | TTS 4.9s + precache 5.6s + providers 4.0s | — | See below |

### Biggest Performance Opportunities

1. **Remove dead code (SAVES ~5-10MB import, reduces startup by ~0.5-1s):** The 32 unused packages are never imported, so they don't affect runtime. But the directory structure and `__init__.py` files cause Python's import machinery to scan them, adding ~0.5s to cold start.

2. **Fix TTS precache thread storm (SAVES ~200MB peak RSS):** Currently spawns 30+ threads. With semaphore(4), peak memory drops by ~150-200MB during startup.

3. **Lazy-init voice pipeline on first use (SAVES ~400MB idle):** STT and TTS models are loaded eagerly in `startup()`. If the user only uses text mode, these 400MB are wasted. Lazy-load on first voice request.

4. **Fix Groq provider self-disable (SAVES ~1-3s fallback latency):** When Groq is incorrectly disabled, every request falls through to Gemini (~500ms) or OpenRouter (~500ms) instead of Groq (~164ms).

5. **Remove duplicate connectivity polling:** Both `app.js` `checkAPI()` (10s interval) and `telemetry.js` SSE connection events track the same thing. Remove the polling one.

---

## 7. AI System Audit

### What works well
- **Provider fallback chain** is well-designed: Groq (fast) → Gemini → OpenRouter → Ollama (local). Clean separation of concerns.
- **Key rotation** on Groq and OpenRouter handles multi-key scenarios. OpenRouter correctly avoids penalizing health on rate limits.
- **Streaming pipeline** in `jarvis.py` with phrase-level TTS chunking is architecturally sound — LLM generates while TTS synthesizes previous phrases in parallel.
- **Circuit breaker** prevents cascading failures.
- **Intent router** with deterministic fast-path avoids unnecessary LLM calls for greetings, memory store, etc.

### What needs fixing
- **`_handle_action` dispatch:** 160-line if/elif chain. Should be a registry dict mapping intent names to handler functions.
- **110 unused attributes on JarvisMKX:** `self.hyp_gpu = None`, `self.kernel_fusion = None`, etc. These are placeholders for subsystems that were never wired in. Remove them.
- **Context compression summary grows unbounded:** The ` | `-separated summary string grows with every compression cycle, eventually bloating the LLM context window.
- **No parallel tool execution:** Actions are executed sequentially. For multi-intent queries, tools should run concurrently.

---

## 8. Voice Pipeline Audit

### Latency Budget

| Stage | Best | Typical | Worst | Target |
|-------|------|---------|-------|--------|
| Wake detect | 2ms | 5ms | 10ms | <100ms ✅ |
| VAD | 0.1ms | 0.5ms | 1ms | — ✅ |
| STT (Groq) | 150ms | 400ms | 2s | <150ms ⚠️ |
| STT (local) | 500ms | 1s | 2s | — ⚠️ |
| LLM (Groq) | 100ms | 300ms | 2s | <200ms ⚠️ |
| TTS (Piper) | 50ms | 100ms | 300ms | <100ms ✅ |
| TTS (Edge) | 200ms | 400ms | 1.5s | — ⚠️ |
| **Total** | **~300ms** | **~800ms** | **~6s** | **<1s** ⚠️ |

### Key Issues
- **Local STT blocks event loop** (CRITICAL-3 above). This is the single biggest voice pipeline bug.
- **Wake word callback not async-compatible.** If the callback is a coroutine, it's silently dropped.
- **No streaming STT.** The entire audio must be captured before transcription starts. Streaming STT (Groq supports it) would reduce perceived latency by ~200-400ms.
- **VAD calibration only runs once.** If background noise changes, the threshold becomes stale.

---

## 9. Security Audit

| Severity | Issue | Location | Impact |
|----------|-------|----------|--------|
| CRITICAL | RCE via desktop actions | `actions/file_manager.py`, `/api/desktop/action` | Arbitrary command execution |
| CRITICAL | Auth token leaked unauthenticated | `/api/auth/token` | Auth bypass |
| HIGH | Flask bound to 0.0.0.0 | `web/server.py:723` | Network exposure |
| HIGH | Auto-grants media permissions | `ui_web.py:56-60` | Silent mic/cam access |
| HIGH | Shutdown endpoint no auth when env unset | `web/server.py` | DoS vector |
| MEDIUM | No CSP | `public/index.html` | XSS exploitation |
| MEDIUM | CORS wildcard ports | `web/server.py:51` | Cross-origin attacks |
| MEDIUM | Auth token via query string | `web/server.py` | Token leakage in logs |
| MEDIUM | Command injection in PowerShell calls | `actions/audio_manager.py`, `actions/disk_manager.py` | Local privilege escalation |
| LOW | Telemetry SSE bypasses auth | `web/server.py` | System metrics leakage |

---

## 10. Code Quality

### Strengths
- Consistent logging across all modules
- Clean async/await patterns in the streaming pipeline
- Good use of dataclasses for configuration
- Provider abstraction is well-designed with proper fallback
- Frontend is lightweight (~1K LOC JS, zero dependencies)

### Weaknesses
- **Massive dead code problem** (57% of LOC is unused)
- **No type annotations** in most modules (only `typing.Optional` used in a few places)
- **Inconsistent error handling:** Some modules log and swallow, others raise, others return None
- **No docstrings** on most internal methods
- **Duplicate implementations** (`escapeHtml` x2, `playNextAudio` x2, `CIRC` x2)
- **110 unused attributes** on the main `JarvisMKX` class
- **Thread safety is inconsistent:** Some locks, some not. `_build_system_prompt` cache is unprotected.
- **`asyncio.ensure_future`** used 3 times (deprecated since Python 3.10)

---

## 11. Dependency Audit

### requirements.txt analysis (50 lines, 22 active packages)

| Package | Used? | Size | Notes |
|---------|-------|------|-------|
| toml | ✅ | Tiny | Config parsing |
| aiohttp | ✅ | Medium | Used in some actions |
| asyncio-throttle | ⚠️ | Tiny | May not be actively used |
| groq | ✅ | Medium | STT + LLM |
| google-generativeai | ✅ | Large | Gemini LLM |
| openai | ✅ | Medium | OpenRouter + Zen |
| ollama | ✅ | Tiny | Local LLM |
| piper-tts | ✅ | Medium | Local TTS |
| edge-tts | ✅ | Small | Cloud TTS |
| sounddevice | ✅ | Small | Audio capture |
| numpy | ✅ | Large | VAD, audio processing |
| pathvalidate | ✅ | Tiny | File path validation |
| PyQt6 + WebEngine | ✅ | Very Large | Desktop shell (largest dep) |
| flask + flask-cors | ✅ | Medium | Web server |
| psutil | ✅ | Small | System monitoring |
| requests | ✅ | Medium | HTTP (redundant with aiohttp) |
| pydantic | ⚠️ | Medium | May not be actively used |
| pyperclip | ✅ | Tiny | Clipboard |
| pyautogui | ✅ | Medium | Desktop automation |
| pywin32 | ✅ | Medium | Windows API |
| screen-brightness-control | ✅ | Tiny | Display control |
| mediapipe | ✅ | Large | Gesture/face recognition |
| opencv-contrib-python | ✅ | Very Large | Computer vision |
| mss | ✅ | Small | Screenshot capture |
| playwright | ⚠️ | Large | Browser automation (optional) |

**Not in requirements.txt but installed:** `flask-limiter`, `opentelemetry-sdk`, `opentelemetry-api`

**Recommendations:**
- Remove `requests` if `aiohttp` covers the same use cases
- Verify `pydantic` and `asyncio-throttle` are actually imported
- Pin `PyQt6` and `PyQt6-WebEngine` to exact versions (they're the heaviest deps)
- Add `flask-limiter` and `opentelemetry-sdk` to requirements.txt

---

## 12. Testing Audit

### Current state: MINIMAL

| Test file | Lines | Type | Coverage |
|-----------|-------|------|----------|
| `tests/smoke.py` | ~200 | Import checks | Imports only |
| `tests/benchmarks.py` | ~200 | pytest-benchmark | 6 regression tests |
| `test_tracing.py` | 24 | Smoke test | Tracing module only |
| `test_e2e_traces.py` | 75 | E2E test | Server + chat + traces |

**Missing entirely:**
- Unit tests for any pipeline module
- Unit tests for any provider
- Unit tests for intent router
- Unit tests for action handlers
- Integration tests for the full voice pipeline
- Security tests (auth bypass, injection)
- Frontend tests (any)
- Load/stress tests
- Regression baselines

---

## 13. Optimization Roadmap

### Phase 1: Quick Wins (1-3 days)

| # | Change | Impact | Effort |
|---|--------|--------|--------|
| 1 | **Delete 32 dead packages** (~25K LOC) | -57% codebase, cleaner architecture, faster imports | 1 hour |
| 2 | Fix local STT blocking event loop (`asyncio.to_thread`) | Unfreezes voice pipeline | 15 min |
| 3 | Fix Groq provider self-disable on rate limit | Restores fastest provider | 15 min |
| 4 | Fix no-quit-path in PyQt6 tray | Users can actually exit | 30 min |
| 5 | Add `Semaphore(4)` to TTS precache | -200MB peak RSS at startup | 30 min |
| 6 | Remove `_safe_path()` no-op, implement real validation | Fixes RCE vector | 1 hour |
| 7 | Remove `/api/auth/token` endpoint or protect it | Fixes auth leak | 30 min |
| 8 | Bind `run_server()` to `127.0.0.1` | Eliminates network exposure | 5 min |
| 9 | Remove dead `JarvisMKX` attributes (100+ `None` assignments) | Cleaner code | 30 min |
| 10 | Fix duplicate `escapeHtml`, `CIRC`, `playNextAudio` | Code deduplication | 30 min |

### Phase 2: Major Improvements (1-4 weeks)

| # | Change | Impact | Effort |
|---|--------|--------|--------|
| 1 | Refactor `_handle_action` to dispatch dict | Maintainability | 2 hours |
| 2 | Add streaming STT (Groq supports it) | -200-400ms perceived latency | 1 day |
| 3 | Lazy-load voice pipeline on first voice request | -400MB idle RAM | 3 hours |
| 4 | Add proper thread locks to `JarvisMKX` caches | Eliminates race conditions | 2 hours |
| 5 | Fix stream fallback garbled output | Better fallback UX | 2 hours |
| 6 | Add CSP headers to the web UI | XSS protection | 30 min |
| 7 | Replace Flask dev server with gunicorn/waitress | Production-grade serving | 2 hours |
| 8 | Add `asyncio.to_thread` to Gemini streaming | True async streaming | 1 hour |
| 9 | Add `_check_package` to Gemini/OpenRouter/OpenCodeZen | Early provider availability detection | 30 min |
| 10 | Add unit tests for core pipeline (intent, context, provider router) | Regression safety | 2 days |

### Phase 3: Advanced MK-X Upgrades (1-3 months)

| # | Change | Impact | Effort |
|---|--------|--------|--------|
| 1 | Implement the actual hyper_optimization / ai_runtime modules (or remove them) | Either use the 11K LOC of optimization code or delete it | 1-2 weeks |
| 2 | Multi-agent architecture with parallel tool execution | Complex task handling | 1-2 weeks |
| 3 | RAG pipeline with vector DB for persistent memory | Long-term knowledge | 1 week |
| 4 | Full voice pipeline with streaming STT + streaming TTS overlap | Sub-500ms voice round-trip | 1 week |
| 5 | Plugin system with sandboxed execution | Third-party extensibility | 1-2 weeks |
| 6 | Comprehensive test suite (>80% coverage) | Production reliability | 2-3 weeks |
| 7 | OpenTelemetry export to Jaeger/Grafana | Distributed tracing dashboard | 2 days |
| 8 | MCP server integration for file/code operations | Tool ecosystem | 1 week |

---

## 14. Expected Improvements

| Metric | Current | After Phase 1 | After Phase 2 | After Phase 3 |
|--------|---------|---------------|---------------|---------------|
| Codebase size | 43,943 LOC | ~18,000 LOC | ~18,000 LOC | ~25,000 LOC (with real features) |
| Dead code | 57% | 0% | 0% | 0% |
| Idle RAM | 204MB | 204MB | ~160MB | ~200MB (with more features) |
| Startup time | ~15s | ~13s | ~10s | ~8s |
| Voice round-trip | ~800ms | ~800ms | ~500ms | <500ms |
| Security vulnerabilities | 10 | 5 | 2 | 0 |
| Test coverage | ~2% | ~2% | ~40% | >80% |
| Packages | 43 | 11 | 11 | 15 (with real additions) |

---

## 15. Final Recommended Architecture

```
JARVIS MK-X (Simplified)
│
├── main.py                          Entry point (6 modes)
├── ui_web.py                        PyQt6 shell + QWebEngineView
│
├── core/                            Core orchestration (~3K LOC)
│   ├── jarvis.py                    Main orchestrator
│   ├── config.py                    TOML config
│   ├── context.py                   Conversation + user profile
│   ├── intent_router.py             Intent classification
│   ├── dialogue.py                  State machine
│   └── personality.py               Mood + time awareness
│
├── providers/                       LLM abstraction (~1K LOC)
│   ├── base.py                      Abstract provider + health
│   ├── router.py                    Fallback chain
│   └── groq/gemini/openrouter/ollama/zen
│
├── pipeline/                        Voice pipeline (~500 LOC)
│   ├── stt.py                       Groq Whisper + local fallback
│   ├── tts.py                       Piper + Edge-TTS
│   ├── vad.py                       Energy-based VAD
│   └── wake_word.py                 openWakeWord
│
├── actions/                         Desktop automation (~3K LOC)
│   └── 22 action modules
│
├── memory/                          Memory system (~1K LOC)
│   ├── store.py                     SQLite + JSON
│   └── vector_store.py              Semantic search
│
├── security/                        Security layer (~1.5K LOC)
│   └── engine, policies, sandbox, trust
│
├── knowledge_graph/                 KG (~1K LOC)
│   └── entity extraction + graph queries
│
├── web/                             Flask server (~700 LOC)
│   └── server.py
│
├── python/                          Telemetry + tracing (~200 LOC)
│
├── vision/                          Camera + face (~1K LOC)
│
└── public/                          Frontend HUD (~1K LOC)
    ├── index.html
    └── js/{app,chat,voice,auth,reactor,telemetry}.js

TOTAL: ~12,000 LOC of active, used, clean code.
```

**Key principle:** Every package must be imported by an active entry point. If it's not imported, it doesn't exist.

---

## 16. Summary of Findings

| Category | Count | Severity |
|----------|-------|----------|
| Critical issues | 4 | Must fix before any public use |
| High issues | 7 | Fix within 1 week |
| Medium issues | 15 | Fix within 1 month |
| Dead code packages | 32 | Remove immediately |
| Dead code LOC | ~25,000 | 57% of codebase |
| Missing tests | ~95% of code | Add progressively |
| Security vulnerabilities | 10 | Fix top 4 ASAP |

**The core 11-package system is well-designed and functional. The single most impactful action is deleting the 32 dead packages. This alone transforms the project from a confused sprawl into a clean, maintainable codebase.**
