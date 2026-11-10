# JARVIS Dynamic Island — repository audit and cleanup record

**Scope:** full product isolation on `dynamic-island-cleanup`, based on the `dynamic-island` branch.  
**Audit basis:** recursive Git tree and source/configuration inspection.  
**Execution limitation:** GitHub tree and file operations were available; no local checkout or target KDE session was available in this run. CI tests, packaging execution, and runtime behaviour are therefore not claimed as verified.

## Findings

The repository contained 1,367 tree entries (1,190 files) and several overlapping product generations. The active Dynamic Island implementation was already concentrated in `dynamic-island/app/`, while Orbit/J-Browser/Electron, CLI/TUI, browser extensions, F1 experiments, old audit output and a quarantined duplicate desktop implementation remained at the root.

The existing Dynamic Island has distinct UI, coordinator, backend, voice, gesture, desktop-action and 3D workspace modules. Its AI bridge uses the established AgentLoop rather than requiring a second agent implementation. The core AI runtime is distributed across `core/`, `providers/`, `runtime/`, `memory/`, `tools/`, `security/`, `plugins/` and `packages/`.

## Retained

- `dynamic-island/` — authoritative desktop application and its focused tests.
- `core/`, `providers/`, `runtime/`, `memory/`, `tools/`, `security/`, `config/` — agent execution, provider routing, memory, tools, policy and configuration.
- `plugins/`, `packages/`, `skills/` — provider/MCP integrations and agent capabilities. These are not UI surfaces; they remain because the assistant backend can depend on them.
- `packaging/desktop/` — KDE desktop entry, plasmoid, KWin placement helper and installer.
- `scripts/island-launcher.py`, `scripts/jarvis-autostart`, `scripts/scan_secrets.py` and relevant setup/voice/diagnostic utilities.
- General agent tests, desktop tests, performance harness and security checks.

## Removed from this product branch

- Orbit, J-Browser, Chromium/Electron shell, native browser prototype and browser extension trees.
- Browser bridge, browser-specific launchers and browser-specific CI/tests/docs.
- Old CLI/TUI application, F1 test-drive experiment and old full-window desktop launcher surface.
- Quarantined duplicate desktop implementation (the active implementation is under `dynamic-island/app/`).
- Historical audit dumps, browser research notes, obsolete packaging and generated screenshots/references unrelated to the current app.
- Archived skill manifests; active skill manifests and instruction sets remain.

Git history is preserved. This is a branch-level source-tree cleanup, not a history rewrite. No changes are made to `main`, `dynamic-island` or other historical branches.

## Configuration and CI changes

- Root project metadata now identifies the Dynamic Island rather than the former browser/engineering workspace.
- CI now runs Python quality checks, the retained application tests and secret scanning; Electron/browser jobs and stale CLI import checks are removed.
- Runtime dependencies are documented around the desktop app, providers, MCP, memory and push-to-talk audio.
- Wake-word configuration is explicitly disabled to match the button/push-to-talk interaction model.
- Packaging documentation describes the KDE Plasma 6 user-level installer.

## Findings requiring runtime verification

1. **KDE Wayland placement:** test KWin helper on the target Plasma version and multiple display layouts.
2. **Installer consistency:** execute install/uninstall on a clean user account; confirm launcher paths, autostart and permissions.
3. **Voice:** verify capture device selection, STT fallback, TTS playback and cancellation on actual audio hardware.
4. **Gestures:** install optional camera dependencies and verify explicit enable/disable and camera shutdown.
5. **3D workspace:** verify Qt Quick 3D module availability and failure isolation on the target GPU/driver.
6. **AI backend:** run with no provider configured (island remains usable), then with each intended provider; verify approval, cancellation, tool execution and shutdown.
7. **CI:** run the updated workflow. This audit did not execute the test suite.

## Cleanup principle

Preserve the AI execution and security substrate where the Dynamic Island backend depends on it. Remove unrelated product surfaces, not generic agent capabilities merely because they are not part of the Qt UI.
