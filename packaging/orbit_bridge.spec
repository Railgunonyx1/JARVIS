# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — JARVIS Orbit bridge daemon (G13 packaging).
#
# Build (Windows, from repo root, using the project venv):
#     python -m PyInstaller --noconfirm --clean packaging/orbit_bridge.spec
#
# Artifact: dist/JARVISOrbitBridge/JARVISOrbitBridge.exe — the loopback bridge
# (default 127.0.0.1:8170) that speaks DSH/HTTP to the MV3 extension. The
# Chromium runtime is NOT bundled here (locked decision: resolved at runtime
# via J_BROWSER_CHROMIUM_PATH / packaged resolver, never the user's Chrome);
# packaging/installer.iss installs the extension-loading launcher alongside.
#
# The kernel stack imports dynamically (provider routers, memory stores, tool
# registries), so hidden imports are collected from the module families the
# bridge reaches. Any change to those families must be re-verified at build
# time with a live smoke test (see packaging/BUILD.md).

from PyInstaller.utils.hooks import collect_submodules

hidden = []
for family in ("core", "providers", "memory", "tools", "security",
               "runtime", "orbit", "jbrowser", "jbrowser_bridge"):
    hidden += collect_submodules(family)

a = Analysis(
    ["../jbrowser-bridge/server.py"],
    pathex=[".."],
    binaries=[],
    datas=[
        # Profile/extension surfaces are resolved from the install layout,
        # never baked into the binary.
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "notebook", "IPython"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JARVISOrbitBridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="JARVISOrbitBridge",
)
