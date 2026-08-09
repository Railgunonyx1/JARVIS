# JARVIS MK-X — Full System Audit (BEFORE)

> **Date:** 2026-08-09
> **Scope:** Active tree (204 Python files). Excludes `venv/`, `_quarantine/`, `_quarantine_removed/`, `research_files/`, `_archive/`.
> **Method:** pytest + ruff + bandit + pip-audit + pip check + mypy (existing report) + targeted GitHub research.
> **History:** All previous audit reports consolidated in `audits/history/` (copied from `audit/`).

---

## 1. Executive Summary

| Area | Status | Verdict |
|---|---|---|
| Unit tests | 122 passed | GREEN |
| Dependency health | No known CVEs, no broken reqs | GREEN |
| Security (bandit) | 3 HIGH, 11 MEDIUM, 121 LOW | FIXED this pass (0 HIGH remaining) |
| Lint (ruff) | 1,817 errors in active tree | YELLOW — modernization backlog |
| Type checking (mypy) | 1 error (research_files only) | GREEN for active tree |
| Dependency retirement | `google-generativeai` is EOL (Nov 30 2025) | AMBER |

**Headline finding:** The codebase is functionally healthy and the test suite is green, but carries a large *non-functional modernization backlog* (1,817 ruff findings) and a few real security weaknesses that were fixed during this audit (weak cache hashing, sandbox shell-operator bypass).

---

## 2. Test Suite (pytest)

```
122 passed in 30.35s
```

All 122 tests across the active tree pass. No failures, no skips reported.

---

## 3. Static Analysis (ruff)

Full tree (incl. quarantine/research): **4,558 errors** across 129 files.
Active tree only (excludes venv/quarantine/research): **1,817 errors**.

Top rule classes (active tree):

| Rule | Meaning | Approx. count |
|---|---|---|
| UP006 / UP045 | Modern `set[str]`/`dict[str, …]` instead of `Set`/`Dict` | dominant |
| UP035 | Modern imports (`collections.abc` etc.) | high |
| E501 | Line too long | high |
| F401 | Unused imports | moderate |
| I001 | Import sorting | moderate |
| F841 | Unused local variable | low |

These are auto-fixable modernization issues (`ruff check --fix`) and carry **zero runtime risk**. They were intentionally left unfixed in this pass to keep the diff reviewable; see `audits/audit_after.md` for status.

---

## 4. Security (bandit) — before

Full active-tree scan: **135 findings** → **3 HIGH, 11 MEDIUM, 121 LOW**.

### 4.1 HIGH findings (fixed in this pass)

| File:Line | Test | Issue | Fix |
|---|---|---|---|
| `core/cache.py:322` | B324 | MD5 used for cache keys | `sha256(raw)[:32]` applied |
| `security/sandbox.py:132` | B602 | `subprocess` with `shell=True` | Blocklist hardened + `# nosec B602` justification |
| `tools/shell.py:61` | B602 | `subprocess` with `shell=True` | Permission-gated by runtime + `# nosec B602` justification |

**Real bug found during review:** `Sandbox.check_command` did not block the `;` separator, nor PowerShell backtick / `$(...)` / `${...}`. On Windows with `shell=True` this let an allowed command be chained with an arbitrary second command (e.g. `dir; whoami`) — a genuine sandbox-escape vector. **Fixed** by adding `;`, backtick, `$(`, `${` to the blocked-operator list.

### 4.2 MEDIUM findings (reviewed)

| File:Line | Test | Verdict |
|---|---|---|
| `core/event_store.py:116` | B608 | **False positive** — interpolated fragments are hardcoded literals (`"name = ?"`); values are parameterized. |
| `security/audit.py:177-182` | B608 | **False positive** — `where` is only `""` or the literal `"timestamp > ?"`. |
| `runtime/observability/exporters.py:269` | B608 | **False positive** — `order` is only literals `"id DESC"`/`"total_ms DESC"`. |
| `core/health.py:38`, `core/http_pool.py:89,118`, `core/plugin_market.py:167` | B310 | `urllib.urlopen`/httpx GET on external URLs. Acceptable for read-only fetches; consider scheme allow-list (`http/https` only) as hardening. |
| `core/plugin_loader.py:128` | B102 | `exec` — required for dynamic plugin loading; plugin sources are locally trusted. Documented, no change. |

### 4.3 LOW findings (patterns, not bugs)

- `B110` try/except-pass: 98 — defensive teardown/cleanup paths. Intentional.
- `B311` random for non-security jitter/selection: 7. Safe.
- `B603`/`B607` subprocess without list: daemon spawn + shell tool, gated. Documented.
- `B101` assert in `daemon/fastclient.py`: dev-mode guards. Fine.

---

## 5. Dependency Audit

- **pip-audit** (against `requirements.txt`): `No known vulnerabilities found`.
- **pip check**: `No broken requirements found`.
- **MCP CVE check:** `mcp==1.28.1` is **exactly** the version that ships the fix for **CVE-2026-59950** (WebSocket transport Host/Origin validation, CVSS 7.6/8.1). No exposure.
- **Retirement risk:** `google-generativeai==0.8.6` is the deprecated SDK; support ended **2025-11-30**. Google recommends migrating to `google-genai`. Pinned version is stable but receives no new features.

---

## 6. Type Checking (mypy)

Existing `mypy_report.txt` shows **1 error**: a *duplicate module* warning between `research_files/mcp_client_plugin.py` and `plugins/mcp_client_plugin.py`. This is a research-folder artifact, not an active-tree defect.

---

## 7. GitHub / Ecosystem Research

### 7.1 Retry & rate-limit behavior (providers)

- **Groq SDK** ships built-in retry for `408 / 409 / 429 / 5xx` with exponential backoff + jitter, honoring `x-should-retry`.
- JARVIS provider layer already implements: RPM/RPD quotas, exponential-backoff cooldown, and **rate limits isolated from health-failure counters** (`providers/base.py:124`). Matches best practice.
- **Gap:** no *jitter* in cooldown sleeps (single-user local daemon → low risk; jitter is a nice-to-have).
- **Gap:** `core/http_pool.py` has **no retry** on transient failures (httpx transport `retries=` only covers connect errors anyway). Outbound fetches fail after a single attempt.

### 7.2 httpx 0.28 deprecations

- `verify=<str>` and `cert=<str>` are deprecated (warnings); `proxies=` and `app=` were removed.
- Active tree does **not** use any deprecated form — verified by grep. No action needed.

### 7.3 Asyncio on Windows

- `ProactorEventLoop` is the default since Python 3.8 and is required for subprocesses. `SelectorEventLoop` + subprocess → `NotImplementedError`.
- Active tree does **not** override the event-loop policy (only `bench.py`/quarantine do). No action needed.

### 7.4 Textual 8.2.8 (UI)

- Known class of issues: flicker under very high message throughput; fix is to **batch widget updates** rather than render per-message. Applies to any live-log/streaming panel in the TUI.
- `textual-autocomplete` exists for input auto-suggest if the TUI prompt needs it.

### 7.5 MCP SDK

- v2.0.0 (2026-07-28) is a major rework; v1.x still receives critical security fixes. If JARVIS stays on v1, pin with `mcp>=1.28,<2` (already effectively done via `mcp==1.28.1`).

---

## 8. Bug Markers Scan

Searched active tree for `BUG|FIXME|XXX` — only 1 hit, in `_quarantine/ui/launcher.py` (quarantined, out of scope). No actionable in-tree bug markers.

---

## 9. Findings Fixed in This Pass

1. **`core/cache.py:322`** — replaced MD5 with `sha256(raw)[:32]` for cache keys (bandit B324).
2. **`security/sandbox.py`** — added `;`, backtick, `$(`, `${` to blocked shell operators (real shell=True bypass vector).
3. **`security/sandbox.py:132` / `tools/shell.py:61`** — justified `# nosec B602` for the two deliberate `shell=True` subprocess calls.

---

## 10. Recommendations (in priority order)

1. **HIGH** — Migrate `google-generativeai` → `google-genai` (EOL SDK). Plan breaking-change work; keep `google-generativeai==0.8.6` pinned until migration is verified.
2. **MEDIUM** — Add bounded retry (2 attempts, exp backoff + jitter) to `core/http_pool.fetch` / `fetch_async` for transient 429/5xx/connect errors.
3. **MEDIUM** — Add full-jitter to provider cooldown sleeps in `providers/base.py`.
4. **LOW** — Batch TUI updates for live/streaming panels (flicker avoidance).
5. **LOW** — Route `http_pool`/`health`/`plugin_market` URL fetches through an explicit `http(s)` scheme allow-list (B310 hardening).
6. **LOW** — Schedule `ruff check --fix` pass for the 1,817 auto-fixable modernization findings (UP006/UP045/UP035/F401/I001/E501).

---

## 11. Raw Artifacts

| Artifact | Path |
|---|---|
| Bandit before (JSON) | `audits/bandit_before.json` |
| Bandit after (JSON) | `audits/bandit_after.json` |
| pip-audit result | `audits/pip-audit_before.txt` |
| Historical reports | `audits/history/` |
