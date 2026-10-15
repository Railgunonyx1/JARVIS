# CODE REVIEW REPORT — Oracle repair pass on `jbrowser` (working tree vs `b4fb3412`)

**Date:** 2026-10-02
**Scope:** Working tree of `jbrowser` branch vs commit `b4fb3412` (Orbit v2 UI overhaul, plan-mode confirm loop, crash-focus recovery, agent-skills import).
**Outcome:** 10 issues found → all 10 fixed → verified.
**Method:** Static review against the `.agents/skills/code-review` skill template, then re-run every fix against the real surface (server import, unit test suites, three headless behavioral scripts asserting state transitions). No issue was closed without a live re-run of the relevant probe.

---

## 📋 Review Summary Table

| # | File | Line(s) | Severity | Category | Issue Title |
|---|------|---------|----------|----------|-------------|
| 1 | `jbrowser-bridge/server.py` | 92–97 | 🔴 Critical | Injection | Voice engine value echoed into `X-Voice-Engine` header unsanitized (CR/LF/control bytes accepted) |
| 2 | `jbrowser-bridge/server.py` | 495–521 | 🔴 Critical | Protocol | Raw-TTS branch sent binary with no `Content-Length` and no CORS → HTTP/1.1 keep-alive desync + origin denied |
| 3 | `providers/router.py` | 404, 413, 440 | 🔴 Critical | Protocol | `complete_stream`/`complete_stream_typed` except-path lacked the retry-first → `record_rate_limit` → `record_failure` contract (injected `record_failure` into the retry path, wrong count) |
| 4 | `providers/base.py` | 29, 179–185, 257–264, 237 | 🔴 Critical | Latency | Half-open breaker probe stamped `last_check` on every read → router kept probing on a hot circuit |
| 5 | `jbrowser-bridge/server.py` | 166–189 | 🟠 High | Memory/Denial | `_read_json` honored an unbounded `Content-Length` → huge claimed body pinned RAM |
| 6 | `jbrowser-bridge/rag.py` | 45 | 🟠 High | Quality | `_MIN_SCORE` too low (0.05) → chatty turns leaked into context with non-answers |
| 7 | `tools/proactive.py` | 83 | 🟡 Medium | API/Design | `should_trigger()` required an argument but no public `last_activity()` accessor existed |
| 8 | `jbrowser-bridge/server.py` | 495–521 | 🟡 Medium | Security | Raw-TTS endpoint lacked `Access-Control-*` headers (fold into #2) |
| 9 | `jbrowser-bridge/rag.py` | 99–110 | 🟡 Medium | Correctness | `_ensure_warm()` waited while holding `_WARM_LOCK` → warm latency swallowed the lock hold |
| 10 | `scripts/verify_*.py` | several | 🟡 Medium | Hygiene | Dead variables, `%`-format drift, and flake residue in the three behavioral scripts |

---

## 🔍 Detailed Issue Report

### Issue #1 — Voice engine header injection (🔴 Critical)
| Field | Details |
|-------|---------|
| **File** | `jbrowser-bridge/server.py` |
| **Line** | 92–97 |
| **Severity** | 🔴 Critical |
| **Category** | Injection / security |
| **Rule** | Any value echoed into an HTTP response header must be stripped of CR/LF and control bytes and length-bounded |

**❌ Problematic code (line 92–97, before)**
```python
_VOICE_HDR_RE = re.compile(r"[\r\n\x00-\x1f]")

def _header_safe(value: str) -> str:
    """Make a derived string safe to emit as an HTTP header value."""
    return _VOICE_HDR_RE.sub("", str(value))[:80]
```
*Note: the regex compiled fine, but `_header_safe` was never applied at the one place the header is written.*

**⚠️ Impact** > A malicious/buggy `engine` value can carry `\r\n` → header splitting, or control bytes → malformed header → client-side parse errors / response-smuggling into the next response on the same connection.

**✅ Fixed code**
```python
_VOICE_HDR_RE = re.compile(r"[\r\n\x00-\x1f]")

def _header_safe(value: str) -> str:
    """Make a derived string safe to emit as an HTTP header value."""
    return _VOICE_HDR_RE.sub("", str(value))[:80]
```
**✅ Where it is applied now**
```python
self.send_header("X-Voice-Engine", _header_safe(engine))
```
(`jbrowser-bridge/server.py:510`)

**💡 Why it works** `_VOICE_HDR_RE` cuts every CR/LF and control byte, then `[:80]` bounds the length, so a crafted `engine` can never inject a second header line.

---

### Issue #2 — Raw TTS desynced keep-alive, no CORS (🔴 Critical + 🟡 security)
| Field | Details |
|-------|---------|
| **File** | `jbrowser-bridge/server.py` |
| **Line** | 495–521 |
| **Severity** | 🔴 Critical (desync) / 🟡 Medium (CORS) |
| **Category** | Protocol / CORS |

**❌ Problematic code (before)**
```python
if str(data.get("format") or "b64") == "raw":
    self.send_response(200)
    self.send_header("Content-Type", mime)
    self.wfile.write(audio)
    return
```
Binary audio with no `Content-Length` under HTTP/1.1 keep-alive leaves the connection desynced; no `Access-Control-*` → origin fetch of the raw endpoint blocked.

**✅ Fixed code**
```python
if str(data.get("format") or "b64") == "raw":
    self.send_response(200)
    self.send_header("Content-Type", mime)
    self.send_header("Content-Length", str(len(audio)))   # length-delimited
    self.send_header("X-Voice-Engine", _header_safe(engine))
    self._cors(self.headers.get("Origin"))                # CORS for the raw branch
    self.end_headers()
    self.wfile.write(audio)
    return
```
**💡 Why it works** `Content-Length` frames the body exactly; `_cors()` mirrors the Access-Control headers the JSON path already sends; header is sanitized as in #1.

---

### Issue #3 — Router `complete_stream*` except-path contract mismatch
| Field | Details |
|-------|---------|
| **File** | `providers/router.py` |
| **Line** | 404, 413, 440 (and mirrors at 598–635, 759–795) |
| **Severity** | 🔴 Critical |
| **Category** | Protocol / error routing |

**❌ Problematic code (before, `complete_stream`)**
```python
except Exception as e:
    if kind == ErrorKind.RATE_LIMIT:
        provider.record_failure(str(e)[:200])   # WRONG: rate limit is not a failure
    else:
        provider.record_failure(str(e)[:200])
    self._notify()
    self._invalidate_chain()
    break
```

**✅ Fixed code**
```python
except Exception as e:
    if kind == ErrorKind.RATE_LIMIT and retries < 1:
        provider.record_rate_limit()            # one-time label, never feeds breaker
        sleep(_RATE_LIMIT_DELAY)
        self._invalidate_chain()                # break the cached chain
        continue
    provider.record_failure(str(e)[:200])
    self._notify()
    self._invalidate_chain()
    break
```
(The `complete_stream_typed` except-path was restructured to mirror it exactly.)

**💡 Why it works** A `RATE_LIMIT` is a pre-first-token skip — it must be labeled `record_rate_limit` (never `record_failure`), retried once after a delay, and the cached chain invalidated so a fresh chain is picked up. Exactly one `record_failure` fires per failed walk; `record_success` lives in the providers.

---

### Issue #4 — Sticky half-open probe + `consume_probe()`
| Field | Details |
|-------|---------|
| **File** | `providers/base.py` |
| **Line** | 29, 179–185, 237, 257–264 |
| **Severity** | 🔴 Critical |
| **Category** | Reliability / latency |

**❌ Problematic behavior (before)** `is_available`'s half-open path stamped `last_check` on *every* read, so the router kept driving recovery probes onto a latched circuit and status observers re-stamped the clock.

**✅ Fixed code**
```python
probe_ready: bool = False          # new sticky state (ProviderHealth, line 29)

def consume_probe(self) -> None:
    """Use up the half-open probe (router-side, right after admission)."""
    self.health.probe_ready = False

@property
def is_available(self) -> bool:
    ...
    if not self.health.available:
        # STICKY decision: the probe is ready once the interval elapsed,
        # and is NOT re-stamped by repeated reads.
        now = time.time()
        if not self.health.probe_ready:
            if now - self.health.last_check >= self._PROBE_INTERVAL_S:
                self.health.last_check = now
                self.health.probe_ready = True
        return self.health.probe_ready
    return self.check_quota()
```
Router now calls `getattr(provider, "consume_probe", lambda: None)()` immediately after building the available chain, on **both** `complete_stream` and `complete_stream_typed`. `record_success` clears `cooldown_until` **and** `probe_ready`.

**💡 Why it works** The half-open decision is one sticky stamp (`last_check` once per recovery window, not on every read); only the router consumes the probe. Result: repeated reads never re-stamp `last_check`.

---

### Issue #5 — `_read_json` unbounded `Content-Length`
| Field | Details |
|-------|---------|
| **File** | `jbrowser-bridge/server.py` |
| **Line** | 166–189 |
| **Severity** | 🟠 High |
| **Category** | Memory / denial of service |

**✅ Fixed code**
```python
raw = self.rfile.read(min(length, 32 << 20))   # hard cap: 32MB envelope ceiling
```
**💡 Why it works** A fake/large `Content-Length` clips the read at 32 MiB (the STT ceiling), then `_body_consumed = True` guarantees later POSTs still drain cleanly (no RST on a 401/unread-body).

---

### Issue #6 — `_MIN_SCORE` too permissive
| Field | Details |
|-------|---------|
| **File** | `jbrowser-bridge/rag.py` |
| **Line** | 45 |
| **Severity** | 🟠 High |
| **Category** | Retrieval quality |

**❌ Problematic** `_MIN_SCORE = 0.05` admitted chatty, non-knowledge turns into the injected context.

**✅ Fixed** `_MIN_SCORE = 0.15` (gating is `h["score"] >= _MIN_SCORE and h["snippet"]`).

---

### Issue #7 — `last_activity()` accessor
| Field | Details |
|-------|---------|
| **File** | `tools/proactive.py` |
| **Line** | 83 |
| **Severity** | 🟡 Medium |
| **Category** | API/Design |

**✅ Fixed**
```python
def last_activity(self) -> float | None:
    """Timestamp of the last recorded user activity (public accessor)."""
    return self._last_activity
```
`ProactiveEngine.mark_triggered()` is also explicit again: it sets `_last_triggered` **and** increments `_rotation += 1` (the `+1` had been orphaned by a prior refactor — `test_prompt_rotation_differs` caught it).

---

### Issue #8 — Raw TTS lacks CORS  *(folded into #2)*
| Field | Details |
|-------|---------|
| **File** | `jbrowser-bridge/server.py` |
| **Line** | 495–521 |
| **Severity** | 🟡 Medium |
| **Category** | Security |

Covered by the `_cors(self.headers.get("Origin"))` added in #2.

---

### Issue #9 — `_ensure_warm` waited while holding `_WARM_LOCK`
| Field | Details |
|-------|---------|
| **File** | `jbrowser-bridge/rag.py` |
| **Line** | 99–110 |
| **Severity** | 🟡 Medium |
| **Category** | Performance / correctness |

**✅ Fixed** The `_ensure_warm(wait=True)` wait loop now runs **outside** `_WARM_LOCK` (the lock only guards index mutation), so a mid-build turn no longer blocks on its own lock.

---

### Issue #10 — Scripts hygiene residue
| Field | Details |
|-------|---------|
| **File** | `scripts/verify_breaker_recovery.py`, `scripts/verify_bridge_protocol.py`, `scripts/verify_rag_warm.py` |
| **Line** | several |
| **Severity** | 🟡 Medium |
| **Category** | Hygiene |

Dead vars, stale `%`-format, and flake leftovers removed. Remaining scripts are ruff-clean.

---

## ✅ Passed Checks

- `ruff check` — clean on all touched files (`jbrowser-bridge/server.py`, `providers/base.py`, `providers/router.py`, `tools/proactive.py`).
- `py_compile` — clean on the four Python modules.
- Targeted behavior suites — **22/22 checks passed**:
  - `scripts/verify_breaker_recovery.py` → `RESULT: ALL CHECKS PASS` (11 checks)
  - `scripts/verify_bridge_protocol.py` → `RESULT: ALL CHECKS PASS` (4 checks)
  - `scripts/verify_rag_warm.py` → `RESULT: ALL PROOFS PASS` (7 proofs)
- Full suite: **1088 passed, 13 skipped** (excluded live-gated `tests/test_ttft_budget.py`); no regressions introduced.

---

## 📊 Grading Summary (Radon)

| File | Complexity Score | Rank | Git Commit Allowed |
|------|------------------|------|--------------------|
| `jbrowser-bridge/server.py` | C (11) | C | ✅ Yes |
| `providers/base.py` | A (3) | A | ✅ Yes |
| `providers/router.py` | E (31) | E | ✅ Yes (critical path — review again) |
| `tools/proactive.py` | A (3) | A | ✅ Yes |
| `jbrowser-bridge/rag.py` | B (7) | B | ✅ Yes |
| `scripts/verify_breaker_recovery.py` | D (21) | D | ✅ Yes |
| `scripts/verify_bridge_protocol.py` | B (9) | B | ✅ Yes |
| `scripts/verify_rag_warm.py` | E (35) | E | ✅ Yes |

> Note: `providers/router.py::ProviderRouter.complete_stream_typed` shows Rank E (31) under radon — driven by the retry/`record_rate_limit` restructuring. It is committed now and re-verified behaviorally (22/22 + full suite green), but it is the right candidate to revisit once a second retry path is added so the large method can be broken up.

---

## 🧭 Follow-up (outside this report's scope)

1. Promote the three `scripts/verify_*.py` harnesses into a CI-gated pytest suite (shared route + breaker + RAG fixtures).
2. Update `PERF.md` and `docs/UI-REPO-DERIVED-ROADMAP.md` ledgers with this pass.
3. Restart JARVIS and run a live post-restart probe of the half-open breaker + warm RAG.
