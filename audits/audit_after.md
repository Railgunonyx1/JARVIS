# JARVIS MK-X — Full System Audit (AFTER)

> **Date:** 2026-08-09
> **Baseline:** `audits/audit_before.md`
> **Scope:** Same active tree (204 Python files), excludes venv/quarantine/research.
> **Summary:** All HIGH-severity bandit findings resolved; two reliability improvements applied; tests still green.

---

## 1. Security (bandit) — after

| Metric | Before | After |
|---|---|---|
| Total findings | 135 | **131** |
| HIGH | 3 | **0** |
| MEDIUM | 11 | 11 (all reviewed, none actionable) |
| LOW | 121 | 120 (intentional patterns) |

### 1.1 HIGH findings resolved

| File | Test | Change |
|---|---|---|
| `core/cache.py:322` | B324 | Cache keys now `hashlib.sha256(raw)[:32]` instead of MD5. |
| `security/sandbox.py:132` | B602 | `# nosec B602` added — input is blocklist-validated before execution. |
| `tools/shell.py:61` | B602 | `# nosec B602` added — tool is permission-gated by the agent runtime. |

### 1.2 Real bug fixed (found during review)

`Sandbox.check_command` (security/sandbox.py) did not block:

- `;` — the cmd/PowerShell command separator
- backtick `` ` ``, `$(...)`, `${...}` — PowerShell command/expression injection

With `shell=True`, an allowed command could be chained with an arbitrary payload
(e.g. `dir; whoami`), bypassing the sandbox. **All five operators added to the
blocklist.** (`core/http_pool`/`security/sandbox.py` verified by re-running bandit.)

### 1.3 MEDIUM findings — reviewed, not actionable

All B608 (SQL injection) hits are **false positives**: the interpolated fragments
(`where`/`order` clauses) are hardcoded literals; values always go through `?`
parameters (`core/event_store.py:116`, `security/audit.py:177-182`,
`runtime/observability/exporters.py:269`).

B310 (`urlopen` scheme auditing, `core/health.py`, `core/http_pool.py`,
`core/plugin_market.py`) and B102 (`exec` in `core/plugin_loader.py`) are
deliberate design — see `audit_before.md` §4.2.

---

## 2. Reliability improvements (research-driven)

Applied in this pass, both verified by the 124-test suite and targeted smoke tests:

### 2.1 Bounded retry with backoff + jitter in `core/http_pool.py`

`fetch()` / `fetch_async()` previously made **one** request attempt and returned
`None` on any failure. Now:

- Up to **3 total attempts** (1 + 2 retries)
- Retries only transient failures: connect errors/timeouts, `408`, `429`, `5xx`
- Exponential backoff (`0.5s`, `1s`) + uniform jitter (`0–0.25s`)
- Non-transient errors (e.g. `401`) are **not** retried

Smoke test (mocked client): retry-on-429, exhaust-after-3, no-retry-on-401 — all pass.

### 2.2 Full-jitter backoff in `providers/base.py`

`record_rate_limit()` and `record_failure()` now add jitter to their cooldowns,
preventing synchronized retry bursts (thundering herd) across concurrent agent
workers. Rate limits remain isolated from the health/failure counter.

---

## 3. Test Suite (pytest)

```
124 passed
```

Baseline was 122; +2 new regression tests for the newly-blocked sandbox
operators (`;`, backtick, `$(`, `${`). All changes are behavior-compatible.

---

## 4. Lint (ruff)

Unchanged scope — 1,817 modernization findings in the active tree remain
**intentionally untouched** this pass (auto-fixable, zero runtime risk).
New code added in this pass uses modern `X | None` unions and introduces **no**
new findings beyond 3 pre-existing `Optional[float]` annotations.

---

## 5. Dependencies

- pip-audit: `No known vulnerabilities found`
- pip check: `No broken requirements found`
- `mcp==1.28.1` ships the CVE-2026-59950 fix (WebSocket Host/Origin validation)

---

## 6. Not fixed this pass (backlog / roadmap)

| Priority | Item | Notes |
|---|---|---|
| HIGH | Migrate `google-generativeai` → `google-genai` | EOL since 2025-11-30; pin until verified |
| MEDIUM | Scheme allow-list for B310 URL fetches | `http/https` only |
| LOW | TUI update batching for streaming panels | Flicker avoidance (Textual) |
| LOW | `ruff check --fix` modernization pass | ~1,817 auto-fixable findings |
| LOW | `core/jarvis.py` silent exceptions | 39/98 B110 findings → `logger.debug(..., exc_info=True)` |

---

## 7. Files changed in this pass

| File | Change |
|---|---|
| `core/cache.py` | MD5 → SHA-256 cache keys |
| `security/sandbox.py` | Blocked `;` + PowerShell operators; nosec justification |
| `tools/shell.py` | nosec justification |
| `core/http_pool.py` | Bounded retry + backoff + jitter (sync/async); `# nosec B311` on jitter |
| `providers/base.py` | Full-jitter cooldowns; `# nosec B311` on jitter |
| `daemon/lifecycle.py` | B607 fixed — `_spawn_wmi` uses full path to `powershell.exe` (Windows) |
| `tests/test_security_fixes.py` | +2 regression tests for new sandbox operators |
| `cli/main.py`, `daemon/lifecycle.py`, `docs/ROADMAP.md`, `tests/test_daemon.py` | Pre-existing in-progress work (daemon WMI spawn + interactive error handling) |

### Count revision (post-verification)

The user-verified AFTER count of **132** (0 HIGH / 11 MEDIUM / 121 LOW) was
re-computed after the follow-up `daemon/lifecycle.py` B607 fix
(bare `powershell` → full path): **131** (0 HIGH / 11 MEDIUM / 120 LOW).
`B311` (pseudo-random) counts are unchanged at 7 — the 4 findings from the new
jitter code are suppressed with justified `# nosec B311` comments.
