# KDE Wayland Runtime Validation — Report Skeleton

Checkpoint

`d6575c2d1e232f00f716eb5045bebb47d12ae0ac`

Current workspace status

- `git rev-parse HEAD`: `d6575c2d1e232f00f716eb5045bebb47d12ae0ac`
- `git status --short`: `?? tmp/`
- Packaging desktop files present on disk and committed:
  - `packaging/desktop/README.md`
  - `packaging/desktop/install.sh`
  - `packaging/desktop/install-kwin-rule.sh`
  - `packaging/desktop/JARVIS-Island.desktop`
  - `packaging/desktop/JARVIS.desktop`
  - `packaging/desktop/kwin/jarvis-island/metadata.json`
  - `packaging/desktop/kwin/jarvis-island/contents/code/main.js`
  - `packaging/desktop/com.jarvis.desktop.appdata.xml`
  - `packaging/desktop/com.jarvis.desktop.flatpak.json`
- Offscreen Qt test results are recorded separately below and do **not** count as a Wayland runtime pass.
- Runtime gate status: **NOT RUN / UNVERIFIED**

---

## 1. Environment snapshot

Record the exact target environment before testing. Run this from the KDE Plasma Wayland session, not from a remote or terminal-only context.

```bash
set -euo pipefail

{
  echo "=== Git checkpoint ==="
  git -C /path/to/repo rev-parse HEAD
  git -C /path/to/repo status --short

  echo "=== Desktop session ==="
  printf 'Session: %s\n' "${XDG_SESSION_TYPE:-unknown}"
  printf 'Desktop: %s\n' "${XDG_CURRENT_DESKTOP:-unknown}"
  printf 'Wayland display: %s\n' "${WAYLAND_DISPLAY:-unset}"

  echo "=== Versions ==="
  python3 --version
  python3 -c 'import PySide6; print("PySide6", PySide6.__version__)' 2>/dev/null || true
  kwin --version 2>/dev/null || true
  plasmashell --version 2>/dev/null || true
  printf 'Kernel: %s\n' "$(uname -r)"

  echo "=== Display ==="
  echo "Screens: $(qdbus org.kde.KWin /org/kde/kwin/Screens count 2>/dev/null || echo unknown)"
  echo "Primary: $(qdbus org.kde.KWin /org/kde/kwin/ScreenMappingManager primaryScreen 2>/dev/null || echo unknown)"
} > wayland-env-$(date +%Y%m%d-%H%M%S).txt
```

Capture the output alongside the report. Do not treat "looks right in a screenshot" as an environment record.

---

## 2. Packaging contract

### 2.1 Application identity

| File | Identifier claimed | Verification |
|------|-------------------|--------------|
| `packaging/desktop/JARVIS-Island.desktop` | `Name=JARVIS Island`, `Exec=jarvis-desktop-island`, `Icon=jarvis-desktop` | Confirm file exists in `applications/`, `Exec` resolves to a real launcher, and icon name is resolvable. |
| `packaging/desktop/JARVIS.desktop` | companion desktop entry | Confirm if a separate companion launcher is still intended. |
| `packaging/desktop/kwin/jarvis-island/metadata.json` | `KPlugin.Id = jarvis-island`, `KPlugin.Name = JARVIS Island` | Confirm the KWin script id matches the desktop file app id logic used by the compositor. |
| `packaging/desktop/com.jarvis.desktop.appdata.xml` | freedesktop appdata | Confirm if shipping appdata is intended for this product. |
| `packaging/desktop/com.jarvis.desktop.flatpak.json` | Flatpak manifest | Confirm whether Flatpak is part of the supported delivery path. |

### 2.2 Installer contract

Source: `packaging/desktop/install.sh`

What the installer is documented to do:

1. Create an isolated Python venv at `$INSTALL_DIR/venv`.
2. Install pinned runtime dependencies into the venv, including `PySide6==6.8.1`.
3. Stage a filtered copy of the repo into `$INSTALL_DIR/jarvis-repo`, excluding `.git`, `.env`, caches, `packaging`, `scripts`, desktop files, and build artifacts.
4. Install launchers:
   - `jarvis-desktop`
   - `jarvis-desktop-island`
   - `jarvis-island`
5. Bake the install root into the launcher shebangs and fallback paths.
6. Enable autostart by default via `jarvis-autostart enable`.
7. Install desktop entries into `$DESKTOP_DIR`.
8. Optionally install the KWin placement script via `install-kwin-rule.sh`.

Validation checklist before the runtime gate:

- [ ] The launcher shebangs point at the installed venv Python, not a system or development interpreter.
- [ ] `jarvis-desktop-island` exists and is executable after install.
- [ ] The desktop entries exist and `Exec=` points at an installed command, not a relative path.
- [ ] Autostart entry `jarvis-desktop.desktop` exists in `$XDG_CONFIG_HOME/autostart/` if installation enabled it.
- [ ] The KWin script is installed only for KDE/Wayland sessions and is not forced on unsupported environments.

### 2.3 KWin placement script contract

Source: `packaging/desktop/kwin/jarvis-island/metadata.json` and `packaging/desktop/kwin/jarvis-island/contents/code/main.js`

The documentation indicates the compositor script:

- identifies the island window by `resourceClass`, `resourceName`, or `desktopFileName` equal to `jarvis-island`;
- sets `keepAbove = true`, `skipTaskbar = true`, and attempts `skipSwitcher = true`;
- centers the window at the top of the active output using `frameGeometry`;
- re-centers on `frameGeometryChanged` and output changes;
- includes a guard to avoid a position-correction feedback loop.

Validation checklist before the runtime gate:

- [ ] The script id matches how the island declares itself to the compositor.
- [ ] The script is active in the test session.
- [ ] The island is recognized by the compositor by the expected identifier.

---

## 3. Runtime gate

Run this on the real KDE Wayland desktop after installation, using the installed launcher when possible. Prefer the installed layout over a development `PYTHONPATH` run, because the two layouts can differ in autostart, paths, and KWin integration.

If a test cannot be run, mark it **blocked** and record why. Do not mark an untested behavior as passed.

### 3.1 Startup and lifecycle

| Test ID | Steps | Pass criteria | Evidence |
|--------|-------|---------------|----------|
| R-01 clean launch | Launch `jarvis-desktop-island` from the installed environment. | Starts without an unhandled exception; main window appears. | Log excerpt, exit status, screenshot. |
| R-02 single-instance behavior | Launch a second instance while the first is running. | Second instance does not open a duplicate window; existing window is raised or a sensible message is emitted. | Steps, observed window count, logs. |
| R-03 autostart state | Check whether login autostart was registered by install or by the app. | Autostart entry exists only when intended; disabling it removes the entry. | File path, contents of the autostart entry. |
| R-04 repeated open/close | Launch and quit the island multiple times in sequence. | No stale windows, orphan lock files, or stuck processes remain. | Process list, lock file state, logs. |

### 3.2 Placement and stacking

| Test ID | Steps | Pass criteria | Evidence |
|--------|-------|---------------|----------|
| R-05 initial placement | Note where the idle pill appears immediately after launch. | Island appears in the intended top-center region on the intended output. | Screenshot plus screen geometry. |
| R-06 keep-above behavior | Open a normal application window and observe the island. | Island remains above the intended windows under the documented conditions. | Reproducible sequence, z-order observation. |
| R-07 compositor recognition | Confirm the KWin script sees the island window. | Compositor applies the documented keep-above/centering behavior. | Script activation evidence, placement result. |

### 3.3 Interaction and focus

| Test ID | Steps | Pass criteria | Evidence |
|--------|-------|---------------|----------|
| R-08 idle interaction | Hover/click the idle pill as designed. | Idle -> compact/expanded transitions work without clipping or misplaced content. | Before/after screenshots, observed state. |
| R-09 input handling | Use buttons, text input, and any push-to-talk control. | Interactive regions respond; noninteractive regions behave as designed. | Steps, affected region, logs if any. |
| R-10 focus behavior | Type into the island input, then switch to another application and back. | Text entry works; the island does not steal typing focus when it should not. | Exact sequence, observed focus owner. |
| R-11 click-through intent | Verify whatever click-through behavior the product intends for passive states. | Passive regions behave as intended; interactive regions remain interactive. | Steps and intended behavior. |

### 3.4 Display changes

| Test ID | Steps | Pass criteria | Evidence |
|--------|-------|---------------|----------|
| R-12 monitor change | Add, remove, or switch active output where safe. | Placement and geometry recover correctly afterward. | Display configuration, before/after geometry. |
| R-13 scaling change | Change fractional scaling or resolution where safe. | Layout remains usable; pill does not collapse or misplace in an unsupported way. | Config change, screenshot, observed geometry. |

Only test display changes with a safe recovery path available.

### 3.5 Regression

| Test ID | Steps | Pass criteria | Evidence |
|--------|-------|---------------|----------|
| R-14 ordinary desktop interaction | Use normal shortcuts, window management, and other desktop apps during the session. | Core desktop behavior remains functional while the island is running. | Failed interaction and logs if any. |

---

## 4. Decision rule

Runtime gate **passed**:

- every required test above is run on the supported KDE Plasma/Wayland environment,
- each required test meets its pass criteria,
- the application logs contain no unexplained critical error for the tested paths,
- the report records the exact tested commit and environment.

Runtime gate **failed**:

- a required behavior fails reproducibly, or
- the application crashes, hangs, or violates its input/stacking/focus contract.

Runtime gate **incomplete**:

- a required test was not run,
- the environment was unsupported or ambiguous,
- evidence is missing for a required behavior.

A documented failure is useful engineering evidence. It is not a pass.

---

## 5. Offscreen automated results — separate section

These results establish that the committed test suite passed in headless mode. They do not validate KDE Wayland placement, focus, click routing, monitor changes, or compositor behavior.

Run recorded

```bash
cd /home/Railgunonyx/Desktop/JARVIS
rm -rf dynamic-island/__pycache__ dynamic-island/tests/__pycache__ dynamic-island/app/__pycache__ dynamic-island/app/ui/__pycache__ dynamic-island/app/integration/__pycache__ dynamic-island/app/desktop/__pycache__ tests/__pycache__ tests/desktop/__pycache__ core/__pycache__ core/agent/__pycache__ packaging/__pycache__ tmp/__pycache__
QT_QPA_PLATFORM=offscreen python -m pytest tests/desktop/ dynamic-island/tests/desktop/ -q --import-mode=importlib
```

Result

- 123 passed
- 4 skipped
- 1 warning
- exit code 0

Warning

```
core/agent/tools.py:123:
  DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated
  for removal in Python 3.16; use inspect.iscoroutinefunction() instead
```

Skipped tests

- `tests/desktop/test_backend_smoke.py:78` — No LLM API keys configured
- `tests/desktop/test_desktop_foundation.py:25` — Separate desktop chat window removed; island is sole UI
- `tests/desktop/test_desktop_foundation.py:45` — Separate desktop chat window removed; backend test moved to island UI
- `tests/desktop/test_desktop_foundation.py:89` — Separate desktop chat window removed; e2e moved to island UI

Note

The warning is in the shared agent runtime, not in the Dynamic Island test files. It is a hygiene item, not a failing assertion.

---

## 6. Unresolved items to carry into the next audit

1. Runtime gate not executed. The offscreen suite is passing, but KDE Wayland placement, focus, input, monitor handling, and the KWin script integration are still unverified in this session.
2. KWin script runtime effect not independently confirmed here. The script exists and is documented, but this report does not assert that the compositor applied it during a live session.
3. Packaging tree is committed and present on disk, but installation was not performed in this session. The install contract is reviewed, not exercised.
4. Duplicate test tree still exists. `tests/desktop/test_island.py` and `dynamic-island/tests/desktop/test_island.py` remain separate. Do not remove either one without comparing unique coverage and import assumptions first.
5. Warning hygiene. The `asyncio.iscoroutinefunction` deprecation in the agent tool layer should be updated to `inspect.iscoroutinefunction()` before the next Python release removes it.

---

## 7. Minimum evidence to attach before claiming the runtime gate passed

For every required test that passes, attach:

- test ID,
- exact steps,
- expected and actual behavior,
- pass/fail/blocked status,
- screenshot or log excerpt if useful,
- tested commit SHA,
- environment snapshot.

For any failure or blocked test, attach:

- the observed failure,
- the exact environment,
- a reproducible reproduction step if available,
- an issue identifier if one is created.

---

Report status: **skeleton with committed evidence attached; runtime gate not executed.**
