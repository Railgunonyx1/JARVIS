# JARVIS MK-X — Agent Conventions

## Architecture Contract (FREEZE)

```
USER / CLIENT -> INTENT ROUTER -> AGENT KERNEL -> HARNESS -> MODEL GATEWAY
    -> PROVIDER ROUTER -> MODEL -> TOOL EXECUTOR -> SANDBOX + PERMISSIONS
    -> OBSERVATION -> VERIFICATION -> BUS EVENT -> {TUI, Persistence, MCP, ACP}
```

### Invariants

1. **Single tool boundary.** All individual tool execution MUST pass through
   `ToolExecutionService`. No protocol, adapter, or agent path may bypass it.

   ```
   Terminal ----|
   MCP ---------|
   ACP ---------|---> ToolExecutionService ---> Permission ---> Executor ---> Result
   Codex -------|
   ```

2. **Harness != Model.** Harness controls HOW the agent reasons (planning, tools,
   verification). ModelGateway controls WHICH model runs. They compose independently.

3. **BusEvent is the only event type.** Terminal events are BusEvent aliases.
   Every meaningful action emits a BusEvent with `schema_version` and `session_id`.

4. **Verification is a post-execution gate.** Runs after the execution phase,
   not after every tool call. On failure: agent receives structured failure context,
   transitions VERIFYING -> RECOVERING -> EXECUTING (retry with context).

5. **Failure classification is deterministic.** Precedence:
   CANCELLED > TIMEOUT > PERMISSION_DENIED > MALFORMED_TOOL > CONTEXT_OVERFLOW
   > PROVIDER_FAILURE > MODEL_FAILURE > TOOL_FAILURE

6. **RECOVERING != ROLLED_BACK.** RECOVERING = agent repairs current state.
   ROLLED_BACK = system reverts changes. Both coexist.

## Key Files

| Component | File |
|-----------|------|
| Agent loop | `core/agent/loop.py` |
| Tool service | `core/agent/tool_service.py` |
| Verification | `core/agent/verification.py` |
| Harness | `core/harness/__init__.py` |
| Model gateway | `providers/model_gateway.py` |
| Event bus | `runtime/event_bus.py` |
| State machine | `core/agent/state.py` |
| Permissions | `core/agent/permissions.py` |
| Protocols | `runtime/protocols/__init__.py` |
| Authority memory | `memory/authority.py` |
| Composition root | `runtime/kernel.py` |
| Code-scan gate | `security/code_scan.py` |

## Current Sprint: Phase A — Kernel Integration

| Sprint | What | Status |
|--------|------|--------|
| 20K | AgentLoop -> ToolExecutionService (single boundary) | Done |
| 20L | VerificationEngine as post-execution gate | Done |
| 20M | ACP/Codex route through ToolExecutionService | Done |
| 20N | RECOVERING state + deterministic FailureClass | Done |
| 20P | Unified pipeline tests + no-bypass architecture test | Done |

**Legacy execution chain** (`core/executor.py`, `core/task_queue.py`,
`workflows/`) is quarantined under `_quarantine/`. Generated-code scanning and
its gate live in `security/code_scan.py` (`check_generated_code`,
`FORBIDDEN_CODE_PATTERNS`, `generated_code_enabled`, `run_generated_code`).

**Test strategy:** Build all implementation first, run full test suite once at end of Phase A.

## Phase B — J-Browser (Chromium agent browser)

Built on `jbrowser` branch (from clean `main`). J-Browser is an optimized
Chromium agent-browser platform that inherits JARVIS's full agent stack
(skills, tools, memory, EventBus) on the same branch — no copy.

| Area | Where |
|------|-------|
| Optimized launch flags | `jbrowser/optimization.py` (GPU raster, QUIC, num-raster-threads, tab freezing, 12-tab cap) |
| Engine abstraction | `jbrowser/backend/base.py` (ABC) + `jbrowser/backend/playwright.py` (headed+persistent, WebScraper fallback) |
| Tabs / Sessions | `jbrowser/tabs.py` (stable tab ids), `jbrowser/sessions.py` (persistent profiles under `config/browser_profiles/`) |
| Page context | `jbrowser/page_context.py` (`[elN]` handles for agent reasoning) |
| Events | `jbrowser/events.py` (`browser.*` BusEvents via `runtime.event_bus`) |
| Permissions | `jbrowser/permissions.py` (low/medium/high, approval gating) |
| Facade + tools | `jbrowser/controller.py` (`get_controller()`), `jbrowser/tools.py` (`browser.*` handlers) |
| Skills transfer | `jbrowser/skills.py` — surfaces the canonical `skills/` registry (browser_automation, web_research, ...) |
| CLI | `python -m apps.jbrowser open/tabs/read/screenshot/status/repl` |

Playwright is optional (lazy import); J-Browser unit tests mock the backend so the
suite passes without it (`pip install playwright` + `playwright install chromium`
to actually browse). Single-engine discipline holds: legacy `tools/browser.py`
handlers AND `external/browser_agent.py` both route through `get_controller()`
→ `PlaywrightBackend` (one Playwright engine). `BrowserAgent` is retained as a
deprecated compatibility adapter. Everything flows through
`ToolExecutionService` (no bypass).

Implementation notes (accuracy contract — doc matches code):
- **Lazy launch (implemented):** `create_session` is logical only and never
  launches Chromium. The browser/context starts on the first page-needing
  operation (`create_tab`/`navigate`/`read`).
- **Session isolation (implemented):** each session maps to its own Playwright
  `BrowserContext`, so cookies/storage/auth are isolated between sessions.
  Persistent sessions use `launch_persistent_context(profile_dir)` (survive
  restarts); ephemeral sessions each get a fresh `new_context()` on one shared
  browser. `close_session` is scoped to that session; `shutdown()` releases all
  native resources.
- **Network governance (implemented):** `jbrowser.network.BrowserNetworkPolicy`
  denies private/loopback/link-local destinations by default *before* `goto`,
  so an agent browse cannot pivot into localhost/private services.
- **Browser risk (single source of truth):** `tools/classification` owns
  `browser_risk_for_tool`; `jbrowser.permissions` is a thin adapter. Mutations
  (click/type/submit/...) are HIGH + destructive (approval-gated); reads/nav are
  LOW.
- **Controller serialization (implemented):** public `BrowserController`
  operations are serialized under an RLock so concurrent tool threads cannot
  corrupt the non-thread-safe Playwright engine.
- **Live integration tests (opt-in):** `tests/test_jbrowser_live.py` is gated
  behind `JARVIS_RUN_BROWSER_LIVE=1` and marked `@pytest.mark.browser` so the
  default suite stays hermetic (never starts a Playwright driver). Run with
  `JARVIS_RUN_BROWSER_LIVE=1 pytest tests/test_jbrowser_live.py`.
- **Known limitation (documented, not a bug fix yet):** the standalone CLI
  (`python -m apps.jbrowser ...`) runs each subcommand in a fresh process, so
  `open` then `tabs/read` in separate invocations do not share tabs. A persistent
  daemon/client split is future work; within one process (REPL, agent tools) tabs
  persist normally.

**Test strategy:** run full suite once at end of Phase B (was 660 passed /
19 skipped with J-Browser unit tests green; live tests are opt-in).

## Phase C — JARVIS Orbit (standalone browser product)

JARVIS **Orbit** is the daily-driver browser whose intelligence layer is JARVIS
itself. Two halves, one contract:

- **Chromium owns browsing.** Unbranded Chromium (runtime resolved via
  `J_BROWSER_CHROMIUM_PATH` or `orbit.cdp._find_chromium()` — a Playwright
  build, never the user's installed Chrome profile) runs tabs, DOM, network,
  and hosts the MV3 extension surfaces (sidebar + new-tab home that talk to the
  DSH bridge at `127.0.0.1:8170`).
- **JARVIS owns agency.** The kernel (AgentLoop → ToolExecutionService → the
  `orbit.*` tool catalog) supplies all reasoning, planning, tool use, memory,
  verification, and security. Chromium is controlled only through the single
  browser facade: `BrowserController` → `CDPBackend` → CDP websocket.
  `chrome.debugger` is FORBIDDEN in the extension — the 501 `DEREAL` control
  duck test is the seam, not a control surface.

| Area | Where |
|------|-------|
| CDP transport | `orbit/cdp.py` (`CDPConnection` sync recv-while-wait under one RLock; `CDPBackend` implements `BrowserBackend`) |
| Tab registry | `orbit/registry.py` (stable `tab_id` ↔ CDP target_id; USER/AGENT/SYSTEM ownership via `core.locks.ResourceLock`) |
| Facade + tools | `orbit/controller.py` (`get_orbit_controller`), `orbit/tools.py` (`orbit.*` handlers, single ToolExecutionService boundary) |
| Vertical slice | `orbit/runtime.py` (`OrbitRuntime`, DSH-style commands; readback seam imports `orbit.tools.get_orbit_controller`) |
| Risk + consent | `tools/classification.py` `browser_risk_for_tool` (single source); `core/agent/permissions.py` sensitive-site gate, fail-closed |
| Sensitive sites | `security/sensitive_sites.py` (banking/webmail/account/cloud origins; host + subdomain match) |
| Network policy | `jbrowser.network.BrowserNetworkPolicy` — default-deny private/loopback/link-local before `goto` |
| Extension | `extensions/jbrowser/` (MV3, NO `chrome.debugger`; authenticated `BridgeClient` sends `Bearer` token) |
| Bridge | `jbrowser-bridge/server.py` (loopback-only, CORS chrome-extension, optional bearer auth; `/v1/agent` + `/v1/cdp` permanent 501) |

### Phase C invariants (extend the FREEEZE)

7. **One browser control path.** Every individual browser action passes through
   `BrowserController`, owned by `OrbitRuntime` and surfaced only as `orbit.*`
   tools through `ToolExecutionService`. Legacy `tools/browser.py` handlers
   route through the same facade.
8. **Ownership beats blocking.** Tab access is serialized by stable-id
   ownership: a contested tab yields the deterministic `RESOURCE_LOCKED`
   signal (structured ToolResult: `reason`, `owner`, `key`), never a
   silent wait or a raw throw.
9. **Consent is mode-independent.** Low/medium auto-approve per mode; high/
   critical AND navigation to a sensitive origin always require explicit
   operator approval. No consent channel wired = deny (fail closed).
10. **Declarative tool metadata.** Every tool carries `retry_semantics`
    (READ/IDEMPOTENT/CONDITIONALLY/NON) and `concurrency`
    (parallel/serialized) from the shared classification engine.

### Phase C gates

| Gate | What | Status |
|------|------|--------|
| G0 | subsystem audit + classification map | Done |
| G1 | bridge + ownership locks + DSH bridge hardening | Done |
| G2 | unbundled-Chromium runtime spike | Done |
| G3 | CDP subsystem (connection, registry, backend) | Done |
| G4 | vertical slice through ToolExecutionService | Done |
| G5 | browser tool hardening (retry, concurrency, consent, RESOURCE_LOCKED) | Done |
| G6 | extension rewrite (no chrome.debugger, auth'd bridge client, AGENTS.md) | Done |
| G7 | kernel integration (KernelBackend→ModelGateway, budgets, tab ownership, WAITING_BROWSER) | Done |
| G8 | end-to-end vertical slice (DSH→bridge→agent→tools→CDP) | Done |
| G9 | security + tests (sensitive sites, scan gate, audit) | Next |
| G10 | crash recovery (WAITING_BROWSER in `core/agent/state.py`) | Pending |
| G11 | import wizard (CSV password guidance only — no stored secrets) | Pending |
| G12 | selective memory (stable identity, constellation keyspace + ownership, BLOB mode) | Pending |
| G13 | E2E/perf (P50/P95/P99), packaging, first-run, docs, CI, final report | Pending |

Bridge extension client is **authenticated** (bearer token via
`chrome.storage` `jb:bridgeToken`); the bridge is fail-closed on state-changing
requests when `--auth` is set. Orbit unit tests are hermetic (fake transport);
live CDP tests are opt-in via `JARVIS_RUN_BROWSER_LIVE=1`.

## Research Pipeline

```text
Priority A:
├── OpenWork
├── Nanocoder
├── Rowboat
├── Freebuff / Codebuff
├── TUIOS
├── Terminal UI / OS projects
└── OpenObserve

Priority B:
├── Switchyard
├── Kronos
├── Council of High Intelligence
├── Mindwalk
└── OpenWork ecosystem
```

Research runs in parallel but cannot destabilize the active sprint.
See `jarvis-research-tags.md` for full analysis.

## Windows Notes

- cp1252 stdout. Always encode safely.
- `shell.execute` WinError 87 is known. Use `shell.cmd` with care.
- Canonical tool name is `shell.execute` (not `shell.cmd`).

## Code Style

- No comments unless asked.
- Prefer editing existing files.
- Check `package.json` / `pyproject.toml` before adding dependencies.
- Never commit secrets or keys.
