# JARVIS MK-X — Architecture Audit (NEW 1)

> **Date:** 2026-08-10
> **Scope:** Active tree (excludes `venv/`, `_quarantine/`, `_quarantine_removed/`, `research_files/`, `_archive/`).
> **Method:** Source walk of all pipelines + error paths + feature inventory; cross-checked against the running test suite (154 passed).
> **Companions:** `audits/audit_before.md` (security baseline), `audits/audit_after.md` (security after). This report is a *structural* audit: error architecture, pipelines, features — not a bandit/ruff recount.

---

## 1. Executive Summary

| Area | Verdict | Notes |
|---|---|---|
| Error architecture | GOOD — result-object driven | 4 custom exceptions, all in the daemon boundary; every other failure is surfaced as data (`ToolResult`/`ExecResult`/`AgentResult`) + audit trail |
| Resilience stack | STRONG but unevenly wired | Fallback chain, cooldowns, circuit breaker, retries, shielded runs all exist; some components are standalone/unwired |
| Pipelines | 9 identified; 7 load-bearing | Named-pipe IPC + knowledge_graph + several legacy subsystems are built but not wired into the active agent path |
| Features | Broad | CLI/REPL, 4-tool registry, daemon IPC, 5 providers, memory stack, security stack, 2 Textual UIs, observability |
| Two agent paths | **Biggest architectural risk** | Legacy `core/jarvis.py`/`core/executor.py` chain coexists with the active `core/agent/loop.py` path |
| Tests | 154 passed | 17 files; security + daemon + memory + observability best covered |

---

## 2. Error Architecture

### 2.1 The exception surface is deliberately tiny

Only **4 custom exception classes** exist, all at the daemon transport boundary:

| Exception | File:Line | Base | Meaning |
|---|---|---|---|
| `DaemonError` | `daemon/client.py:40` | `Exception` | The daemon replied with an error frame |
| `DaemonDisconnected` | `daemon/client.py:44` | `Exception` | Connection dropped or never authenticated |
| `FastError` | `daemon/fastclient.py:29` | `Exception` | Sync fast-path connection/protocol failure |
| `DaemonAlreadyRunning` | `daemon/server.py:70` | `RuntimeError` | A healthy daemon already owns the project |

There is **no exception hierarchy** — every class is a leaf. The design philosophy everywhere else is **failures-as-data**, not exceptions:

| Result type | Location | Fields |
|---|---|---|
| `ToolResult` | `tools/schema.py:11-18` | `success / output / error / metadata` |
| `ExecResult` | `security/executor.py:111-135` | `success / stdout / stderr / exit_code / duration_ms / timed_out / blocked / reason / mode` |
| `SandboxResult` | `security/sandbox.py` | sandbox-specific analogue |
| `AgentResult` | `core/agent/loop.py:29-50` | `success / response / trace_id / state / error / observation / perf` |
| `ProviderHealth` | `providers/base.py:19-28` | availability + cooldown state |
| `LLMResponse` | `providers/types.py` | text / tool_calls / usage / finish_reason |

### 2.2 Error flow per subsystem (the "architecture of each error")

**2.2.1 Agent loop** (`core/agent/loop.py`)
- Whole-run: `run()` wraps everything in `try/except Exception` (`:175-184`) → records `task.failed`, appends to `state.errors`, returns `AgentResult(success=False)`. The observer is always finalized in `finally` (`:185-187`).
- Empty model response: built into a failure string with `finish_reason` detail (`:126-141`).
- Max-iterations: falls out of the loop → `task.failed` ("max iterations reached", `:189-201`).
- Per tool call (`_handle_call`, `:251-297`): unknown tool → `TOOL_FAILED` + `ERROR:` injected back into the LLM context; permission denial → `PERMISSION DENIED` injected; tool failure → `step_finished(step, "error")` + `ERROR: {result.error}` fed back to the model. **Errors become model-visible context — the loop heals itself by feeding failures back.**
- Decision-memory write is firewalled: `_record_decision` wraps persistence in `except Exception: pass` (`:221-237`) so a finished task is never re-failed by a memory write.

**2.2.2 Tool executor** (`core/agent/tools.py`)
- Unknown tool → `ToolResult(success=False, "Unknown tool: …")` + `TOOL_FAILED` event (`:44-54`).
- Handler exceptions → caught, truncated to 500 chars, returned as failed `ToolResult` (`:76-93`). Sync handlers run via `asyncio.to_thread` (`:60`) so a blocking handler cannot stall the loop.

**2.2.3 Permission gate** (`core/agent/permissions.py:56-81`)
- Mode disallow → `(False, reason)` + `permission.checked` event. Security denial → same. Every decision is recorded (`PERMISSION_CHECKED` event + `security/audit.py` entry via `SecurityEngine._log_allowed`/`_log_denied`).

**2.2.4 Provider layer** (`providers/base.py`, `providers/router.py`)
- `check_quota` (`:93-114`): RPM/RPD + cooldown blocks availability.
- `record_rate_limit` (`:125-137`): cooldown `min(120, 10 * 2**n)` + jitter, deliberately **not** feeding the failure counter.
- `record_failure` (`:138-154`): exponential cooldown `min(300, 30 * 2**(n-3))` full-jitter; provider disabled at 5 consecutive failures.
- Router (`:104-161`): iterates the fallback chain; per-provider failure → `provider.fail.{name}` metric + warning; all failed → `RuntimeError("All providers failed. Last error: …")`. **Errors here escalate to a hard exception only when every provider is exhausted.**

**2.2.5 Daemon IPC** (`daemon/server.py`, `daemon/client.py`, `runtime/transport/tcp.py`)
- `_safe_send` (`:90-96`): a dead client can never take the daemon down.
- `_dispatch` (`:316-348`): unknown type → `MSG_ERROR`; handler exception → `MSG_ERROR` with `str(exc)[:500]`.
- `_on_client` (`:275-312`): bad auth → `MSG_ERROR unauthorized`; disconnect logged as an ordinary warning; active runs shielded from cancellation.
- Shielded/detached runs (`_shielded_kernel_run:490`, `_run_locked:506`): a client that vanishes mid-run does not kill the kernel work; the next client waits for the lock — surfaced via the `run.queued` frame.
- Client timeouts (`daemon/client.py:63,67`): `CONNECT_TIMEOUT = 5.0`, `IDLE_TIMEOUT = 120.0`; `_recv` turns timeout into `DaemonError`, `None` frame into `DaemonDisconnected`.
- TCP transport: `ConnectionResetError`/`OSError` on receive → treated as EOF/disconnect (`tcp.py:47-50`), a close never raises.
- The REPL (`cli/main.py`) routes every failure through `_run_daemon_goal` (`:476-502`): `DaemonDisconnected` → "daemon connection lost", `DaemonError`/`ConnectionError`/`OSError` → "daemon error", anything else → "unexpected error". **No daemon failure can crash the REPL.**

**2.2.6 Secure executor** (`security/executor.py`)
- Spawn failure `(OSError, ValueError)` → `ExecResult(success=False, exit_code=-1)`.
- `TimeoutExpired` → `timed_out=True` + process-tree kill (`taskkill /T /F` on Windows, `killpg` elsewhere, `:378-380, 421-445`).
- Output decode uses `errors="replace"`; reader threads are bounded (`_drain`, `:401-419`).
- Policy rejections → `ExecResult(blocked=True, reason=…)`; every shell execution is audited (hash-only, `tools/shell.py:_audit_shell_execution`).

**2.2.7 Memory**
- JSON parse failure → log + empty-dict fallback (`memory/memory_manager.py:33-51`).
- SQLite sync failure → warning, JSON memory still returned (`:103-119`).
- Embedding model load failure → logged, never retried, deterministic hash-bucket fallback (`memory/vector_store.py:47-63`).
- Write path defers embeddings/graph work to the background lifecycle worker so chat never blocks (`memory/controller.py:92-96`).

**2.2.8 Observability** (`runtime/observability/tracer.py`)
- Instrumentation "can never crash the loop": span end is wrapped in `try/except`, contextvar reset guards `RuntimeError`, and `span()`/`trace()` context managers catch `BaseException`, mark the span `ERROR`, and re-raise.

**2.2.9 Legacy planner path** (`core/executor.py`, `core/cog_error_handler.py`)
- Step retry loop (`:453-521`): up to 3 attempts; `analyze_error` returns `RETRY / SKIP / REPLAN / ABORT`; `SKIP` on a `critical` step is forced to `REPLAN`; unknown tool → user-facing apology. LLM-classifies failures (noisy `print`s) — different philosophy from the deterministic active loop.

### 2.3 Error-visibility gaps (what is still silent)

| Gap | Severity | Location |
|---|---|---|
| ~42 bare `except: pass` in `core/jarvis.py` (legacy path) | LOW | startup warmups, TTS worker, ingestion |
| Circuit breaker not used by `providers/` | MED | only `core/jarvis.py:783-791` |
| `knowledge_graph/`, `inference_engine/`, `reliability_engine/` standalone | MED | wired only via legacy `core/jarvis.py` / `core/container.py` |
| `context.compacted` notification branch has **no emitter** | LOW | `cli/main.py:196` vs `core/context/budget.py:136` |
| `ui/providers.py` has **no task endpoint** (MOCK_TASKS) | LOW | UI shows no live task stream |

---

## 3. Pipelines

### 3.1 Agent execution pipeline (active, load-bearing)

1. `cli/main.py` entry → `app()` → `_resolve_transport` (`:302`) → daemon client or in-process `_build_loop` (`:84`).
2. `AgentLoop.run()` (`core/agent/loop.py:90`) → `tracer.begin` → `decision_logger.begin_task` (trace_id, `:94`) → `observer.start` (`:96`) → `AgentState` (`:97`).
3. `context_builder.build` (`core/agent/context.py:16`) → system prompt + messages.
4. Loop (`:102`): `context_manager.fit_for_loop` (`:104-107`) → `router.complete` (`:110-116`, span with provider/model/latency/tokens) → `state.add_tokens`.
5. No tool calls → `TASK_COMPLETED` (`:142`) / empty → `TASK_FAILED` (`:133`).
6. Tool calls → `_handle_call` (`:251`): `step_started` → registry lookup → `TOOL_REQUESTED` → `permissions.check` (`:266`) → `observe_permission` → `executor.execute` (`:277`) → `step_finished` → `state.record_tool` → tool message appended to context.
7. Loop repeats until finish / max iterations; `_finish_observation` (`:208`) renders the observation; `_record_decision` (`:221`) persists the decision memory.

### 3.2 Provider / LLM pipeline

1. `ProviderRouter.complete` (`providers/router.py:104`) walks the fallback chain `groq → gemini → openrouter → ollama` (`:36`).
2. Per provider: `check_quota` → `complete`/`complete_stream` (adapter: `groq_provider.py:60`, `gemini_provider.py:90` via `asyncio.to_thread`, `openrouter_provider.py:54`, `ollama_provider.py:41`, `opencode_zen_provider.py:34`).
3. Failures → `record_rate_limit` / `record_failure` cooldowns; next provider attempted; all exhausted → `RuntimeError`.
4. `parse_openai_tool_calls` / `parse_ollama_tool_calls` (`providers/types.py:66`) → tool-call messages back to the loop.

### 3.3 Memory pipeline

1. `MemoryAPI` (`memory/api.py:45`) → `MemoryController` (`memory/controller.py:41`).
2. Read: hybrid ranking (`memory/ranking.py`) — SEMANTIC 0.35 / LEXICAL 0.25 / IMPORTANCE 0.20 / RECENCY 0.10 / PROJECT 0.05 / USEFULNESS 0.05 — over tiered stores (`tiered_store.py`: hot 100 LRU / warm 1000 SQLite / cold).
3. Write: fast stores sync, embeddings/graph deferred to `MemoryWorker` (`memory/lifecycle.py:39`, priority HIGH…IDLE).
4. Metadata touch (importance/recency, `metadata.py`), project docs auto-import (`project_knowledge.py`, CLAUDE.md/AGENTS.md/JARVIS.md).
5. Context integration: `ContextManager.fit` (`core/context/manager.py:73`) → compress + trim tool outputs → `context.compacted` report.

### 3.4 Daemon IPC pipeline

1. CLI/fast client → `DaemonClient` (`daemon/client.py:59`) or `FastClient` (`daemon/fastclient.py:56`).
2. Transport: `runtime/transport/tcp.py` (`open_connection`, asyncio streams, NDJSON) — named-pipe server (`runtime/transport/pipe.py`) **starts but no client connects** (built, unused).
3. Server (`daemon/server.py`): `_on_client` (`:275`) → auth (`MSG_AUTH`, registry token) → `_dispatch` (`:316`) → handler map.
4. `_handle_run` (`:438`): swaps `observer.on_event` → `asyncio.Queue` stream → `run.queued` if lock held → `_shielded_kernel_run` → `MSG_RUN_RESULT` (`:478`).
5. `_drain_events` (`:520`) forwards `MSG_EVENT` frames to the client callback in real time.
6. Lifecycle: `daemon/state.py` (instance lock, registry `~/.jarvis/daemons/daemon-<project_id>.json`), `daemon/lifecycle.py` (WMI spawn + env repair), snapshot to `~/.jarvis/state/` after each task and on shutdown.

### 3.5 Observability / telemetry pipeline

1. `tracer.py` contextvar propagation → `Span` (`spans.py`, `perf_counter_ns`).
2. `SqliteExporter` (`exporters.py`) writer thread + bounded queue → `~/.jarvis/perf.db` (WAL), `read_latest/read_slowest/read_summary`.
3. `DecisionLogger` (`core/decision_logger.py:35`) → `EventStore` (`core/event_store.py`, `events.db`, cap 5000) + `AuditLog` (`security/audit.py`, `audit.db`, 5s buffered flush).
4. Rendering: `runtime/observability/dashboard.py` (`render_trace`, `trace_table`, `render_summary`) + `cli.perf` command (`perf_cli`, `cli/main.py:740`).

### 3.6 Security pipeline

1. Tool call → `PermissionEngine.check` (`core/agent/permissions.py:56`) → `ModeManager.is_allowed` (`core/mode_manager.py:130`) → `SecurityEngine.check_permission` (`security/engine.py:71`) → policy (`security/policies.py`) + rate limit + optional confirmation → audit.
2. Execution → `AgentToolExecutor` (`core/agent/tools.py:33`) → tool function → `SecureExecutor.execute` (`security/executor.py:303`) → `CommandPolicy.classify` → structured `shell=False` or governed PowerShell/cmd → resource-bounded run → `ExecResult`.
3. Audit: every permission decision (`allowed`/`denied`/`confirmed`) and every shell execution (hash-only payload) written to `audit.db`.

### 3.7 Tool execution pipeline

1. `build_default_registry` (`tools/__init__.py:13`) registers exactly 4 tools: `filesystem.write`, `filesystem.read`, `filesystem.list`, `shell.execute`.
2. `ToolRegistry.to_openai_tools` (`tools/registry.py:39`) serializes schemas for the model.
3. Dispatch: registry lookup → permission → `AgentToolExecutor.execute` → handler (`tools/filesystem.py`, `tools/shell.py`).
4. Output: `ToolResult` → `truncate` → injected into the model context as a tool message.

### 3.8 UI pipeline

1. `ui/conversation.py` (Textual conversation client) + `ui/tui.py` (dashboard) → `TuiDataSource` (`ui/backend.py:28`: psutil + daemon + mock fallback + background reconnect).
2. Terminal (non-Textual): `cli/ux.py` `LiveTaskDisplay` (Rich `Live`, `auto_refresh=False`, event-driven) + `cli/cockpit.py` + `cli/details.py` renderers.
3. Events flow: daemon `MSG_EVENT` → client callback → `TaskObserver` → Live/Textual widget updates.

### 3.9 Startup pipeline

1. `cli/main.py` `entry()` (`:827`) routes `daemon`/`perf`/`tui` before typer; else `app()`.
2. Daemon: `daemon/server.py:_start_daemon` (`:609`) → env repair → `enable_perf` → `DaemonServer.start` (`:142`) → instance lock → `build_kernel` → warm thread → TCP bind (3 retries) → named-pipe (best-effort) → registry entry.
3. In-process: `_build_loop` (`cli/main.py:84`) profiler-phased: `config.load → tools.registry → project.discover → providers.router → memory.open → memory.docs`, booted in the `jarvis-kernel-boot` background thread so the prompt appears immediately.
4. Kernel: `runtime/kernel.py:build_kernel` (`:31`), `close_kernel` (`:74`); state snapshots via `runtime/state.py` (atomic tmp+rename).

### 3.10 Pipeline health — dead / incomplete edges

| Pipeline edge | Status |
|---|---|
| Named-pipe transport (`runtime/transport/pipe.py`) | Built, server binds — **no client connects** (TCP is the live path) |
| `knowledge_graph/` package (SQLite) | Used only by legacy `core/jarvis.py` — the active memory path uses `memory/graph.py` (JSON) |
| `reliability_engine/` (circuit breaker, health monitor, graceful degradation) | Referenced only via `core/container.py` — not wired into the active loop |
| `inference_engine/`, `systems/`, `workflows/`, `skills/`, `plugins/`, `mcp_jarvis/` | Legacy / standalone — no imports in the active agent path |
| `context.compacted` event | No emitter exists (report flag only) |
| TUI live task stream | `ui/providers.py` has `MOCK_TASKS` but no real task endpoint |

---

## 4. Features Inventory

### 4.1 CLI / REPL
- One-shot goals + interactive REPL; options `--mode` (plan|controlled|smart|agent), `--max-iterations`, `--max-tokens`, `--project-dir`, `--verbose`, `--json`, `--profile-startup`, `--daemon`, `--standalone` (`cli/main.py:240-256`).
- Subcommands: `daemon start|stop|status|list|sweep` (`:671`), `perf latest|slowest|summary` (`:740`), `tui [--dashboard|--mock|--url]` (`:793`).
- REPL slash-commands: `/help /tools /mode /plan /model /models /status /context /tokens /compact /memory /history /tree /resume /cockpit /notifications /verbose /clear /exit`.
- Fast path `python -m cli.fast "goal"` (stdlib-only, warm-daemon round trip).

### 4.2 Tools (active registry — 4)
`filesystem.write`, `filesystem.read`, `filesystem.list`, `shell.execute`. Bounds: read ≤50 MB / 500 entries, output ≤20000 chars; shell timeout 60s (max 300), output cap 8000 chars. `generated_code` exists only in the legacy path (env-gated off by default, statically denylisted, remapped to `filesystem.write`).

### 4.3 Daemon
Single-instance lock, TCP + named-pipe transports, token auth, registry + sweep, state snapshots, event streaming, `run.queued` busy feedback, shielded/detached runs, graceful shutdown, WMI spawn + Windows env repair, 5s connect / 120s idle client timeouts.

### 4.4 Providers
Groq (key rotation), Gemini (2.0-flash), OpenRouter (key rotation), Ollama (qwen2.5:1.5b), OpenCodeZen (free). Fallback chain, cooldowns, health tracking, never eager-imported at startup.

### 4.5 Memory
9 memory types (SEMANTIC…NOTE), hybrid scoring, 3-tier store, metadata touch, decision memory (per-project), project knowledge auto-import, knowledge triple graph (JSON), embedding fallback, background write lifecycle, `~/.jarvis` persistence.

### 4.6 Security
Modes plan/controlled/smart/agent; policies (TOML, hot-reload); permission levels DENIED…UNRESTRICTED; confirmation handler; rate limiting (60s window); SecureExecutor (structured `shell=False` / governed shell, env sanitization, cwd constraints, output caps, timeout + process-tree kill); sandbox; audit DB (every decision + every shell exec); generated-code gate + static scan; IPC frame cap (4 MB); redaction + trust scorer + anomaly detector + adaptive policy (all present, mostly legacy).

### 4.7 UI
Textual conversation client, Textual dashboard, Rich Live task display, cockpit dashboard, notifications, status bar.

### 4.8 Observability
Tracer (contextvars, 512-traces ring), spans, metrics registry, SQLite exporter (perf DB), event store, decision logger, perf CLI dashboard, startup profiler.

---

## 5. Key Findings

1. **Two agent paths coexist.** The active path (`core/agent/loop.py` + 4-tool registry + PermissionEngine) is deterministic and audit-driven; the legacy path (`core/jarvis.py` + `core/executor.py` planner/error-handler) is LLM-classified and noisy. `EXEC_TOOL_ALIASES` (`core/mode_manager.py:30-53`) bridges tool names. **Recommendation:** retire or quarantine the legacy chain to remove a duplicate attack/behaviour surface.
2. **`shell.execute` is now the only command tool** and it is fully audited (hash-only) — the strongest P0 property in the tree, enforced by tests.
3. **Error philosophy is consistent**: data-object results + audit/event trail + fallback values; exceptions are reserved for the daemon boundary, where they are now fully handled in the REPL.
4. **Dead/incomplete edges** (see §3.10) are the main architecture debt: named-pipe IPC built but unused, `knowledge_graph/` superseded by `memory/graph.py`, resilience engine not wired to the loop.
5. **`~/.jarvis` is the single state home** (`perf.db`, `data/*.db`, `daemons/`, `state/`, `knowledge_graph.json`) — easy to snapshot/back up.

---

## 6. Recommendations (priority order)

1. **HIGH** — Resolve the dual-agent-path risk: decide the load-bearing path and quarantine the legacy chain (`core/jarvis.py`, `core/executor.py`, `core/planner.py`, `core/intent_router.py`, `core/action_*`).
2. **MEDIUM** — Wire the named-pipe transport to a client (or remove the server-side bind) so the dual-transport claim is real.
3. **MEDIUM** — Add a real TUI task endpoint (stream real runs into `ui/conversation.py` instead of mock tasks).
4. **MEDIUM** — Emit a `context.compacted` observer event (a report flag exists but nothing emits it).
5. **LOW** — Replace the ~42 silent `except: pass` blocks in `core/jarvis.py` with `logger.debug(..., exc_info=True)` before any legacy-path work continues.
6. **LOW** — Route `providers/` through the circuit breaker now that it is only invoked from the legacy path.

---

## 7. Test Coverage Snapshot

| Area | Tests |
|---|---|
| Daemon reliability (IPC, churn, auth, REPL survival) | `tests/test_daemon.py` — 17 |
| Secure executor boundary | `tests/test_executor_security.py` — 23 (+3 audit regressions) |
| End-to-end agent→shell→executor | `tests/test_executor_e2e.py` — 3 |
| Memory (Stage 1 + Mem + integration) | `tests/test_mem.py` (14) + `test_memory_stage1.py` (13) |
| Observability | `tests/test_observability.py` — 20 |
| Security fixes (sandbox/generated-code/IPC cap) | `tests/test_security_fixes.py` — 14 |
| Context/UX/TUI/startup/imports/task-observer | 9 + 11 + 4 + 9 + 3 + 6 |

**Suite: 154 passed.**
