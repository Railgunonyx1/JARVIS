# Repository structure

The repository has one product surface: JARVIS Dynamic Island for KDE Plasma 6. The AI runtime remains modular so the UI does not duplicate agent logic.

| Path | Responsibility |
|---|---|
| `dynamic-island/app/` | PySide6 overlay, conversation, desktop actions, voice, gestures and optional 3D workspace |
| `core/` | AgentLoop, context, permissions, verification and shared application services |
| `providers/` | Cloud/local model providers and routing |
| `memory/` | Persistent and vector memory |
| `tools/` | Agent tool registry and implementations |
| `runtime/` | Kernel composition, event bus, observability and telemetry |
| `security/` | Permission policy, redaction, sandbox and audit controls |
| `skills/` | Skill manifests and progressive instruction loading |
| `plugins/`, `packages/` | Provider, MCP and reusable integration packages |
| `config/` | Model, voice, security and execution-mode configuration |
| `packaging/desktop/` | KDE desktop entry, KWin helper, installer and uninstaller |
| `scripts/` | Island launch, autostart, setup and diagnostic utilities |
| `tests/desktop/` | Desktop integration and UI tests |
| `dynamic-island/tests/` | Focused Dynamic Island release and lifecycle tests |
| `docs/` | Architecture, UI, voice and operational documentation |

Orbit, J-Browser, Chromium/Electron, browser extensions and the legacy CLI/TUI are not part of this branch's product scope.
