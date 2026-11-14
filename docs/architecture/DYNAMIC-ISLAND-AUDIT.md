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

## Cleanup principle

Preserve the AI execution and security substrate where the Dynamic Island backend depends on it. Remove unrelated product surfaces, not generic agent capabilities merely because they are not part of the Qt UI.

## Package-01 closure evidence — 2026-11-14

**Branch:** `pkg01-autostart-fix` — commits `3a892ae1d9528b213dfc7652da8b11792904adf1`, `c8589f695417278215af70a31c0c4a7bce90d3cc`, on top of `cff6d8b3`.
**Host:** local KDE/Wayland session, Python 3.14.9, PySide6 6.12.0, git 2.56.0. CI-equivalent runs used `QT_QPA_PLATFORM=offscreen` and `PYTHONPATH=dynamic-island:.`.

### Defects fixed on this branch

1. **KWin helper reported a path it never wrote** (`3a892ae1`). `kwriteconfig6 --file <relative>` resolves against `$XDG_CONFIG_HOME`/`$HOME/.config`, never `$PWD`, so the helper enabled the rule in a different file than the one it printed. The helper now resolves one absolute `kwinrc` and passes it to both `kwriteconfig6` and `kwriteconfig5`.
2. **KWin payload was replaced in place** (`c8589f69`). The installed script tree is now staged at `$DEST.new.$$` and moved into position, with the stage removed by an `EXIT HUP INT TERM` trap, so an interrupted install cannot leave a half-written script.
3. **Autostart registration failed on `dynamic-island-cleanup`** (pre-existing, blob `db5d3539`; fixed on this branch in `cff6d8b3`, blob `2868a375`). Running the wrapper's own entry point against the installed layout produced `ModuleNotFoundError: No module named 'app'` and exit status 1 for `enable`, `status` and `disable`: the wrapper imported `app` from the repository root instead of `dynamic-island/`, and never registered `--run`. `install.sh` runs under `set -euo pipefail` and calls the autostart step at line 73, *before* the KWin helper block at lines 78–84, so a failing autostart aborts the install before the KWin script is staged.

Verified by execution, not inspection: the same staged layout exits 1 with `ModuleNotFoundError` at `7160001b` and returns 0 with a correctly written `Exec=` entry at `cff6d8b3`.

### Installer lifecycle (redirected root, stubbed session)

`install.sh` and `uninstall.sh` were run against a temporary root (`INSTALL_DIR`, `BIN_DIR`, `DESKTOP_DIR`, `ICON_DIR`, `XDG_CONFIG_HOME`, `HOME`, `XDG_CURRENT_DESKTOP=KDE`) with `qdbus6` stubbed. The real configuration was not touched: `~/.config/kwinrc` remained `f7c3d86f…`, autostart files 0, and the pre-existing `~/.local/share/kwin/scripts/jarvis-island` untouched.

| Step | Result |
| --- | --- |
| `install.sh` | exit 0; autostart entry written with absolute `Exec=`; KWin script installed; `Enabled in: <root>/xdg/kwinrc`; `org.kde.KWin /KWin reconfigure` invoked (stubbed) |
| installed `jarvis-autostart status` | exit 0, `autostart enabled` |
| `uninstall.sh` | exit 0; autostart entry removed; KWin script removed; `INSTALL_DIR` deleted |
| residue | none, after `ac58db57`: `mimeinfo.cache` is removed only when it holds nothing but its header; foreign entries and the directory itself are always preserved |

The installer's own `pip install` could not reach PyPI from this host; the lifecycle run used a local wheelhouse (`PIP_NO_INDEX=1`, `PIP_FIND_LINKS=…`) built from the pip cache. This is an environment limitation, not an installer defect.

### Test results on this branch

| Check | Result |
| --- | --- |
| `ruff check . --select E9,F63,F7,F82` | pass |
| `python -m pytest tests/ -q` | 1054 passed, 2 failed, 10 skipped |
| `python -m pytest dynamic-island/tests/ -q` | 46 passed, 1 skipped |
| `python scripts/scan_secrets.py` | clean |

`dynamic-island/tests` is 46 because `test_kwin_rule_helper.py` (10 tests) and two uninstall-cache cases were added here; the 34 pre-existing cases are unchanged.

### Known baseline failure — not introduced here

`tests/desktop/test_island.py::test_island_constructs_idle` and `::test_island_constructs_idle_and_expands` fail with `assert island._card.width() >= 185` → `assert 183 >= 185`. The identical failure occurs at `cff6d8b3`, which does not contain `dynamic-island/tests/test_kwin_rule_helper.py`, so it is independent of this branch. It is a two-pixel layout assertion that does not hold under PySide6 6.12.0. Recorded as a known baseline failure; deliberately not fixed in this phase.

### Still unverified

- KDE runtime behaviour (real placement, focus handling, reconfigure against a live session) — requires per-operation approval and has not been performed.
- `kwriteconfig5` path — the binary is absent from this host; only `kwriteconfig6` was exercised.
- CI runs Python 3.11; this host runs 3.14.9. The interpreter gap is the likely cause of the layout failure above.

### KDE runtime check — read-only, live session

Session reports **KWin 6.8.2** (Plasma 6), so `kwriteconfig6` is the correct backend on this machine.

Observed state before the check, read-only:

- `~/.config/kwinrc` — `f7c3d86f…`, 2652 bytes, containing `[Plugins] jarvis-islandEnabled=false`.
- `~/.local/share/kwin/scripts/jarvis-island` — present.

So the existing live installation has the KWin script deployed but **disabled**: the island currently falls back to compositor placement. That is the observable symptom the wrong-`kwinrc` defect produces, and it is why the helper's "Enabled in:" line could be true while the rule was inactive.

The helper was then run against a *copy* of `kwinrc` (`KWINRC_PATH`, `KWIN_SCRIPT_DIR` redirected; `qdbus6` stubbed so no reconfigure reached the session):

| Action | Result |
| --- | --- |
| `--install` | exit 0; copy gained exactly one line, `jarvis-islandEnabled` `false` → `true`; payload staged as `contents/` + `metadata.json`; one `org.kde.KWin /KWin reconfigure` call, stubbed |
| `--uninstall` | exit 0; key back to `false`; script directory removed |
| real `kwinrc` | sha256 identical before and after — `f7c3d86f…` |

Not performed, by design: writing the real `kwinrc`, calling `reconfigure` against the live session, and observing island placement or focus. Those require per-operation approval and remain the only unverified items in Package-01.

### Decisions recorded with this evidence

- **Supported platform is Plasma 6.** `kwriteconfig6` is the verified backend (KWin 6.8.2). The `kwriteconfig5` path exists in the helper but is unexercised, because the binary is absent from every machine used so far. Plasma 5 is therefore **not** a claimed supported target until that backend is tested; dropping it from the matrix is equally acceptable.
- **Documentation structure.** This file and `docs/architecture/ARCHITECTURE.md` are canonical. No competing root-level `ARCHITECTURE.md`, `ROADMAP.md` or `DEVELOPMENT_LOG.md` is created: evidence belongs with the record it qualifies, and a separate development log is added only if the volume of history genuinely requires one.
- **Version drift.** CI runs Python 3.11 with an unpinned `PySide6>=6.8`; this host runs 3.14.9 with PySide6 6.12.0. That gap is the likely cause of the two baseline layout failures, and it means CI alone cannot establish desktop correctness.

### Intermittent Qt teardown abort (observed, not reproducible)

One `python -m pytest dynamic-island/tests/ -q` run terminated with signal 6 (`rc=134`, Python fatal abort after the extension modules `shiboken6`, `PySide6.QtCore/QtGui/QtWidgets/QtTest`, `numpy`, `psutil` were loaded) immediately after the main suite had finished. Four consecutive re-runs of the same command passed with `46 passed, 1 skipped`. It occurred on a documentation-only change, so the two events are unrelated, but a teardown-time abort on a headless Qt platform is exactly the kind of instability the reliable-startup/shutdown work must reproduce deliberately rather than inherit.


## Dynamic Island core phase — gesture shutdown audit (2026-11-14)

A read-only source audit found a gap in the camera/tracker shutdown contract:

- `HandTracker.stop()` waited up to five seconds but did not check whether the worker was still alive before logging that it had stopped.
- `Camera.stop()` waited up to three seconds but did not report whether the capture worker had actually exited.
- `AppCoordinator._stop_gestures()` stopped the tracker and camera but never called `camera.tracker_exit_confirmed()`, despite that being the documented release gate in both classes.
- The previous test named `test_coordinator_signals_camera_after_tracker_exit` manually called `camera.tracker_exit_confirmed()`; it did not invoke `AppCoordinator`. It therefore did not test the coordinator behaviour its name claimed to cover.
- `HandTracker._track_loop()` had a placeholder in its `finally` block where the comment said MediaPipe was closed, but no close call existed.

### Correction committed on `dynamic-island-core`

- `HandTracker.stop()` and `Camera.stop()` now return whether their respective worker has actually exited. Repeated stop calls still check/join an existing worker.
- MediaPipe is closed from the tracking worker's `finally` block, after its final processing call; startup-failure cleanup also closes an already-created instance.
- The coordinator now releases the camera only after both tracker and capture workers have exited. If a bounded join times out, a daemon cleanup watcher waits for actual termination before calling `tracker_exit_confirmed()`.
- `Camera.tracker_exit_confirmed()` rejects release while its capture worker is still alive.
- The coordinator test now exercises the real `AppCoordinator._stop_gestures()` path, and a delayed-worker test verifies that a timeout cannot cause early release.

This is source-level and CI-verifiable lifecycle work. It does not replace physical camera validation on the target laptop. A capture driver that blocks indefinitely may keep the cleanup watcher waiting; in that case the implementation deliberately prefers not to release a device still potentially in use.

### CI evidence

The initial core-phase run #278 (`43582819933`) terminated with a Qt/Python SIGBUS (exit 135) during the root test suite. It was not classified as a baseline assertion failure. The shutdown test was corrected to retain and join its worker thread, and the test disconnects the process-wide `QApplication.quit()` slot so it cannot terminate the pytest application's event loop.

The subsequent full CI run #280 passed:
- Safety lint: pass.
- Root suite: 1,058 passed, 9 skipped, 1 warning.
- Dynamic Island suite: 49 passed, 2 skipped.
- Secret scan: clean.

The latest full CI run #284, on commit `5ccd4c27c3ba5b928647a4b8ac50c36568ec32b0`, passed:
- Safety lint: pass.
- Root suite: 1,058 passed, 9 skipped, 1 warning.
- Dynamic Island suite: 53 passed, 2 skipped.
- Secret scan: clean.

The dynamic suite now includes tests for coordinator camera-release ordering, delayed worker shutdown, backend completion-signal semantics, GUI-thread workspace cleanup, settings-directory resolution and concurrent settings saves. The CI environment is Ubuntu, Python 3.11 and Qt offscreen. These runs verify source and automated tests, not live KWin placement, keyboard focus under Wayland, physical camera release or GPU performance.


## Settings persistence audit — 2026-11-14

A source audit found that `JARVIS_DESKTOP_HOME` had inconsistent semantics: it was assigned to the source-code directory in one constant, then used as a file path in another. `_ensure_dir()` created that source directory rather than the parent of the active settings file. On a fresh installation this could leave `~/.jarvis-desktop` absent and make saves fail; when the environment override was set to a directory, the code attempted to replace that directory as though it were a file.

The fix on `dynamic-island-core` establishes one contract:

- `JARVIS_DESKTOP_HOME` is a directory override.
- The settings file is always `SETTINGS_DIR / "settings.json"`.
- The directory created by `_ensure_dir()` is derived from `SETTINGS_FILE.parent`, so tests and callers that override the file path remain isolated.
- Atomic saves use unique same-directory temporary files, preventing concurrent saves from overwriting the same staging file.
- The existing default location `~/.jarvis-desktop/settings.json` is preserved for compatibility.

Regression tests cover the environment override, fresh default-directory creation and concurrent saves. CI run #284 passed these tests. The settings file path was not tested against the user's actual home directory; no local settings were read or modified.


## Desktop action portability audit — 2026-11-14

- Terminal launch no longer assumes `foot`; it prefers `konsole` in KDE sessions and otherwise searches supported installed terminal emulators.
- Browser launch uses Python's system-default browser integration and opens a blank tab rather than assuming Firefox.
- The `wmctrl` maximize/minimize invocations were using malformed argument sequences. They now use the documented `-b add,<state>` form and have regression tests.
- `wmctrl` remains an X11/XWayland mechanism. The current target is KDE Plasma Wayland, so native Wayland window actions remain an explicit integration gap. No unsupported claim of full Wayland window management is made. A KWin scripting backend is the candidate, but it requires a tested command bridge before implementation.

### Python compatibility CI

Workflow `.github/workflows/ci.yml` now runs the same gate on Python 3.11 and 3.14.

Run #289 passed on both:
- Python 3.11: 1,058 root tests passed, 9 skipped; 61 Dynamic Island tests passed, 2 skipped; lint and secret scan clean.
- Python 3.14: 1,058 root tests passed, 9 skipped; 61 Dynamic Island tests passed, 2 skipped; lint and secret scan clean.

This confirms test-suite compatibility on both Python versions in Ubuntu/Qt-offscreen CI. It does not establish identical performance or live desktop behaviour on the target laptop.


## Agent backend and conversation-panel reliability — 2026-11-14

The backend audit found and corrected the following defects:

- Blocking `queue.Queue.get()` inside the asyncio coroutine prevented idle-loop callbacks from running. The consumer now awaits `asyncio.to_thread(queue.get)`, allowing model changes and cancellation callbacks to execute while idle.
- A rejected message previously consumed a request ID. Queue insertion and ID commitment now occur under the same lock; a full queue leaves the counter unchanged.
- Task cancellation is scheduled only through the owning event loop. No fallback calls `Task.cancel()` from the caller thread.
- Shutdown requested during kernel construction is checked before the backend enters READY, and the partially created runtime is still closed.
- Worker startup is serialized with stop requests; stale state is cleared before restart, and a worker that has not terminated cannot be replaced.
- Runtime and event-loop references are published and cleared under the state lock.
- Model changes are applied on the agent loop. The synchronous API waits for completion and returns failure if scheduling or execution fails.
- Cancellation now covers both active tasks and queued request IDs. A queued cancellation emits a dedicated signal and the consumer skips that exact request.
- The conversation panel's Enter handler was connected twice and used an empty-string default that prevented Return from reading the input field. It now connects once and sends the field contents.
- The unused cancellation signal is wired to a stop-response button. The overlay tracks the active request ID and restores input after a final response or backend failure.

Regression tests were added for queue saturation, request cancellation, startup/shutdown races, loop creation failure, model selection, terminal/browser selection, window command syntax, Enter-to-send and cancellation controls. The latest complete CI result for these changes is pending; earlier Python 3.11/3.14 matrix results do not cover these later commits.
