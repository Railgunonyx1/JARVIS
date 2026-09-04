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
