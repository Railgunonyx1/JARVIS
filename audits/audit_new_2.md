# JARVIS MK-X — Architecture Audit (NEW 2)

> **Date:** 2026-08-11
> **Scope:** Active tree (excludes `venv/`, `_quarantine/`, `_quarantine_removed/`, `research_files/`, `_archive/`). Includes the new `web/` browser dashboard.
> **Method:** Source walk of the WS transport, daemon run/dedupe path, browser client, and dashboard; cross-checked against the running test suite (174 passed).
> **Companions:** `audits/audit_before.md`, `audits/audit_after.md`, `audits/audit_new_1.md`. This report is the *second* structural audit; it supersedes NEW 1's snapshot and focuses on the delta since then (WebSocket browser transport + dashboard), plus a re-verification of the error/pipeline architecture.

---

## 1. Executive Summary

| Area | Verdict | Notes |
|---|---|---|
| Error architecture | GOOD — still result-object driven | Exception surface unchanged (4 daemon-boundary classes); browser client adds its own recoverable error paths, no new exceptions leak into the UI |
| Resilience stack | STRONG — now spans Python + browser | TCP/WS transports share the daemon's shield/dedup; browser adds bounded-backoff reconnect with same-id run resubmission |
| WS/browser transport | **NEW, load-bearing** | `runtime/transport/ws.py` + `web/src/daemon/client.ts` implement the third client type (browser) on the same envelope protocol |
| Bootstrap auth | GOOD | Single-use, short-TTL credential issued over authenticated TCP, embedded in the dashboard URL; never the permanent registry token |
| Pipelines | 10 identified; 8 load-bearing | The dashboard pipeline (daemon → WS → React) is now real; named-pipe, knowledge_graph, resilience engine remain unwired |
| Tests | 174 passed (was 154) | +11 `test_daemon_ws.py`, +4 `test_client_reconnect.py`, +2 `test_security_fixes.py`, +1 `test_pipe_ipc.py` |
| Build hygiene | 3 defects found in environment | npm registry served a tampered `react` (placeholder shim); mitigated via `npm pack` + package.json restore — see §5.4 |

---

## 2. Error Architecture

### 2.1 Python exception surface (unchanged, re-verified)

Still exactly **4 custom exception classes**, all at the daemon transport boundary — no hierarchy, failures-as-data everywhere else:

| Exception | File:Line | Base | Meaning |
|---|---|---|---|
| `DaemonError` | `daemon/client.py:40` | `Exception` | Daemon replied with an error frame |
| `DaemonDisconnected` | `daemon/client.py:44` | `Exception` | Connection dropped or never authenticated |
| `FastError` | `daemon/fastclient.py:29` | `Exception` | Sync fast-path connection/protocol failure |
| `DaemonAlreadyRunning` | `daemon/server.py:70` | `RuntimeError` | A healthy daemon already owns the project |

### 2.2 Browser error architecture (NEW)

`web/src/daemon/client.ts` introduces a *recoverable-failure* model on the JS side, deliberately avoiding new exception types:

| Failure mode | Handling | Location |
|---|---|---|
| Request timeout (30s) | `PendingRequest` rejected; entry removed from map | `client.ts` `request()` |
| Send on closed socket | `request()` rejects `"not connected"`; `run()` is deferred to reconnect | `client.ts` `issueRun()` |
| Connection loss mid-run | Status → `reconnecting`; run is NOT failed — it is **resubmitted with the same id** on reconnect; daemon `_run_ids` dedupe attaches to the running task | `client.ts` `handleClose()` / `daemon/server.py:554-560` |
| Reconnect attempts exhausted (5, 250ms→5s jittered backoff) | Status → `error`; in-flight runs rejected with a descriptive error | `client.ts` `scheduleReconnect()` / `failInFlight()` |
| Malformed frame | Ignored; never raises into the dispatch loop | `client.ts` `handleMessage()` |
| Cancellation | `MSG_CANCEL` with the current run id; server sends a terminal `stream.result {cancelled:true}` so the client's run loop returns | `client.ts` `cancel()` / `server.py:602-607` |

The UI layer (`store/connection.ts`, `store/task.ts`) is a pure reducer over connection status + streamed events; no UI code can throw from protocol handling.

### 2.3 Error-path hardening this cycle

- **`tools/shell.py` audit crash fix** — the audit-hash slice no longer assumes a non-None execution result (`tools/shell.py:60`); regression covered in `test_executor_security.py`.
- **WS handler isolation** — an exception escaping the WS connection handler logs and drops just that connection; the server never dies (`runtime/transport/ws.py:122-137`).
- **Dead-peer hygiene** — `WebSocketTransport.send` maps any websockets failure to `ConnectionError`, which `_safe_send` swallows (`ws.py:55-65`); `_ws_clients` discards closed peers before any broadcast (`server.py:457-458`).
- **Duplicate-run protection** — `_handle_run` claims the request id atomically under `_run_claim`; a resent id attaches to the in-flight task instead of double-executing (`server.py:554-560`).
- **Silent-wait fix preserved** — a client that lands while the kernel lock is held gets an explicit `run.queued` frame, never an empty wait (`server.py:580-588`).

---

## 3. Pipelines

### 3.1 NEW — Dashboard pipeline (load-bearing)

```
daemon status --web  (CLI, authenticated TCP)
   └─ issue_bootstrap → {bootstrap, expires_in, ws_port, project_id}
   └─ prints http://localhost:5173/?bootstrap=<cred>&ws_port=<port>
browser loads web/ (Vite, port 5173)
   └─ App reads ws_port → ws://127.0.0.1:<ws_port>/ + bootstrap
   └─ DaemonClient.open → auth {bootstrap} → ok
   └─ run(goal):
        MSG_RUN {goal} (id = runId)
        daemon _handle_run → _run_ids[id] → _run_locked → kernel AgentLoop
        observer.on_event → queue → MSG_EVENT stream → client onEvent → store.handleEvent
        terminal MSG_RUN_RESULT {result} → store.finishRun
   └─ heartbeat: MSG_PING every 15s; stale-frame watchdog closes at 40s silence
```

E2E verified this cycle: bootstrap auth → `ok` → 8 streamed events (`task.started`, `step.started`, `permission.observed`, `step.completed`, `task.finished`) → `stream.result success=True`.

### 3.2 NEW — WS connection-state broadcast

`_broadcast_conn_state(event, peer, exclude)` (`server.py:446-460`) pushes `MSG_CONN_STATE {event, peer, clients}` with id `__broadcast__` to **WS subscribers only** (TCP/pipe clients correlate every frame to a request id and would misread an unsolicited frame). The connecting peer is excluded (it already got its `ok`). The browser bar renders live peer count from these frames.

### 3.3 Re-verified pipelines (unchanged from NEW 1)

Agent execution (§3.1), provider (§3.2), memory (§3.3), daemon IPC over TCP (§3.4), observability (§3.5), security (§3.6), tools (§3.7), UI/Textual (§3.8), startup (§3.9) — all unchanged and still load-bearing. The **WS transport is now a live member of the daemon IPC family**; previously it was server-bound but clientless.

### 3.4 Dead / incomplete edges (unchanged from NEW 1)

| Pipeline edge | Status |
|---|---|
| Named-pipe transport (`runtime/transport/pipe.py`) | Built, server binds — **no client connects** |
| `knowledge_graph/` package | Legacy-only; active memory uses `memory/graph.py` |
| `reliability_engine/` | Not wired into the active loop |
| `inference_engine/`, `systems/`, `workflows/`, `skills/`, `plugins/`, `mcp_jarvis/` | Legacy / standalone |
| `context.compacted` event | No emitter exists |
| Textual TUI task stream | `ui/providers.py` uses mock tasks only |

---

## 4. Features Inventory

### 4.1 NEW — Web dashboard (`web/`)

| Layer | Tech | Files |
|---|---|---|
| Build | Vite 6.4, TypeScript 5.7, `tsc -b` gate | `vite.config.ts`, `tsconfig.{app,node}.json` |
| Styling | Tailwind v4 (`@import "tailwindcss"`) | `src/index.css` |
| UI framework | React 19, strict mode | `src/main.tsx` |
| State | Zustand 5 — `connection` + `task` stores | `src/store/*.ts` |
| Protocol | `protocol.ts` mirrors `protocol.py` (envelope constants, id generator) | `src/daemon/protocol.ts` |
| Client | `DaemonClient` — auth, correlation, run streaming, cancel, heartbeat, stale watchdog, backoff reconnect w/ same-id resubmit | `src/daemon/client.ts` (315 lines) |
| Panels | Connection bar (status dot, peer count, URL/bootstrap), chat, agent timeline (steps, errors, result) | `src/components/*.tsx` |

Scripts: `dev` (port 5173 strict), `build`, `typecheck`, `preview`. Deps: react/react-dom ^19, zustand ^5, vite ^6, tailwindcss ^4, @vitejs/plugin-react.

### 4.2 NEW — Daemon capabilities added this cycle

- Bootstrap credentials: `MSG_BOOTSTRAP` (`server.py:424-438`), TTL `BOOTSTRAP_TTL`, single-use (`_authorize` pops), `_prune_bootstrap_tokens` sweep, `status --web` (`server.py:826-850`).
- `status --web` URL now includes `&ws_port=<port>` — previously bootstrap-only, which left the browser with no endpoint to connect to.
- Run-id dedupe / resume: `_run_ids` map keyed by request id, shield + detached-run semantics preserved on client vanish.

### 4.3 Rest of the inventory (re-verified)

CLI/REPL (slash-commands, fast path), 4-tool registry (`filesystem.write|read|list`, `shell.execute`), daemon TCP + WS transports + token/bootstrap auth + state snapshots, 5 providers with fallback/cooldown, memory stack (9 types, 3 tiers, hybrid scoring), security (modes, policies, SecureExecutor, audit DB), 2 Textual UIs + Rich Live display, observability (tracer, spans, metrics, SQLite exporter, event store).

---

## 5. Key Findings

1. **One protocol, three client implementations.** `daemon/client.py` (asyncio), `daemon/fastclient.py` (sync stdlib), and `web/src/daemon/client.ts` (browser) all speak the envelope protocol. Constants in `web/src/daemon/protocol.ts` and `web/src/daemon/events.ts` are hand-mirrored from Python — there is no generated/shared source of truth, so a rename on one side will fail silently at runtime, not at build time.
2. **Run-id dedupe is the correctness keystone.** The browser's reconnect resubmits the run with the *same* id; only the daemon's atomic `_run_ids` claim (`server.py:554-560`) guarantees the kernel task isn't executed twice. This is covered by `test_client_reconnect.py` (4 tests) — good.
3. **Bootstrap trust model is sound but URL-fragile.** The credential is single-use, short-TTL, scoped per daemon instance, and never the permanent token. But it travels in the page URL: browser history, referer headers, and screenshot tools can leak it. `_prune_bootstrap_tokens` bounds exposure only for the daemon's own lifetime.
4. **Environment defect (not repo code): the npm registry served a tampered `react`.** `npm install` produced a stub `react` (index = `require("placeholder-react")`, no `exports`, truncated package.json) that broke `react/jsx-runtime` resolution. Mitigation: `npm pack react@19.0.0` (the registry tarball itself was real) → install from local tarball → restore the real `package.json` into `node_modules/react/`. Any fresh clone/CI must reproduce this workaround or pin integrity.
5. **`status --web` gap fixed.** NEW 1's dashboard URL carried only `bootstrap`; the browser had no `ws_port`. Now the URL carries both and `App.tsx` derives `ws://127.0.0.1:<ws_port>/`.
6. **Agent runs have real filesystem side effects** — a smoke run in this audit wrote `hello.txt`/`output.txt` into the project root (restored/removed). Expected for a 4-tool registry with `shell.execute`, but the dashboard has no visible indication a run is mutating the tree beyond the timeline's step list.

---

## 6. Recommendations (priority order)

1. **HIGH** — Add a protocol-contract guard: a test that `web/src/daemon/protocol.ts` + `events.ts` constants equal `runtime/transport/protocol.py` + `core/events.py` (parse both, assert equality). Prevents silent cross-language drift as the WS surface grows.
2. **MEDIUM** — Add Vitest for `web/src/daemon/client.ts` using a fake `WebSocket` (request correlation, run streaming, heartbeat, stale watchdog, backoff resubmit, cancellation). The Python side is tested; the browser side currently relies on typecheck + manual E2E.
3. **MEDIUM** — CI gate on both: `pytest -q` **and** `web/` `npm run build` + `npm run typecheck`. Today only the Python suite is runnable as the single verification step.
4. **MEDIUM** — Harden the bootstrap flow: after a successful auth, clear `bootstrap`/`ws_port` from `window.history` and treat the credential as spent; document that `status --web` URLs should not be shared/screenshotted. Consider a shorter TTL.
5. **LOW** — Carry over NEW 1: wire the named-pipe client (or drop the bind), add a real Textual task endpoint, emit `context.compacted`, route `providers/` through the circuit breaker.
6. **LOW** — Pin `react`/`react-dom` to exact versions with `integrity` in the lockfile and note the registry-tampering workaround in `web/README` (if one is added) so builds are reproducible elsewhere.

---

## 7. Test Coverage Snapshot

| Area | Tests |
|---|---|
| Daemon reliability (IPC, churn, auth, REPL survival) | `tests/test_daemon.py` — 17 |
| **WebSocket transport + bootstrap (NEW)** | `tests/test_daemon_ws.py` — 11 |
| **Client reconnect / same-id resume (NEW)** | `tests/test_client_reconnect.py` — 4 |
| Secure executor boundary (incl. shell audit fix) | `tests/test_executor_security.py` — 28 |
| Security fixes (sandbox/generated-code/IPC cap) | `tests/test_security_fixes.py` — 16 |
| Observability | `tests/test_observability.py` — 20 |
| Memory (Stage 1 + Mem + integration) | `test_memory_stage1.py` (13) + `test_mem.py` (14) |
| Context engine | `tests/test_context_engine.py` — 14 |
| UX / startup / task-observer / TUI | 11 / 9 / 6 / 4 |
| E2E agent→shell→executor | `tests/test_executor_e2e.py` — 3 |
| Imports / named-pipe | `test_imports.py` (3) + `test_pipe_ipc.py` (1) |

**Suite: 174 passed** (64s). Web: `npm run build` (tsc -b + vite) green; dashboard E2E over WS verified against a live daemon (bootstrap auth → streamed run → `stream.result success=True`).
