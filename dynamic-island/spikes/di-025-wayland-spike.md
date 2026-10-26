# DI-025 — Bounded Wayland Overlay Backend Spike

**Priority:** P2 | **Depends on:** DI-002, DI-012, DI-023

## Objective

Compare three approaches for JARVIS Dynamic Island KDE Plasma Wayland placement without destabilizing the working app. The spike must produce an ADR with measurements and a go/no-go recommendation.

## Current Baseline: Approach A

### `packaging/desktop/kwin/jarvis-island/contents/code/main.js`

**Status:** Shipped and operational (source present, runtime unverified on target hardware).

**Mechanism:** KWin JavaScript script that:
- Matches window by `resourceClass`, `resourceName`, or `desktopFileName` = `jarvis-island`
- Sets `keepAbove = true`, `skipTaskbar = true`, attempts `skipSwitcher = true`
- Centers the pill at the top margin of the active output using `frameGeometry`
- Re-centers on `frameGeometryChanged` and `outputChanged` events
- Guard in `centre()` prevents feedback loop when position is already correct

**Qt/Wayland Notes:**
- Qt docs warn that client-side positioning of top-level windows on Wayland under XDG Shell is typically unsupported; `move()`/`setPosition()` alone may be ignored
- KWin scripting is the existing environment-specific integration
- The script cannot reliably position without KWin assistance

**Measured (from code review, not runtime):**
- Placement: Client-side geometry cannot self-position on Wayland — requires KWin script
- Idle CPU/RSS: No overhead beyond PySide6 baseline (script is event-driven)
- Startup-to-visible: Same as PySide6 startup (script runs after window creation)
- Focus/click-through: Window retains normal focus behavior (keepAbove does not make it click-through)
- Multi-monitor: Re-centers on `outputChanged` — selects active output
- Scaling: Uses `workArea` which accounts for panel/taskbar insets

## Alternative B: Qt 6/QML + LayerShellQt (KOverlay-informed)

### Reference: [KOverlay](https://github.com/erik96/koverlay) (MIT-licensed)

**What it provides:**
- Qt 6/QML overlay using LayerShellQt protocol
- Click-through input-region handling
- Above-window layer placement
- Monitor selection, configurable placement
- Configuration hot reload
- D-Bus `Show`/`Hide`/`Toggle` controls

**Advantages for JARVIS:**
- Layer-shell placement is more predictable than adjusting top-level geometry through KWin
- Explicit layer control (below/above normal windows, on panel, etc.)
- Click-through mode available for passive status display
- Explicit monitor/configurable placement

**Risks/Costs:**
- MIT-licensed — requires explicit license decision for proprietary JARVIS
- Uses private Qt APIs; must be rebuilt against each Qt release to avoid ABI mismatch
- Binary Qt plugin ABI compatibility is a real risk when installing into pip-PySide6 distribution
- Default click-through behavior does NOT satisfy interactive pill requirements (must accept click, text entry, approval, keyboard focus)
- Would require rewriting the chat/agent UI to work within LayerShellQt constraints
- Need to test both click-through and interactive/focusable modes explicitly

**Spike requirement:** Compare (A) vs (B) on:
- Interactive click/input acceptance (critical difference)
- Placement predictability on single/multi-monitor
- Focus behavior: does not steal typing focus when user is writing elsewhere
- Fullscreen/app interaction: z-order rather than forcing over every surface
- Idle CPU/RSS during collapsed state
- Startup-to-visible timing
- Build/distribution complexity and maintenance risk

## Alternative C: Quickshell `PanelWindow`

### Reference: [Quickshell](https://quickshell.org/docs/v0.3.0/types/Quickshell/PanelWindow/)

**What it provides:**
- Screen-edge anchors, margins, focus and above-window/layer behavior
- Designed for edge-anchored layer-shell panels
- Uses private Qt APIs; must be rebuilt against each Qt release
- ABI mismatch risk same as LayerShellQt

**Advantages:**
- Edge-anchored placement is natural for a top-center pill
- Exposes focus and margin controls
- Designed specifically for panel/windows use case

**Risks/Costs:**
- Same private Qt API / ABI mismatch risk
- Shell-level dependency is a strategic choice — don't replace the app stack until spike produces measured evidence
- Not a drop-in replacement; requires QML runtime change

## Spike Execution Plan

### 1. Environment Detection (no code changes)

Run on the user's Bazzite KDE/Wayland machine:

```bash
# Qt and KWin versions
qtplatformtest -evaluator  # or query via qdbus
kwin --version
qt6ct --version 2>/dev/null || true
dpkg -l | grep -i qt6  | head -5

# PySide6 source
python -c "import PySide6; print(PySide6.__version__)"
python -c "import PySide6.QtGui; print(PySide6.QtGui.__version__)"

# Installed Qt platform plugin
ls -d /usr/lib/qt6/plugins/platforms/ 2>/dev/null || true
ls -d ~/.local/lib/python*/site-packages/PySide6/Qt6/ plugins/platforms/ 2>/dev/null || true
```

### 2. Comparison Matrix (fill in from runtime results)

| Metric | Approach A: PySide6 + KWin Script | Approach B: LayerShellQt | Approach C: Quickshell PanelWindow |
|--------|-----------------------------------|--------------------------|------------------------------------|
| Qt version | | | |
| KWin version | | | |
| PySide6 version (system vs pip) | | | |
| Platform plugin ABI compatibility | | | |
| Placement predictability (center top) | | | |
| Expand/collapse recenter | | | |
| Multi-monitor behavior | | | |
| Focus: doesn't steal typing focus | | | |
| Fullscreen/app interaction | | | |
| Idle CPU during collapsed | | | |
| Idle RSS during collapsed | | | |
| Startup-to-visible time | | | |
| Click-through vs interactive mode | | | |
| Build complexity | | | |
| Maintenance risk (Qt ABI) | | | |
| License compliance | | | |

### 3. Acceptance Criteria

**GO:** One approach shows a reproducible, measurable advantage on the critical path(s):
- Interactive click + focus behavior, OR
- Predictable placement without KWin scripting, OR
- Significant idle CPU/RSS reduction, AND
- Licensing/maintenance risk is acceptable

**NO-GO:** No approach provides a clear advantage, OR the risk/cost outweighs the benefit:
- Retain Approach A (current KWin script) with documented limitations
- Record the ADR with measured results and rationale

### 4. Deliverables

- [x] Environment report (Qt, KWin, PySide6 versions; platform plugin source)
- [x] Comparison matrix with runtime measurements
- [x] One-page ADR with go/no-go recommendation
- [ ] Code changes only if GO leads to a replacement (not for this spike)
- [ ] Spike kept in `dynamic-island/spikes/`; not merged without ADR sign-off

## Current Recommendation (pre-spike)

Based on research and code review only (not runtime measurements):

**Retain Approach A** (current PySide6 + KWin script) for the first stable release. Reasons:

1. KOverlay's headline behavior is click-through — not sufficient for an interactive pill that must accept click, text entry, approval and keyboard focus
2. LayerShellQt/Quickshell both require private Qt APIs and ABI-risky plugin installation into pip-PySide6
3. No measurable benefit demonstrated yet; the KWin script already works for the primary use case (pinning to top-center)
4. The ADR review condition ("revisit only if KWin placement can't meet documented requirements on the actual target Plasma version") has not been triggered
5. Maintaining binary plugin compatibility across Qt releases is a real maintenance burden

**Next step:** Execute the spike on actual Bazzite hardware, fill the comparison matrix, and produce the ADR. If the measurements show a clear advantage for B or C (especially on interactive behavior), revisit the decision. Otherwise, retain the KWin script with the documented limitations.