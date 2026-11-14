# JARVIS Dynamic Island — repository audit and cleanup record

**Scope:** full product isolation on `dynamic-island-cleanup`, based on the `dynamic-island` branch.  
**Audit basis:** recursive Git tree and source/configuration inspection.  
**Execution:** source audit and cleanup were performed through the GitHub integration. The updated GitHub Actions workflow passed on Ubuntu; no local checkout or target KDE session was available, so KDE/Wayland and physical-device behaviour remain manual verification items.

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
3. **Voice:** CI covers the desktop voice fallback path. Verify capture-device selection, local/cloud STT, TTS playback and cancellation on actual audio hardware.
4. **Gestures:** CI verifies deterministic camera/tracker shutdown and idempotent stop behaviour. Install optional camera dependencies and verify actual camera access and shutdown on target hardware.
5. **3D workspace:** CI now exercises Qt Quick scene loading, visibility transitions, idempotent load, missing-scene handling and shutdown. Actual GPU/driver rendering and performance still require target-machine verification.
6. **AI backend:** run with no provider configured (island remains usable), then with each intended provider; verify approval, cancellation, tool execution and shutdown.
7. **CI:** [successful GitHub Actions run](https://github.com/Railgunonyx1/JARVIS/actions/runs/42799353096): Ruff passed; root suite 1,057 passed / 9 skipped; Dynamic Island suite 31 passed / 1 manual test skipped; secret scan clean.

## Dynamic Island Core review — 2026-11-14

### Current implementation verified from source

- `IslandWindow` is a frameless, translucent PySide6 `QWidget` with `WindowStaysOnTopHint`, `Tool` and `WA_ShowWithoutActivating`.
- The pill uses a 240 ms `QPropertyAnimation` with `OutCubic` easing for geometry transitions.
- Current dimensions are 180×36 (idle), 320×44 (hover compact), and 480×620 (expanded), before outer margins.
- The conversation panel is created lazily on expansion. The coordinator/backend is also started from the expansion path, after the morph has been initiated.
- The controller emits `view_changed` and returns an `IslandView` dataclass through a normal Python property. It does not currently expose a typed Qt `Property` API suitable for assuming direct QML binding.
- Expansion calls `setFocus()` on the conversation input. Source inspection alone does not establish that the top-level window is activated or receives keyboard focus correctly under KWin Wayland.
- Shutdown denies pending approvals, calls coordinator shutdown, and then exits the Qt application. Hiding the island intentionally does not terminate the runtime.

### Presentation architecture decision

**Keep the QWidget pill for the current core phase. Do not migrate production UI to QML yet.**

The repository has no measured evidence that QML would improve the target machine's frame pacing, idle resource use or input responsiveness. A QML migration would require an explicit QObject property/signal contract and a separate verification of top-level window behaviour. The existing Qt Quick 3D workspace is a different surface and is not evidence that QML is the better implementation for the pill.

If performance evidence justifies a prototype, compare three equivalent implementations: (A) current QWidget baseline, (B) QWidget with embedded QQuickWidget, and (C) dedicated QQuickWindow. Measure on the actual target laptop: startup-to-visible time, idle CPU, resident memory, frame-time consistency during expand/collapse, input latency, keyboard focus, and KWin placement. Record Qt version, rendering backend and GPU driver. Keep QWidget as the fallback. Do not infer hardware acceleration from the use of QML.

### Core scope and remaining gates

The approved core scope is startup/shutdown, top-centre placement, expand/collapse animation, and keyboard/pointer focus. Notifications, multi-monitor feature work, launcher, AI conversation-panel expansion, voice changes and dock remain deferred.

The existing source has basic pointer hover/click and focus-on-expand paths, but the following remain **unverified on a live KDE Plasma Wayland session**:

- Overlay visibility and top-centre placement after login and after a second launch.
- Whether KWin rules apply consistently to the actual installed window identity.
- Whether expansion can obtain keyboard focus under Wayland; typing, Tab traversal, Escape/collapse and focus restoration.
- Whether pointer hover, click and collapse timing remain reliable at the target display scale.
- Clean shutdown and restart without stale lock/IPC state.

The recorded Ubuntu workflow run 42799353096 has one completed successful job; all listed steps (dependency installation, safety lint, desktop/application tests and secret scan) succeeded. Its recorded test totals were 1,057 passed / 9 skipped in the root suite and 31 passed / 1 manual skip in the Dynamic Island suite. This is headless CI evidence, not live KDE/Wayland evidence. It is also a separate branch/test snapshot from Package-01's later test run; do not combine the totals.

No local benchmark or target-session result is claimed in this audit. The GitHub source connector cannot execute the application, run local pytest, inspect the user's working tree, or interact with the live desktop. Those checks require a local checkout/runtime.

## Cleanup principle

Preserve the AI execution and security substrate where the Dynamic Island backend depends on it. Remove unrelated product surfaces, not generic agent capabilities merely because they are not part of the Qt UI.
