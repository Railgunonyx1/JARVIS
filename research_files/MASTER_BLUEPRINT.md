# JARVIS MK-X — Master Engineering Blueprint

| Field | Value |
|---|---|
| Version | v4.0 |
| Status | Active Development Specification |
| Last Updated | 2026-08-03 |
| Owners | JARVIS MK-X Architecture |
| Codebase | 60,676 LOC Python, 49 core modules, 8 security modules |
| Related | `DEAD_CODE_MANIFEST.md`, audit reports, performance reports |

This document is the implementation contract for evolving JARVIS MK-X from a
voice-first assistant into a production-grade, auditable autonomous agent
platform. Every phase is status-marked against the current codebase
(`EXISTS` / `GAP` / `NEW`) with files affected, schemas, migration paths, and
validation criteria so an engineering agent can execute it directly.

---

## Executive Summary

JARVIS MK-X already contains most of the infrastructure it needs. The dominant
finding across all phases is **not missing components but missing integration**:

- Audit infrastructure (`security/audit.py`), event sourcing
  (`core/event_store.py`), telemetry (`core/telemetry.py`), and a security
  engine (`security/engine.py`) all exist. **None of them are wired into the
  conversational request path** (`core/jarvis.py`).
- ~23 of 32 top-level packages are true orphans or referenced only by
  `tests/smoke.py`. The production core is ~9 packages.
- There is **no unit test suite** (`tests/` has 3 scripts, 0 pytest cases).
- Performance work is largely complete (see Phase 2); the remaining gap is
  reliability and observability.

Priority order (already user-approved):

```
Phase 5  Auditability Layer Wiring
Phase 3  Verify/Learn Agent Loop
Phase 0  Dead-Code Quarantine (in progress, reversible)
Phase 11/12  Tooling + Test Foundation
```

---

# Phase 0 — Codebase Audit & Dead-Code Quarantine

## Objective

Reduce the 60,676 LOC surface to the true production core, reversibly, without
breaking dynamic loading.

## Current state

- 10 true orphans (0 imports anywhere): `ai_runtime`, `benchmark`,
  `cache_system`, `external`, `gpu_optimization`, `hyper_optimization`,
  `mcp_jarvis`, `os_optimization`, `reasoning_system`, `se_factory`
- ~13 smoke-test-only packages (referenced only by `tests/smoke.py`):
  `digital_twin`, `distributed_engine`, `evolution_engine`,
  `interaction_engine`, `knowledge_engine`, `orchestration_engine`,
  `perception_engine`, `self_evolution`, `system_optimizer`, `workflows`,
  plus the cluster they reference (`knowledge_graph`, `performance_engine`,
  `personal_intelligence`, `voice_engine`)
- Production core: `actions`, `core`, `memory`, `pipeline`, `providers`,
  `security`, `vision` + `web/`, `api/`, `main.py`

## Method

1. Static import inventory (regex over `import`/`from` across all `.py`).
2. **Dynamic-import scan** — grep for `importlib`, `LazyModule`, plugin
   loaders, capability/action registry string names, YAML/JSON registry
   references. This is the decisive gate for `runtime_uncertain` tier.
3. Runtime baseline capture before any move (`phase0_baseline.json`).
4. Quarantine (move, **never delete**) into
   `_quarantine/<date>/{confirmed_orphans,runtime_uncertain}/`.
5. Boot + smoke verification after each move batch.
6. Record per-component manifest with rollback instructions.

## Files affected

```
MODIFY  (moves): _quarantine/<date>/...
CREATE  research_files/DEAD_CODE_MANIFEST.md
CREATE  research_files/architecture/dependency_graph_before_phase0.md
CREATE  research_files/phase0_baseline.json
```

## Completion criteria

- [ ] Every moved dir has a manifest entry with evidence + rollback step
- [ ] Server boots and chat round-trip passes with identical results
- [ ] No import errors during boot

---

# Phase 1 — Core Architecture Refactor

## Current state (largely EXISTS)

DI container (`core/container.py`), service registry (`core/service_registry.py`),
event bus, CQRS concepts, lazy module loading (`core/lazy_imports.py`),
config (`core/config.py`). The architecture exists; it is under-enforced.

## Target changes

- Consolidate the 110+ `self.x = None` optional-attribute declarations in
  `core/jarvis.py:__init__` into a typed `OptionalSubsystems` dataclass.
- Route subsystem acquisition through the service registry (no direct
  `from core.X import Y` inside `jarvis.py` where a registry exists).
- Enforce one-way dependency rule: `core/` must not import `actions/` (the
  registry breaks this today via `action_init` — invert with capability names).

## Files affected

```
MODIFY  core/jarvis.py
MODIFY  core/container.py
MODIFY  core/service_registry.py
```

## Validation

`pytest tests/test_architecture.py` (module-boundary assertions) — Phase 12.

---

# Phase 2 — Performance & Latency

## Current state (mostly DONE this cycle)

| Item | Status |
|---|---|
| Pooled HTTP clients (`core/http_pool.py`) | DONE |
| Lazy startup (`_ensure_started`) | DONE |
| sqlite-vec + MiniLM embeddings (`memory/vector_store.py`) | DONE |
| orjson fast JSON (`core/json_fast.py`) | DONE |
| Semantic response cache (`core/cache.py`) | DONE (opt-in) |
| STT/TTS off-thread (`pipeline/stt.py`, `pipeline/tts.py`) | DONE |
| TTS precache `Semaphore(4)` | DONE |

## Remaining gaps

- **Context compression cap**: `core/context.py` summary at 2000 chars; prune
  history above N turns before LLM call.
- **WAL everywhere**: ensure `memory/tiered_store.py`, `core/cache.py` DBs use
  `PRAGMA journal_mode=WAL`.
- **Provider warm-up**: ping selected provider on first request rather than at
  cold start (already deferred); add adaptive keep-warm.
- **Streaming JSON**: SSE yields already use `fast_dumps()` — extend to
  telemetry broadcast (done) and any remaining `json.dumps` hot paths.

## Validation

`tests/benchmarks.py` before/after; target TTFT < 400ms, full round-trip
< 1.5s on the primary provider.

---

# Phase 3 — Multi-Agent System (Observe→Reason→Plan→Execute→Verify→Learn)

## Current state

- Planner (`core/planner.py`) with mode-filtered real tool names — DONE
  (hallucination bug fixed).
- Executor (`core/executor.py::AgentExecutor`) with replan/error recovery.
- `core/supervisor.py`, `core/workflow.py`, `core/task_manager.py`,
  `core/task_queue.py` exist but are not composed into a full loop.

## Gap (build the Verify→Learn half)

1. **Verify agent** — after tool execution, verify result against goal:
   `core/verify_agent.py` with success criteria (output non-empty, no error
   markers, permission-safe). Emits `verify.passed` / `verify.failed`.
2. **Learn agent** — on verify failure, record the failure signature
   (tool, params-hash, error) into the event store for future planning hints.
3. Parallel tool execution — batch independent steps via `asyncio.gather`
   with a semaphore.

## Files affected

```
CREATE  core/verify_agent.py
CREATE  core/learn_agent.py
MODIFY  core/executor.py (verify step after _call_tool)
MODIFY  core/supervisor.py (compose loop)
```

## Completion criteria

- [ ] A failing tool step produces a `verify.failed` event and a recorded
      learning entry
- [ ] Independent steps execute concurrently (benchmark shows speedup)

---

# Phase 4 — Memory System

## Current state (largely DONE)

- sqlite-vec KNN (`memory/vector_store.py`) with MiniLM 384-dim — DONE
- Tiered store (`memory/tiered_store.py`), context engine (`core/context.py`)
- Semantic cache (`core/cache.py`)

## Gaps

- **Memory ranking**: score memories by recency × relevance × confidence and
  inject only top-K into the prompt.
- **Memory pruning**: TTL + dedup pass for low-importance facts.
- **Procedural memory**: store successful plan→outcome pairs from Phase 3
  Learn agent as reusable workflows (`memory/procedural.py`).
- **Privacy controls**: per-category opt-out (memories of type `fact` vs
  `preference` vs `private`).

## Files affected

```
CREATE  memory/procedural.py
MODIFY  memory/vector_store.py (ranking)
MODIFY  core/context.py (prompt injection top-K)
```

---

# Phase 5 — Auditability / Reliability Layer ⭐ (top priority)

## Objective

Connect the existing reliability infrastructure into the execution pipeline.
Today the wiring is missing: `security/audit.py` is only invoked for security
denials; `core/event_store.py` has zero production callers.

## Current state

| Component | Exists | Wired |
|---|---|---|
| `security/audit.py` AuditLog (sqlite, buffered) | YES | PARTIAL (denials only) |
| `core/event_store.py` EventStore (sqlite, trace_id) | YES | NO |
| `core/telemetry.py` LatencyTracker | YES | YES (jarvis.py) |
| `core/diagnostics_engine.py` | YES | YES |
| `core/log_queue.py` | YES | YES |

## Target architecture

```
User Request (text)
    │
    ▼
jarvis.process_text[_streaming]
    │  DecisionLogger.begin_task(request, source) → trace_id
    ├─► event: request.received
    ├─► event: intent.classified  (intent.name, confidence)
    ├─► event: path.decided       (deterministic | action | llm | semantic_cache)
    │
    ├─► action_registry.execute / _handle_action
    │       ├─► event: action.executed  (intent, handler)
    │       └─► audit: tool.executed    (tool, params_hash, allowed, success, ms)
    │
    ├─► router.complete[_stream]  (LLM path)
    │       └─► event: llm.completed  (provider, model, tokens, latency)
    │
    └─► event: task.completed | task.failed  (latency, source)
    │
    ▼
EventStore (events.db)  +  AuditLog (audit.db)
    │
    ├─► core/replay_engine.py  (reconstruct trace_id timeline)
    └─► core/failure_analyzer.py (attribute failure to subsystem)
```

## Implementation steps

1. **DecisionLogger** (`core/decision_logger.py`): `begin_task()` returns
   `trace_id`; `record(trace_id, name, **data)` writes a `StoredEvent` to the
   `EventStore` (lazy singleton); `record_tool(...)` also writes an
   `AuditEntry` to `AuditLog`.
2. **Trace ID**: `uuid4().hex[:12]`, propagated as `trace_id` through
   `process_text` / `process_text_streaming` and into executor calls.
3. **Wiring points** in `core/jarvis.py`:
   - `process_text` (L381): begin task, intent event, path decision, LLM
     event, completion/failure event.
   - `process_text_streaming` (L589): same, plus semantic-cache-hit event and
     `tts` chunk timing.
   - `_handle_action` (L507): action.executed event + tool audit entry.
4. **Executor** (`core/executor.py::AgentExecutor`): log plan.created,
   permission.checked (mode + security), tool.executed per step, failure with
   recovery decision. `_call_tool` wraps execution to time and record.
5. **ReplayEngine** (`core/replay_engine.py`): `replay(trace_id)` → ordered
   timeline from `EventStore.query`; `recent_tasks(limit)` → distinct
   trace_ids with start/finish.
6. **FailureAnalyzer** (`core/failure_analyzer.py`): `analyze(trace_id)` →
   if last event before a `task.failed` is a failed `tool.executed`, attribute
   to that tool + suggest recovery (retry / replan / abort); if a task started
   but has no completion event, report `missing completion event (timeout)`.
7. **API surface** (`web/server.py`):
   - `GET /api/audit/recent?limit=N`
   - `GET /api/audit/task/<trace_id>`
   - `GET /api/audit/stats`
   - `GET /api/audit/failure/<trace_id>`

## Files affected

```
CREATE  core/decision_logger.py
CREATE  core/replay_engine.py
CREATE  core/failure_analyzer.py
MODIFY  core/jarvis.py
MODIFY  core/executor.py
MODIFY  security/audit.py   (add trace_id column, ALTER-migrated)
MODIFY  web/server.py        (audit endpoints)
```

## Testing requirements

```
Input: "Open browser"
Expected:
- event request.received exists with trace_id
- event path.decided = action
- audit entry tool=open_app success=true
- event task.completed present
- replay_engine.replay(trace_id) returns full ordered chain
```

## Dependencies

- Depends on: Phase 12 (pytest) to lock behavior; EventStore/AuditLog already
  present.
- Required before: Phase 3 (verify agent reads decision events).

## Completion criteria

- [ ] Every user request creates a trace (request → completion events)
- [ ] Every tool execution is recorded in AuditLog + EventStore
- [ ] Failed executions attribute to the responsible subsystem
- [ ] HUD/API can display the execution timeline

---

# Phase 6 — Security Hardening

## Current state (largely DONE this cycle)

- Localhost bind + WS first-message auth token — DONE
- Shell deny-by-default allowlist (`actions/shell_exec.py`) — DONE
- File sandbox with real path validation (`actions/file_manager.py`) — DONE
- CSP + security headers — DONE
- Cloud-TTS redaction (`security/redaction.py`) — DONE
- Rate-limit no longer self-disables providers — DONE

## Gaps

- **Prompt-injection defense**: classify external content (web fetch results,
  RSS, plugin output) at a trust boundary before it reaches the system prompt.
  Tag external data with `<external_source>` markers and instruct the model to
  never obey instructions inside them; harden at `external/web_scraper.py` /
  `news_fetcher.py` output stage.
- **Tool permission deny-by-default in executor**: `AgentExecutor` already
  checks mode + security; extend the same check to `ActionRegistry` handler
  dispatch so every action path enforces policy.
- **Secret management**: move API keys to environment + Windows DPAPI-backed
  store; never in `config/api_keys.json`.

## Files affected

```
MODIFY  external/web_scraper.py, external/news_fetcher.py (trust boundary)
MODIFY  core/action_registry.py (permission check)
MODIFY  core/config.py (secret handling)
```

---

# Phase 7 — Voice Pipeline Engineering

## Current state

- STT cloud→local fallback (`pipeline/stt.py`), off-thread — DONE
- TTS Piper (local, threaded) + Edge (cloud, redacted) — DONE
- Phrase-level streaming TTS with background queue — DONE
- Resource governor throttles TTS under load — DONE

## Gaps

- **Barge-in**: cancel current TTS playback when new wake word / PTT detected.
- **Streaming STT** (Groq supports it): feed partial hypotheses for faster
  perceived response.
- VAD threshold adaptation (`pipeline/vad.py`).
- Wake-word async callback fix (`pipeline/wake_word.py`) — coroutine currently
  dropped.

## Latency targets

| Stage | Target |
|---|---|
| Wake word → VAD | < 150ms |
| STT | < 300ms (cloud) |
| LLM TTFT | < 400ms |
| TTS first audio | < 250ms |
| Full round-trip | < 1.2s |

---

# Phase 8 — Vision System

## Current state

`vision/camera.py` (lazy, max 15fps), `actions/screen_capture.py`,
`actions/screen_analyzer.py` (Gemini analysis). Camera wired in `web/server.py`.

## Gaps

- Screen understanding loop (periodic frame → caption → memory)
- OCR for screen text extraction
- Visual memory (embed frame captions into vector store)
- Explicit hardware/backend choice: local (Moondream/SmolVLM) vs cloud (Gemini
  Vision), selected by resource governor

## Files affected

```
CREATE  vision/ocr.py
CREATE  vision/screen_loop.py
MODIFY  vision/camera.py
MODIFY  memory/vector_store.py (visual captions)
```

---

# Phase 9 — Desktop Automation System

## Current state

- `actions/desktop_automation.py` (media/volume/hotkeys, pyautogui)
- `actions/input_control.py`, `actions/browser_control.py`,
  `actions/system_settings.py`, `actions/window_manager.py`
- File manager now sandboxed; shell allowlisted

## Gaps

- **Action verification**: after desktop action, verify state (e.g. window
  exists) before reporting success.
- **Rollback**: for file/config mutations, snapshot originals and restore on
  failure.
- Permission checks wired through the shared policy engine for every action.

## Files affected

```
MODIFY  actions/desktop_automation.py (verify)
CREATE  actions/rollback.py
```

---

# Phase 10 — Frontend / HUD

## Current state

React + Tauri (`frontend/`), WebSocket with auth-first connect, orjson SSE,
CSP headers. Release exe rebuilt (5.4 MB).

## Gaps

- **Audit timeline view** (Phase 5): render `/api/audit/task/<id>` as a
  step-by-step timeline.
- **Failure badges**: when `failure_analyzer` attributes a failure, surface
  subsystem + recovery in HUD.
- DOM batching via `requestAnimationFrame` for token rendering (reduce repaints).
- Service worker offline caching of static assets.

## Files affected

```
MODIFY  frontend/src/ (components: AuditTimeline, FailureBadge)
MODIFY  frontend/src/chat.js / app.js (token batching)
```

---

# Phase 11 — Development Tooling

## Current state (GAP)

No `ruff`, `mypy`, `bandit`, `pytest` configuration exists. `tests/` has 3
standalone scripts. `frontend/` has no ESLint config.

## Add

```
pyproject.toml / ruff.toml     ruff (linter+formatter)
mypy.ini                       type checking (strict on core/)
bandit.yaml                    security linting
pytest.ini                     test discovery
frontend/.eslintrc             ESLint + Prettier
```

Commands:

```
uv pip install ruff mypy bandit pytest pytest-asyncio
ruff check core actions pipeline memory security web
mypy core
bandit -r core security actions
```

## Validation

- `ruff check` clean on the 7 production packages
- `mypy` no errors on `core/`
- `bandit` no HIGH findings

---

# Phase 12 — Testing Strategy

## Current state (GAP — highest reliability risk)

`tests/smoke.py`, `tests/benchmarks.py`, `tests/comprehensive_audit.py` — none
are pytest tests.

## Plan

| Layer | Files | Framework |
|---|---|---|
| Unit | `core`, `security`, `memory` (DecisionLogger, ReplayEngine, FailureAnalyzer, mode manager, file sandbox, redaction) | pytest |
| Integration | chat round-trip, tool execution, WS auth, audit chain | pytest-asyncio |
| AI evaluation | plan validity, tool-name validity, hallucination spot-checks | pytest + model calls (tagged `@ai`) |
| Performance | latency budgets (TTFT, round-trip) | pytest-benchmark |
| Security | RCE path tests, shell/file deny cases, prompt-injection marker test | pytest |
| Failure sim | missing completion event → FailureAnalyzer attribution | pytest |

## Validation

`pytest -m "not ai"` green in CI; `pytest -m ai` run manually (cost-gated).

---

# Phase 13 — Implementation Order

| Order | Phase | Priority | Dependency | Effort |
|---|---|---|---|---|
| 1 | Phase 5 Auditability wiring | HIGH | — | 1-2 days |
| 2 | Phase 12 test foundation (unit tests for Phase 5) | HIGH | Phase 5 | 1-2 days |
| 3 | Phase 3 Verify/Learn agents | HIGH | Phase 5 | 2-3 days |
| 4 | Phase 0 quarantine (in progress) | MED | baseline | 0.5 day |
| 5 | Phase 11 tooling (ruff/mypy/bandit) | MED | — | 0.5 day |
| 6 | Phase 6 prompt-injection trust boundary | MED | — | 1 day |
| 7 | Phases 4/7/8/9/10 remaining gaps | LOW | prior | ongoing |

Each task must be committed in isolation so rollback is a single operation.

---

# Phase 14 — Final Production Architecture

## Target architecture

```
                 JARVIS MK-X

                    USER
                     │
              Voice / Vision / Web (HUD)
                     │
          ┌──────────┴──────────┐
          │   Cognition Engine   │  intent, context, model routing
          └──────────┬──────────┘
                     │
          Multi-Agent Orchestrator   (Planner / Executor / Verify / Learn)
                     │
        ┌────────────┼────────────┐
        │            │            │
  Tool Executor   Memory System   Governance Layer
  (sandboxed)     (sqlite-vec)    (DecisionLogger / Policy / Risk /
                                  ReplayEngine / FailureAnalyzer)
        │            │            │
        └────────────┴────┬───────┘
                          │
                 EventStore + AuditLog + Telemetry
                          │
                 Telemetry + HUD (timeline, failures)
```

## Technology stack

- Python 3.12, asyncio, Flask (waitress for prod), httpx pool
- SQLite + sqlite-vec (memory + events + audit), WAL
- MiniLM all-MiniLM-L6-v2 embeddings, orjson
- Providers: Groq, OpenRouter, Gemini, Ollama, opencode-zen (ModelManager
  routed)
- Frontend: React + Vite + Tauri, WebSocket (auth-first)
- Tooling: ruff, mypy, bandit, pytest

## Performance targets

| Metric | Target |
|---|---|
| Boot to listen | < 2s |
| Idle RAM | < 250 MB |
| LLM TTFT | < 400 ms |
| Voice round-trip | < 1.2 s |
| Vector search | < 10 ms |
| Memory scale | 100k+ vectors |

## Security model

- Bind 127.0.0.1, WS token auth, CSP, redaction at egress
- Deny-by-default tool policy (mode_manager + security engine)
- File/shell sandboxes with real-path validation
- Audit trail for every decision; replay + failure attribution

## Scalability

- Stateless web layer; shared sqlite for local single-user. Cloud scale-out
  replaces sqlite with Postgres + pgvector while keeping the EventStore/
  DecisionLogger contract unchanged.
