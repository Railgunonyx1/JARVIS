# Project Structure

Top-level layout of the JARVIS MK-X repository.

## Python packages (importable)

| Directory | Package | Purpose |
| :--- | :--- | :--- |
| `cli/` | — | Terminal UI, telemetry cockpit, slash commands |
| `core/agent/` | — | Agent loop, tool service, permissions, verification, state machine |
| `core/` | — | Config, decision logger, event store, API keys, health |
| `memory/` | — | SQLite + sqlite-vec constellation memory |
| `providers/` | — | Multi-LLM provider engine (Groq, Gemini, Ollama, OpenRouter) |
| `runtime/` | — | Event bus, protocol adapters (MCP / ACP / Codex) |
| `tools/` | — | Declarative tool registry (~76 tools) |
| `security/` | — | Secret redaction, sensitive-site filters, sandbox |
| `skills/` | — | Skill registry and manifests |
| `orbit/` | — | Chromium browser subsystem (CDP, tab registry, controller) |
| `benchmark/` | — | Performance benchmarks and timing gates |
| `optimizer/` | — | System prompt optimization and eval harness |

## Application folders (not importable — hyphenated names)

| Directory | Purpose |
| :--- | :--- |
| `jarvis-desktop/` | Desktop companion app (PySide6) |
| `dynamic-island/` | Dynamic Island overlay variant (PySide6) |
| `orbit-browser/` | Electron browser shell |
| `jbrowser-bridge/` | Loopback-only HTTP bridge for the extension |
| `extensions/` | MV3 browser extension |

## Packages (installable Python packages)

| Directory | Package | Purpose |
| :--- | :--- | :--- |
| `packages/jarvis-core/` | `jarvis_core` | Agent kernel and state machine |
| `packages/jarvis-mcp/` | `jarvis_mcp` | MCP protocol adapter |
| `packages/jarvis-memory/` | `jarvis_memory` | Constellation memory store |
| `packages/jarvis-models/` | `jarvis_models` | LLM response dataclasses |
| `packages/jarvis-routing/` | `jarvis_routing` | Multi-provider fallback router |
| `packages/jarvis-tools/` | `jarvis_tools` | Tool registry and implementations |
| `packages/jarvis-ui/` | `jarvis_ui` | Terminal UI rendering |
| `packages/jarvis-verification/` | `jarvis_verification` | Verification gate and recovery |

## Support directories

| Directory | Purpose |
| :--- | :--- |
| `scripts/` | Dev/ops scripts, launchers, benchmarks |
| `tests/` | Test suite |
| `docs/` | Operations docs, perf ledger, setup guides |
| `audits/` | Historical audit reports |
| `config/` | TOML configuration (models, voice, app) |
| `assets/` | Banner, icons, fonts |
| `models/` | Ollama Modelfiles for custom lanes |
| `plugins/` | DSH plugin and other integrations |
| `claude-code-tools/` | External tooling (not part of JARVIS core) |
| `_quarantine/` | Legacy code kept for reference, not imported |

## Naming convention

- **snake_case directories** (`core`, `providers`, `tools`) are Python packages — importable as modules.
- **hyphenated directories** (`jarvis-desktop`, `orbit-browser`) are application folders — never imported as Python modules. They are launched as standalone processes.
- The exception is `packages/*/` which contains installable packages with underscore names (`jarvis_core`, `jarvis_routing`, etc.).
