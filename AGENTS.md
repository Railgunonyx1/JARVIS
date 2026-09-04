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

Playwright is optional (lazy import); J-Browser tests mock the backend so the
suite passes without it (`pip install playwright` + `playwright install chromium`
to actually browse). Single-engine discipline holds: legacy `tools/browser.py`
handlers AND `external/browser_agent.py` both route through `get_controller()`
→ `PlaywrightBackend` (one Playwright process). `BrowserAgent` is retained as a
deprecated compatibility adapter. Everything flows through
`ToolExecutionService` (no bypass).

**Test strategy:** run full suite once at end of Phase B (was 613 passed / 14
skipped with J-Browser tests green).

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
