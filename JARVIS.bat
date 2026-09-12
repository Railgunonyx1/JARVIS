@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title JARVIS Orbit

REM ── JARVIS Orbit — Main Launcher ─────────────────────────────────
REM Canonical entrypoint for the JARVIS Orbit browser
REM (orbit-browser\start.bat delegates back to this file).
REM
REM 1. Reuses / starts the JARVIS kernel backend (port 8170)
REM 2. Reuses / starts the WebSocket bridge        (port 8171)
REM 3. Launches the browser DETACHED and closes this console
REM    immediately. Nothing but the browser keeps running.
REM
REM Idempotent and console-close safe: services spawn via PowerShell
REM Start-Process (own hidden process, NOT console-attached), so they
REM keep running after this console closes. Re-running the launcher
REM reuses what is already listening (no duplicate spawns), and the
REM browser's single-instance lock focuses the existing window.

cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

REM ── Resolve Python (repo venv first, then system) ───────────────
set "PY="
if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
if not defined PY if exist "%~dp0orbit-browser\venv\Scripts\python.exe" set "PY=%~dp0orbit-browser\venv\Scripts\python.exe"
if not defined PY set "PY=python"

echo.
echo   [..] ORBIT - Starting JARVIS Browser...
echo.

REM ── Port liveness via netstat (no powershell spawn per poll) ──
REM Usage: call :PORT_LIVE <port> => ERRORLEVEL 0=up 1=down
goto MAIN

:PORT_LIVE
netstat -ano 2>nul | findstr /R ":%1 " | findstr /C:"LISTENING" >nul 2>&1
exit /b %errorlevel%

:MAIN

REM ── 0. Background Electron deps (overlaps service boot) ───────────
REM If Electron is missing, npm install starts detached NOW so it runs
REM while the kernel and bridge boot underneath, instead of serially
REM after them. Section 4 waits on it (with a ceiling) and falls back
REM to a synchronous install so failures stay loud.
set "NPM_INSTALLING=0"
if not exist "%~dp0orbit-browser\node_modules\electron\dist\electron.exe" (
    echo   [..] Installing dependencies in background...
    set "NPM_INSTALLING=1"
    powershell -NoProfile -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','npm install --prefer-offline --no-audit --no-fund 1>nul 2>&1' -WorkingDirectory '%~dp0orbit-browser' -WindowStyle Hidden" >nul 2>&1
)

REM ── 1. JARVIS kernel backend (8170) ─────────────────────────────
call :PORT_LIVE 8170
if not errorlevel 1 (
    echo   [ok] JARVIS kernel already running on port 8170
    set "KERNEL_UP=1"
) else (
    echo   [..] Starting JARVIS kernel on port 8170...
    set "KERNEL_UP=0"
    powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '%~dp0jbrowser-bridge\server.py','--backend','kernel' -WindowStyle Hidden" >nul 2>&1
)

REM ── 2. WebSocket bridge (8171) ──────────────────────────────────
call :PORT_LIVE 8171
if not errorlevel 1 (
    echo   [ok] ORBIT Bridge already running on port 8171
    set "BRIDGE_UP=1"
) else (
    echo   [..] Starting WebSocket bridge on port 8171...
    set "BRIDGE_UP=0"
    powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '%~dp0orbit-browser\python\server.py','--port','8171','--bridge-port','8170' -WindowStyle Hidden" >nul 2>&1
)

REM ── 3. Wait for BOTH services (unified loop, ~20s ceiling) ─────
if "!KERNEL_UP!"=="1" if "!BRIDGE_UP!"=="1" goto SERVICES_READY

set "WAIT=0"
:WAIT_LOOP
set /a WAIT+=1
if !WAIT! GTR 20 goto SERVICES_READY

if "!KERNEL_UP!"=="0" (
    call :PORT_LIVE 8170
    if not errorlevel 1 (
        echo   [ok] JARVIS kernel ready
        set "KERNEL_UP=1"
    )
)

if "!BRIDGE_UP!"=="0" (
    call :PORT_LIVE 8171
    if not errorlevel 1 (
        echo   [ok] Bridge ready
        set "BRIDGE_UP=1"
    )
)

if "!KERNEL_UP!"=="1" if "!BRIDGE_UP!"=="1" goto SERVICES_READY

ping -n 2 127.0.0.1 >nul
goto WAIT_LOOP

:SERVICES_READY

REM ── 4. Ensure Electron is present ───────────────────────────────
REM If a background install is running, wait on it (~60s ceiling);
REM otherwise fall through to a synchronous install (equiv. old path).
if exist "%~dp0orbit-browser\node_modules\electron\dist\electron.exe" goto ELECTRON_OK
if "!NPM_INSTALLING!"=="0" goto ELECTRON_SYNC

set "NPMPOLL=0"
:ELECTRON_WAIT
set /a NPMPOLL+=1
if exist "%~dp0orbit-browser\node_modules\electron\dist\electron.exe" goto ELECTRON_OK
if !NPMPOLL! GTR 60 goto ELECTRON_SYNC
ping -n 2 127.0.0.1 >nul
goto ELECTRON_WAIT

:ELECTRON_SYNC
cd /d "%~dp0orbit-browser"
if not exist "node_modules\electron\dist\electron.exe" call npm install --prefer-offline --no-audit --no-fund >nul 2>&1
cd /d "%~dp0"

:ELECTRON_OK
if not exist "%~dp0orbit-browser\node_modules\electron\dist\electron.exe" (
    echo   [!!] Electron install failed - run "npm install" in orbit-browser.
    ping -n 6 127.0.0.1 >nul
    exit /b 1
)

REM ── 5. Launch the browser DETACHED so this console closes ───────
REM Instantly. wait-window.ps1 runs hidden on its own; any launch
REM failure is appended to %TEMP%\orbit-launch-error.log.
echo   [..] Launching browser...
powershell -NoProfile -Command "Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','%~dp0orbit-browser\wait-window.ps1','-ElectronPath','%~dp0orbit-browser\node_modules\electron\dist\electron.exe','-WorkDir','%~dp0orbit-browser' -WindowStyle Hidden" >nul 2>&1

REM ── 6. Close this console immediately ────────────────────────────
exit