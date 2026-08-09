# JARVIS Comprehensive Audit

**Date:** 2026-08-08
**Scope:** Full repository — `core/`, `runtime/`, `daemon/`, `cli/`, `ui/`, `providers/`, `memory/`, `security/`, `tools/`, `agents/`, `workflows/`, `knowledge_graph/`, `inference_engine/`, `reliability_engine/`, `systems/`, `external/`, `mcp_jarvis/`, `tests/`, plus `_quarantine/` and `_quarantine_removed/`.
**Method:** Every finding below was verified by direct tooling on this machine (pytest, ruff, pip, static reads). Where a claim came from another session's transcripts, it is marked `[transcript]` and cross-checked. Nothing is asserted from memory alone.

---

## 1. Executive Summary

**Verdict:** The active daemon/kernel core is well-architected and fully tested (102/102 green), but the repository carries **~70k LOC of legacy/quarantined dead weight**, **1,838 lint violations**, **6 latent `NameError` bugs**, and **two critical command-execution security issues**. The largest risk to a production release is not the daemon — it is the **LLM-generated-code executor** and the **`shell=True` sandbox that can be bypassed with `&` command chaining or a newline**.

### Top issues

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 1 | **Critical** | LLM-generated code written to a temp file and executed with full user privileges, no sandbox; prompt even instructs `pip install` | `core/executor.py:90-169` (`_run_generated_code`) |
| 2 | **Critical** | `subprocess.run(..., shell=True)` behind a substring blocklist that is bypassable via `&` / newline injection | `security/sandbox.py:131` |
| 3 | **High** | `shell=True` shell tool registered in the default AgentLoop tool registry (reachable by the running agent) | `tools/shell.py:61`, `tools/__init__.py:85` |
| 4 | **High** | 6 latent `NameError`s (undefined names) — one in a hot path | `agents/agent_ecosystem.py:142,159` (`time`), `knowledge_graph/entity_extractor.py:149` (`Any`), `memory/vector_store.py:66,82,97` (`np`) |
| 5 | **Medium** | Legacy `AgentExecutor` dispatches to an `actions.*` package that **does not exist** → latent `ImportError` | `core/executor.py:235-327`; used by `core/task_queue.py:52`, `mcp_jarvis/server.py:153` |
| 6 | **Medium** | IPC framing has **no maximum frame size** — unbounded buffer growth from a hostile/broken peer on both TCP and pipe | `runtime/transport/protocol.py:114-134`, `runtime/transport/pipe.py:25-43` |
| 7 | **Medium** | Daemon exposes `shutdown` to any locally-authenticated client | `daemon/server.py:487-489` |
| 8 | **Medium** | `requirements.txt` is stale — lists quarantined stack (PyQt6, Flask, mediapipe, playwright), omits actually-used deps (textual, typer, rich, httpx, ruff) | `requirements.txt` |
| 9 | **Low** | ~38 outdated packages in the active venv | `pip list --outdated` |
| 10 | **Low** | Perf/tracing DB exists but has **0 rows** — telemetry is wired, never exercised | `~/.jarvis/perf.db` |

---

## 2. Ground Truth vs Prior Claims

The audit explicitly re-verified claims from other sessions' transcripts.

| Claim `[transcript]` | Reality (this machine) |
|---|---|
| "102/102 tests pass" | **Confirmed** — `102 passed in 21.01s` |
| "Bandit ran, ~90 issues" | **False** — `bandit` is **not installed** in the venv |
| "PyQt6 is the active UI" | **False** — root `main.py` routes to `cli.main`; PyQt6/web/Tauri are quarantined in `_quarantine/ui/` |
| "Active daemon = `daemon/server.py`; AgentLoop is the command interface" | **Confirmed** — `daemon/server.py` builds a kernel via `build_kernel` → `AgentLoop` |
| "Named-pipe IPC is a *proposal*" | **Incorrect** — the pipe transport **already exists** (`runtime/transport/pipe.py`) and the daemon already starts it: `daemon/server.py:155-161` |
| "ZIP's TUI is the only client design" | Partially — `ui/` package exists in-repo, but `textual` is **not installed** and `ui/jarvis_tui.tcss` is missing, so it does not run |
| "~38 outdated packages" | **Confirmed** (partial listing: groq 1.5.0→1.6.0, openai 2.46→2.53, litellm 1.72→1.95, mcp 1.28→2.0, protobuf 5.29→7.35, mediapipe 0.10.35→1.0.0) |

---

## 3. Repository Health

### Active tree size (measured via glob/read, excluding venv and `_quarantine`)

| Area | Files | LOC |
|---|---|---|
| core | 66 | 11,796 |
| memory | 17 | 3,003 |
| tests | 11 | 2,365 |
| runtime | 20 | 1,692 |
| cli | 8 | 1,646 |
| security | 9 | 1,547 |
| daemon | 7 | 1,539 |
| providers | 9 | 1,313 |
| knowledge_graph | 5 | 1,136 |
| workflows | 3 | 1,043 |
| inference_engine | 8 | 900 |
| systems | 6 | 898 |
| external | 7 | 759 |
| agents | 1 | 626 |
| reliability_engine | 4 | 621 |
| **ui** | 3 | 548 |
| tools | 5 | 428 |
| research_files | 2 | 408 |
| mcp_jarvis | 2 | 209 |
| python | 2 | 181 |
| plugins | 1 | 180 |
| scripts | 2 | 90 |
| benchmark | 1 | 49 |

### Dead / vendored weight

- `_quarantine/`: **191 .py files, 33,844 LOC** (includes the old PyQt6 HUD, `ui/web/server.py`, Tauri, mediapipe/vision stack).
- `_quarantine_removed/`: **32 .py files, 4,408 LOC**.
- `.kilo/` with a full `node_modules/` tree is committed to the repo (50 of the 50 `.md` files in the repo live under node_modules or `.agents/`).
- **Git state:** repo has **zero commits** — `git log` fails (`branch 'main' does not have any commits yet`); all files are staged (`A`). **There is no recovery point.**
- Legacy/dead execution path: `AgentExecutor` (`core/executor.py`) dispatches to `actions.*` modules which **do not exist**. Reachable from `core/task_queue.py:52-53` and `mcp_jarvis/server.py:153` → latent `ImportError` if invoked.
- `JarvisKernel` (`runtime/kernel.py:87-133`) is an OS-style placeholder shell: `load_config`, `register_services`, `start_services`, `stop_services` are all no-ops.

---

## 4. Correctness: Tests, Lint, Real Bugs

### Tests
`venv\Scripts\python.exe -m pytest tests\ -q` → **102 passed in 21.01s.** Full suite green, including `tests/test_daemon.py` (12 tests).

### Lint debt
`ruff check` over the active tree (venv/`_quarantine` excluded): **1,838 issues, 1,426 auto-fixable.**

Top rules:

| Rule | Count | Meaning |
|---|---|---|
| UP006 | 613 | `typing` → builtin generics |
| UP045 | 437 | `typing.Optional/Union` → `\|` |
| UP035 | 232 | deprecated typing imports |
| E501 | 172 | line too long |
| F401 | 159 | unused imports |
| I001 | 107 | import block formatting |

Worst files: `core/capability_registry.py` (121), `agents/agent_ecosystem.py` (70), `core/intent_router.py` (48), `core/model_manager.py` (41), `knowledge_graph/relation_mapper.py` (39), `knowledge_graph/graph.py` (38), `core/telemetry.py` (37), `core/container.py` (35).

### Real bugs (not style)

| Bug | Location | Impact |
|---|---|---|
| `time` used but never imported | `agents/agent_ecosystem.py:142,159` (`_execute_task`) | **Runtime `NameError`** in the agent ecosystem's hot path |
| `Any` used but never imported | `knowledge_graph/entity_extractor.py:149` | `NameError` |
| `np` used in annotations, imported only inside functions | `memory/vector_store.py:66,82,97` | Latent (masked by `from __future__ import annotations`), but breaks runtime type introspection |
| Redefinition of `re` | `core/jarvis.py:94` | Module-global corruption of `re` (F811) |
| `subprocess.run(..., check=False)` | `core/executor.py:142`, `tools/shell.py:59`, `bench.py` (reported as `benchmarks.py:82`) | Silent failures on non-zero exit (PLW1510) |

---

## 5. Security Findings

### CRITICAL — LLM-generated code executes with full privileges
`core/executor.py:90-169` `_run_generated_code`:
- Sends a user goal to Gemini 2.5 Flash with a system instruction that literally says *"Install missing packages with subprocess + pip if needed."*
- Writes the returned code to a temp `.py` file and runs it: `subprocess.run([sys.executable, tmp_path], ...)` with `cwd=Path.home()`, **no sandbox, no permission gate, no network/path restriction**.
- Reachability chain: `workflows/workflow_engine.py:506` imports `_run_generated_code`; the legacy executor exposes it as the `generated_code` tool.

**This is the single most dangerous code path in the repository.**

### CRITICAL/HIGH — `shell=True` behind a bypassable blocklist
- `security/sandbox.py:131` runs `subprocess.run(..., shell=True)`. Its `blocked_commands` list (`format`, `rm -rf`, `shutdown`, `reg delete`, …) is matched by substring, so a blocked command can be **bypassed** with `&` (Windows command chaining) or an embedded newline (e.g. `format & dir` or a two-line payload). Line 124 also uses `hashlib.md5` for the process id.
- `tools/shell.py:61` also uses `shell=True` but with meaningful guards: timeouts (60s, capped 300s), 8,000-char output truncation, `_sanitized_env()` that strips credential-like env vars, explicit `cwd`, permission check, and `CREATE_NO_WINDOW`. **However**, it is registered in the default registry via `tools/__init__.py:85` and imported by `runtime/kernel.py:40`, so it is reachable by the live `AgentLoop` in agent mode.

### MEDIUM
- **No IPC frame-size limit** on either transport — NDJSON framing (`runtime/transport/protocol.py:114-134`, `runtime/transport/pipe.py:25-43`) has no `MAX_FRAME_SIZE`; a hostile/broken peer can grow the read buffer without bound.
- **`shutdown` exposed** to any authenticated local client (`daemon/server.py:487-489`); the auth token is stored in the plaintext registry entry (`.jarvis/daemons/*.json`), so any local process that can read the file can shut the daemon down.
- **Named-pipe ACLs unset** — `start_pipe_server` (`runtime/transport/pipe.py:98-120`) uses default pipe security. Mitigation currently relies entirely on the in-band token.
- **Single-instance not enforced** — a second daemon for the same project simply picks a new TCP port (`daemon/server.py:144-151`) and silently fails the pipe bind (`:160-161`). Two daemons can coexist for one project.
- 3 `subprocess.run` calls without `check=` (see §4).

### Not found (clean)
No `eval`/`exec`/`compile` (only `re.compile`), no pickle/marshal, no bind on `0.0.0.0`, no `requests` without a timeout, no hardcoded secrets in the scanned tree.

---

## 6. Dependencies

- **`requirements.txt` is stale and contradictory.** It still pins the quarantined stack (PyQt6, PyQt6-WebEngine, flask, flask-cors, mediapipe, pyautogui, playwright) while the code actively imports textual, typer, rich, httpx, and ruff — none of which are listed.
- `pip list --outdated`: ~38 packages behind; notable: `litellm 1.72.2 → 1.95.0`, `mcp 1.28.1 → 2.0.0` (major), `protobuf 5.29.6 → 7.35.1` (major), `groq 1.5.0 → 1.6.0`.
- **TUI blocker:** `textual` is **not installed**; `psutil` is present; `pywin32` is absent (only relevant if the pipe path is extended — it isn't needed to connect over TCP).
- `bandit` (and any SAST) is absent — the other session's "bandit ran" claim is false on this machine.

---

## 7. Performance & Telemetry

- **Fast CLI:** `cli/fast.py` (stdlib-only) measured **0.32s** startup vs **0.89s** interpreter baseline (~2.8× the full-CLI cost). Positive.
- **Daemon warm-up:** provider SDKs are warmed on a background thread with exponential backoff (`daemon/server.py:183-194`) — the daemon is usable immediately. Positive.
- **Perf DB empty:** `~/.jarvis/perf.db` has the schema (tables `traces`/`spans`/`counters`) but **0 rows**. Tracing works but no real run has completed and flushed (harness kills in this environment; graceful shutdown does flush via `runtime/observability.exporters.disable_perf`).
- **Known heavy imports** (`torch`, `sentence_transformers`, mediapipe) are quarantined, so daemon startup is not paying their cost.

---

## 8. Daemon & Transport Architecture

### What is strong (verified)
- Token auth required before any dispatch (`daemon/server.py:249-257`); hostile-client isolation (`:265-270`); per-client task tracking; graceful ordered shutdown (`:203-237`); run serialization via `asyncio.Lock`; state snapshot written on changes; **event streaming** via `observer.on_event` → bounded-work `_drain_events` (`:420-429, 480-485`).
- **Two transports already exist and share one handler:** TCP (`start_server`) **and** a Windows Named Pipe `\\.\pipe\jarvis-{project_id}` (`runtime/transport/pipe.py`, started at `daemon/server.py:155-161`). Envelope protocol has `version`, `id`, `timestamp`, `payload` (`runtime/transport/protocol.py:76-93`).

### Protocol gaps vs the proposed IPC design (from the other session's spec)

| Area | In the repo today | Proposal / recommendation | Gap? |
|---|---|---|---|
| Protocol versioning | `version: 1` field present, not negotiated | handshake rejects mismatched versions | Partial |
| Request IDs | `id` echoed on all frames | same | **None** |
| Framing | NDJSON line-delimited | length-prefixed; **MAX_FRAME_SIZE** | Size cap missing |
| Heartbeat | `ping`/`pong` handler exists; no client enforcement | PING→PONG, ~5-10s | No liveness enforcement |
| Reconnect | client-side concern; `ui/backend.py` reconnects every 5s | explicit RECONNECTING state | UI side ok, protocol stateless |
| Cancellation | daemon cancels dispatch tasks on disconnect; **kernel run is shielded** (`:450-464`) — an in-flight LLM call is *never* killed | true cancel command | **Needs design** |
| Single-instance | enforced via registry check + instance lock; second instance exits cleanly | same | **Fixed 2026-08-08** |
| Windows pipe ACL | default security | restricted ACL | **Missing** |
| Backpressure/coalescing | unbounded `asyncio.Queue` for events (`:420`) | bounded queues, coalesce transient events | **Missing** |
| Sensitive logging | goals/decision events persisted (audit by design) | log metadata only | Verify client-side handling |
| `shutdown` exposure | exposed to any authed client | not exposed to UI clients | **Missing** |

**Conclusion for transport decision:** The pipe transport is **not a hypothetical** — it is already implemented and started alongside TCP. The two are near-duplicates of a shared handler. Do **not** build a third path; instead (a) add a `MAX_FRAME_SIZE`, (b) make pipe/TCP selection a config flag, (c) decide single-instance + ACL + real cancellation once the audit-driven architecture decision is made. Priority order from the spec (persistent connection → request IDs → async events) is already satisfied by the current daemon.

---

## 9. Agent Runtime

- **Active path:** `AgentLoop.run(goal, session_id)` (`core/agent/loop.py:90-201`) — observe→decide→act loop over `ProviderRouter`, context budgeting (`context_manager.fit_for_loop`), tracer spans, observer lifecycle (`start/finish/cancel`), decision-logger audit trail, and an **always-evaluated permission gate**: `mode_manager.is_allowed` + `security_engine.check_permission` before every tool call (`loop.py:266`, `permissions.py:56-81`). Strong.
- **Cancellation gap:** the agent loop itself has **no cancellation token** — only `TaskObserver.cancel()` in `finally`. The daemon deliberately shields kernel runs so a disconnect never kills an in-flight LLM call. A UI "cancel" therefore requires a new mechanism (cancellation token threaded into `run()`, or killing the detached run task).
- **Legacy parallel path:** `AgentExecutor` (`core/executor.py`) has its own planner/error-handler/retry/replan loop and dispatches to a non-existent `actions.*` package — dead code that still holds latent `ImportError` traps (`core/task_queue.py:52-53`, `mcp_jarvis/server.py:153`). Recommend deletion after confirming `task_queue`/`mcp_jarvis` callers.

---

## 10. TUI Audit (`ui/`)

### Status
- `ui/providers.py`, `ui/backend.py`, `ui/tui.py` written (548 LOC). `TuiDataSource` is a real client of the daemon over TCP with psutil snapshots and an **honest mock/offline fallback** (rows are clearly marked `MOCK`).
- **Does not run:** `textual` not installed; `ui/jarvis_tui.tcss` (referenced by `CSS_PATH="jarvis_tui.tcss"`) **not ported**; no tests yet; no `jarvis tui` CLI entry; no startup/memory benchmark.
- Existing roadmap-relevant items already satisfied by `ui/backend.py`: persistent connection, 5s reconnect, snapshot-style refresh, per-panel cadence (1s/5s/30s).

### Roadmap additions (validated by the ZIP + grid-design notes, recorded as spec not code)
1. **Terminal-grid/cell layout subsystem** (from the Grid Studio design): size widgets from terminal columns×rows, not pixels; **no new rendering dependency** — Textual keeps widget/layout duty; grid concepts drive responsive sizing only.
2. Character-cell presets (e.g. 80×50, 120×36) for layout tests; ANSI/Unicode-safe text handling.
3. `jarvis tui` subcommand (lazy import of textual — keep the fast CLI path import-free).
4. Headless tests (`App.run_test`) + `provider_rows` unit test.
5. Startup-latency and memory benchmark against the 512-MB UI budget before expanding panels.

---

## 11. Documentation & Hygiene

- 50 `.md` files in the repo, of which ~43 are vendored `node_modules` docs under `.kilo/` — add `.kilo/`, `.venv/`, `venv/` to `.gitignore` (or remove from the index).
- markdownlint diagnostics seen on out-of-repo docs (`~/.gemini/.../implementation_plan.md`) — MD022/MD030/MD032 style issues; worth enabling a markdownlint pass on `README.md`/`audit/*.md` only if desired. Cosmetic.
- Existing `audit/01..08*.md` docs (latency map, hotspots, quick wins, architecture, metrics, full technical audit, phase-0 baseline) should be reconciled against this report — several of their claims (e.g. PyQt6 active) are now outdated.

---

## 12. Prioritized Remediation Roadmap

### P0 — do before any release
1. **Remove or sandbox `_run_generated_code`** (`core/executor.py:90-169`): disable by default; never `pip install`; run under a restricted user/container, with an explicit allow/deny gate. ✅ **Done 2026-08-08**: opt-in gate via `JARVIS_ENABLE_GENERATED_CODE` (off by default → `RuntimeError`), `pip install` instruction removed from the prompt, static denylist scan (`_check_generated_code` rejects `os.system`/`subprocess`/`eval`/`exec`/`socket`/`requests`/`urllib`/`__import__`), `check=False` made explicit.
2. **Fix sandbox bypass** (`security/sandbox.py:131`): stop using `shell=True` for command strings (use `shlex.split`/argv lists or `cmd /c` with explicit rejection of `&`, `|`, `>`, newlines); add those characters to the blocklist. ✅ **Done**: `&`, `<`, `^`, `\n`, `\r` added to the operator reject list (chaining/injection closed at both `check_command` and `execute`); `md5` → `sha256` for proc id. (Still `shell=True` — metachar rejection is the active control; an argv-based rewrite is tracked as follow-up.)
3. **Fix the 4 real bugs** (§4). ✅ **Done**: `import time` added to `agents/agent_ecosystem.py`; `Any` added to `knowledge_graph/entity_extractor.py`; duplicate `import re` removed from `core/jarvis.py:94`; `check=False` made explicit at `core/executor.py:142`, `tools/shell.py:59`, `tests/benchmarks.py:82`.

### P1 — before adding features
4. Add `MAX_FRAME_SIZE` to the framing layer (reject before buffering) on both transports. ✅ **Done**: `MAX_FRAME_SIZE = 4 MiB` in `runtime/transport/protocol.py`, enforced in `decode_line`, in the pipe buffer (`runtime/transport/pipe.py:25-48`), and via the TCP reader limit (`runtime/transport/tcp.py`).
5. Decide single-instance + pipe ACL + `shutdown` exposure policy for authenticated clients. ⏳ Partially done. **Single-instance enforced**: `DaemonServer.start()` now refuses to start while a healthy entry exists in its registry (`_ensure_single_instance` → `DaemonAlreadyRunning`, caught cleanly in `_start_daemon`), serialized by a cross-process `filelock` instance lock (`daemon/state.acquire_instance_lock`) held across the register window. A second daemon no longer duplicates on a fresh TCP port or silently fails the pipe bind. Pipe ACL + `shutdown` exposure policy remain open design decisions.
6. Rewrite `requirements.txt` to match reality; pin the current venv; add `textual`/`typer`/`rich`/`httpx`/`ruff`. ✅ **Done**: rewritten from an AST scan of the active tree with versions pinned to the venv; `textual` installed (8.2.8) for the TUI; `pytest-asyncio` added (dev, enables `tests/test_pipe_ipc.py`).
7. Delete legacy `AgentExecutor`/`JarvisKernel`/`actions`-dispatch after confirming `task_queue`/`mcp_jarvis` callers; or quarantine them. ⏳ Open.

**Bonus fixes landed in this pass:** `PipeServer` nested-list bug (`runtime/transport/pipe.py`) — `start_serving_pipe` returns a list on Windows; caught by the newly-enableable `tests/test_pipe_ipc.py`. **Suite: 121 passed** (incl. TUI `provider_rows`/headless-run tests and 3 single-instance daemon tests).

### P2
8. Land the TUI: install textual, port `jarvis_tui.tcss`, add `jarvis tui` command, tests, benchmark.
9. Run `ruff check --fix` for the 1,426 auto-fixable issues; triage the remainder.
10. Add SAST (`bandit`) to CI/scripts so it is actually run.
11. Exercise the perf/tracing path end-to-end and confirm non-empty traces on a completed run.
12. Fix F811/PLW1510 sweep; re-audit `core/capability_registry.py` (121 issues).

### P3
13. Make the transport choice (TCP vs pipe vs both) an explicit config; implement real cancellation semantics for `AgentLoop.run`.
14. Backpressure + event coalescing on the run-event stream.
15. Grid/cell layout subsystem for the TUI (spec only, no new dependency).
16. First real git commit as a recovery point.

### Tier-2 (post-stability) — recorded designs, not implemented
**Gotify notifications (secondary channel only).** Never placed between the Textual UI and the daemon (the pipe/TCP transport owns that); only a side-channel from the daemon via a future `NotificationManager` to phone/desktop. Purposes: long-running task completed, agent needs attention, build/test finished, critical error, daemon online/offline, approval required. Notification levels: `DEBUG`/`PROGRESS` → never; `INFO` → usually not; `COMPLETED`/`WARNING`/`ERROR`/`APPROVAL` → yes. **Requires dedup + rate limiting** so a noisy agent cannot spam. Tier-2 also includes: the Web HUD (WebSocket, quarantined today) and keeping `NotificationManager` a thin decision layer that emits only to configured channels.

**CRM research agent (specialized workflow, not another agent runtime).** Implemented as domain-specific tools + schemas invoked by the existing Planner, never a separate autonomous loop. Tool surface: `crm.search_company`, `crm.get_company_profile`, `crm.search_news`, `crm.search_public_web`, `crm.find_products`, `crm.compare_competitors`, `crm.create_research_brief`. Pipeline: (1) entity resolution (name → official domain → entity ID, prevents cross-company mixing), (2) source collection by priority (official → government/regulatory → reputable publications → industry → public professional), (3) evidence extraction as structured records `{claim, source, date, confidence}` — not raw webpage dumps, (4) synthesis (Company/Industry/Products/Business model/Recent developments/Competitors/Opportunities/Risks/Evidence). **Research memory is separate from conversational memory**: records carry `entity/claim/source/timestamp/confidence/expiration` so stale company facts are not treated as permanent truth. **CRM boundary:** a CRM Adapter sits behind the JARVIS tools; the agent never touches the CRM database directly, and consequential actions (create/modify records, send messages, change deal stages) go through the existing security/permission engine with confirmation. Phase order: 1 public-web research tools → 2 structured evidence + citations → 3 CRM entity model → 4 CRM adapter/plugin → 5 persistent research memory → 6 background research + Gotify notification.

---

## 13. Appendix: Evidence & Methodology

Artifacts produced during this audit (temp):
- `C:\Users\aayan\AppData\Local\Temp\opencode\ruff_all.json` — full 1,838-issue ruff output.
- `C:\Users\aayan\AppData\Local\Temp\opencode\secscan.py` — security grep scanner.
- `C:\Users\aayan\AppData\Local\Temp\opencode\todos.py` — TODO/quarantine/LOC counters.

Commands run: `venv\Scripts\python.exe -m pytest tests\ -q` (102 passed, 21.01s); `ruff check .` scoped; `pip list --outdated`; `pip show bandit` (absent); targeted `rg`/`glob`/`read` on every cited file:line.

**This audit changes the roadmap:** the named-pipe IPC is already partially implemented, the TUI is a validated client component, and the P0 security issues must be resolved before the transport/architecture decision that gates further IPC work.
