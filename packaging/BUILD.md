# JARVIS Orbit — packaging & installer (G13)

The installer is the **delivery layer**; it never drives runtime architecture
(locked decision). JARVIS Orbit ships as two cooperating halves:

| Half | What it is | Source |
|------|-----------|--------|
| **Bridge daemon** | The loopback DSH/HTTP bridge (default `127.0.0.1:8170`) with the full kernel (AgentLoop, tools, memory, security, Orbit tools) | `jbrowser-bridge/server.py` → PyInstaller |
| **Chromium + extension** | The browser itself; MV3 extension surfaces (sidebar, new-tab, first-run) | `extensions/jbrowser/` + a runtime-resolved unbranded Chromium |

Chromium is **never bundled from the user's Chrome** and never the user's
profile: it is resolved at runtime via `J_BROWSER_CHROMIUM_PATH` or a packaged
resolver (see `orbit/cdp.py` `_find_chromium()`).

## Build (Windows, build machine)

```powershell
# 1. Bridge binary
python -m PyInstaller --noconfirm --clean packaging\orbit_bridge.spec
#    -> dist\JARVISOrbitBridge\JARVISOrbitBridge.exe

# 2. (Optional) stage an unbranded Chromium build:
#    copy a chrome-win64 tree to dist\chromium\  (installer picks it up)

# 3. Installer (Inno Setup 6)
ISCC.exe packaging\installer.iss
#    -> dist\installer\JARVISOrbit-Setup.exe
```

## Verification gates (required before shipping a build)

1. `JARVISOrbitBridge.exe` answers `GET http://127.0.0.1:8170/status` with
   `{"ok": true, "kernel": "online"}`.
2. Launch the packaged Chromium with `--user-data-dir` pointing at the Orbit
   profile (`config/browser_profiles/orbit/`) and the installed extension
   loaded once via `chrome://extensions` → **Load unpacked** → `extension\jbrowser`.
3. Sidebar shows **JARVIS online**; a new-tab ask round-trips through the
   bridge to the kernel and back.
4. `python -m pytest tests -q --ignore=tests/test_orbit_live.py --ignore=tests/test_jbrowser_live.py`
   is green on the same tree the binary was built from.

## STOP conditions

- If PyInstaller cannot resolve the kernel's dynamic imports (hidden-import
  gaps surface as `ModuleNotFoundError` only at runtime), do **not** ship:
  add the missing family to `packaging/orbit_bridge.spec` hidden imports and
  re-run gates 1–3.
- If no unbranded Chromium can be resolved at install time, the installer
  still installs cleanly but the first-run flow must surface the "browser
  runtime not found" state instead of pretending to launch.
