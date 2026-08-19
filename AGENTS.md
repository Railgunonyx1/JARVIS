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

## Current Sprint: Phase A — Kernel Integration

| Sprint | What |
|--------|------|
| 20K | AgentLoop -> ToolExecutionService (single boundary) |
| 20L | VerificationEngine as post-execution gate |
| 20M | ACP/Codex route through ToolExecutionService |
| 20N | RECOVERING state + deterministic FailureClass |
| 20P | Unified pipeline tests + no-bypass architecture test |

**Test strategy:** Build all implementation first, run full test suite once at end of Phase A.

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
