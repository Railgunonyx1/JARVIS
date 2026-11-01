# JARVIS Dynamic Island

Minimal AI assistant for Bazzite Linux, built on the existing `Railgunonyx1/JARVIS`
agent core with a new PySide6 Dynamic Island overlay.

> Source-triage note: this overlay is not built by copying a FatihMakes desktop
> project. The useful parts of those repos were audited and either adapted into
> the existing JARVIS layers or explicitly left out. See `Source triage` below.

## Status

- [x] Dynamic Island UI — idle/pill overlay with compact conversation surface
- [x] Push-to-talk voice, streaming responses, inline approvals
- [x] Design tokens — dark palette from the DI-025 mockup
- [x] State machine — idle, compact, expanded; listening, thinking, speaking, approval, error
- [x] Approval lifecycle — request-scoped `ApprovalRecord`, single terminal transition, stale-decision rejection
- [x] Explicit-confirmation queue — approval-gated desktop actions route through `JarvisBackend` → `AppCoordinator` → `IslandWindow` → permission callback
- [x] KDE Wayland placement — KWin script pins the pill to the active output top-center
- [x] Packaging, launcher, desktop entry, autostart, and KWin script are aligned
- [ ] KDE Wayland runtime validation (Bazzite HDMI-A)

## Source triage — selected external references

The Dynamic Island overlay is not built by importing an entire FatihMakes desktop project. The useful parts from those repos were audited and either adapted to fit the existing JARVIS layers or explicitly left out.

The strongest conceptual matches in those repos are:

- **Mark-LVI** — best source for provider/tool/undo/confirmation *concepts*.
  Used here as design reference for verified outcomes, explicit consent, and
  provider/tool discipline. Not copied as a second agent loop.
- **Mark-XXXIX-OR** — comparison baseline for older/simpler implementations.
  Kept as a reference only where it offers something the newer repo does not.
- **Mark-X.1 / Mark-X / AI-Assistant-for-Computer** — lower priority.
  Useful for interaction-pattern lookup and simpler local implementations, but
  their broader desktop GUI feature sets are not what this overlay needs.


| Capability | Source repo | Decision | Where it lives now |
|---|---|---|---|
| Verified tool outcome classification | Mark-LVI `actions/` | **Adapt concepts, not the loop.** Reused the verified/unverified/to-block classification intent and JSON outcome contract; implemented on top of `ToolExecutionService` + `core/agent/verification.py` | `core/agent/tool_service.py`, `core/agent/verification.py` |
| Explicit confirmation for sensitive actions | Mark-LVI `undo.py`, `confirm.py` | **Adapt the gateway shape.** Adopted request-scoped approval + single terminal transition; kept the existing `PermissionEngine`/`mode_manager` as the authority | `dynamic-island/app/ui/overlay_window.py:ApprovalRecord`, `dynamic-island/app/integration/coordinator.py` |
| Interchangeable model providers | Mark-LVI `providers/` | **Keep the existing gateway.** JARVIS already has `providers/router.py` + `providers/types.py`; Mark-LVI's provider plumbing is informative only | `providers/router.py`, `providers/types.py` |
| Lazy-loaded, self-describing tools | Mark-LVI `actions/` / `tools/` concepts | **Keep JARVIS registry.** JARVIS already owns `tools.registry` + `tools.schema` + the tool catalog; Mark-LVI highlighted lazy/registry discipline worth keeping in mind | `tools/registry.py`, `tools/schema.py` |
| Memory retrieval on demand | Mark-LVI memory layer concept | **Keep existing memory.** Reuse the existing `memory/` subsystem; do not import a second competing memory path | `memory/` |
| Avatar / dashboard / full desktop GUI | Mark-X / Mark-X.1 / AI-Assistant-for-Computer | **Leave out.** Not needed for the minimal overlay; would duplicate or bloat the current UI architecture | Not added |

Notes:
- Mark-LVI self-identifies as Creative Commons BY-NC 4.0 and Mark-X.1 states personal/educational/non-commercial use. The repo-level feature lists above are used as *design references*, not copied source.
- The dynamic-island overlay reuses the existing JARVIS agent core (`core/`, `providers/`, `runtime/`, `memory/`) unchanged; the desktop layer is the new surface.
- Licensing caveat is per-repository and per-file, not per-feature. If any code is later reused more directly than a concept, re-check the actual license and file-level notices before copying.

## Design system

Palette (from the DI-025 mockup):

| Token | Hex   | Usage            |
|-------|-------|------------------|
| primary   | `#141619` | island background   |
| accent    | `#8C96A3` | idle dot, hover, active button   |
| text      | `#EBEEF2` | primary content   |
| muted     | `#B0B7C1` | secondary captions, dividers   |
| divider   | `#3A3A3C` | borders and separators   |
| input bg  | `#2C1C2E` | text field background   |
| input fg  | `#FFFFFF` | text field content   |
| blue      | `#0A84FF` | send button, listening indicator   |
| blue hover| `#0071E3` | send button hover, listening hover   |
| amber     | `#FFD60A` | approval prompts   |

## Quick start

```bash
cd dynamic-island
python3 app/main.py
```

Requires: Python 3.11+, PySide6, and the parent JARVIS repo on `PYTHONPATH`.

Note: `app/main.py` is the Dynamic Island app entry point as described by
this README. The native desktop packaging uses `scripts/island-launcher.py`
and the `jarvis-desktop-island` launcher instead, which resolves the same
entry point from the installed layout.

## Structure

```
app/
  main.py                  # Entry point (launches the island)
  ui/overlay_window.py     # Dynamic Island overlay (idle -> expanded)
  ui/conversation_panel.py # Compact conversation panel (expanded state)
  ui/island_controller.py  # UI state controller
  integration/jarvis_backend.py  # AgentLoop ↔ Qt bridge
  integration/coordinator.py     # UI ↔ agent coordinator + approval routing
  voice/                   # STT/TTS (Phase 3)
  gestures/                # Camera + tracking (Phase 4)
  desktop/                 # Action layer (Phase 5)
  workspace3d/             # Qt Quick 3D (Phase 6)
  config/                  # Settings
  diagnostics/             # Perf monitoring
  paths.py                 # Path helpers (launcher-aware)
  settings.py              # Persistence settings model
  autostart.py             # freedesktop autostart control
tests/
assets/
packaging/
```

## Interface states

- **idle** — 180×36 pill, centred in the upper third, shadow + amber dot.
- **compact** — 320×44 pill (hover). Only the dot animates.
- **expanded** — full conversation surface: transcript, inline approval row, push-to-talk input row.

The island is the sole user-facing interface. No separate desktop chat window
remains.

## Verification

`python -m pytest dynamic-island/tests/desktop/ -q` → targeted desktop tests.

Full desktop reconciliation (hermetic Qt, offscreen):

```bash
QT_QPA_PLATFORM=offscreen python -m pytest \
  dynamic-island/tests/desktop/ \
  tests/desktop/ \
  -q --import-mode=importlib -W error::DeprecationWarning
```

