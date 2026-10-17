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
REM A-05: a candidate is only accepted if it actually RUNS (a checked-in
REM venv can reference a missing interpreter — verify, don't assume).
set "PY="
if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" -c "import sys" >nul 2>&1 && set "PY=%~dp0venv\Scripts\python.exe"
)
if not defined PY if exist "%~dp0orbit-browser\venv\Scripts\python.exe" (
    "%~dp0orbit-browser\venv\Scripts\python.exe" -c "import sys" >nul 2>&1 && set "PY=%~dp0orbit-browser\venv\Scripts\python.exe"
)
if not defined PY (
    python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo   [!!] No working Python found. Install Python 3.11+ or repair venv\Scripts.
    echo   [!!] Launcher cannot start the JARVIS services without it.
    timeout /t 15 >nul
    exit /b 1
)

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
REM If Electron is missing, npm ci starts detached NOW so it runs
REM while the kernel and bridge boot underneath, instead of serially
REM after them. Section 4 waits on it (with a ceiling) and falls back
REM to a synchronous install so failures stay loud.
REM A-06: npm ci installs exactly the locked dependency graph when a
REM lockfile exists; plain npm install is the fallback.
set "NPM_CMD=npm install --prefer-offline --no-audit --no-fund"
if exist "%~dp0orbit-browser\package-lock.json" set "NPM_CMD=npm ci --prefer-offline --no-audit --no-fund"
set "NPM_INSTALLING=0"
if not exist "%~dp0orbit-browser\node_modules\electron\dist\electron.exe" (
    echo   [..] Installing dependencies in background...
    set "NPM_INSTALLING=1"
    powershell -NoProfile -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','%NPM_CMD% 1>nul 2>&1' -WorkingDirectory '%~dp0orbit-browser' -WindowStyle Hidden" >nul 2>&1
)

REM ── 0b. Bridge auth token (A-01) ────────────────────────────────
REM One shared per-installation secret for the kernel bridge and the WS
REM bridge, stored in the user profile (not the repo). Re-launches reuse
REM it, so already-running services stay reachable. If the token file is
REM missing/empty while services are up, those services were started with
REM an unknown secret — they are killed and restarted with the fresh one
REM (secure reset, not a fallback to unauthenticated).
set "TOKEN_FILE=%LOCALAPPDATA%\JARVIS\bridge-token"
set "TOKEN_FRESH=0"
set "J_BROWSER_BRIDGE_TOKEN="
if exist "%TOKEN_FILE%" set /p J_BROWSER_BRIDGE_TOKEN=<"%TOKEN_FILE%"
REM Validate: token must be plain hex (guards against corrupted files —
REM cmd block-expansion previously wrote "ECHO is off." into this file).
echo %J_BROWSER_BRIDGE_TOKEN%| findstr /r "^[0-9a-f][0-9a-f]*$" >nul 2>&1 || set "J_BROWSER_BRIDGE_TOKEN="
if "%J_BROWSER_BRIDGE_TOKEN%"=="" set "TOKEN_FRESH=1"
if "%TOKEN_FRESH%"=="1" (
    if not exist "%LOCALAPPDATA%\JARVIS" mkdir "%LOCALAPPDATA%\JARVIS" >nul 2>&1
    REM Generate+write in ONE PowerShell call: cmd %-expansion inside a
    REM parenthesized block expands at parse time and has already written
    REM garbage here once.
    powershell -NoProfile -Command "[IO.File]::WriteAllText('%TOKEN_FILE%', [guid]::NewGuid().ToString('N'))" >nul 2>&1
    set /p J_BROWSER_BRIDGE_TOKEN=<"%TOKEN_FILE%"
    call :PORT_LIVE 8171
    if not errorlevel 1 (
        echo   [..] Token reset - restarting bridge services with the fresh secret...
        for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr /C:":8171 " ^| findstr /C:"LISTENING"') do taskkill /PID %%p /F >nul 2>&1
        for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr /C:":8170 " ^| findstr /C:"LISTENING"') do taskkill /PID %%p /F >nul 2>&1
        timeout /t 1 >nul
    )
)

REM ── 1. JARVIS kernel backend (8170) ─────────────────────────────
call :PORT_LIVE 8170
if not errorlevel 1 (
    echo   [ok] JARVIS kernel already running on port 8170
    set "KERNEL_UP=1"
) else (
    echo   [..] Starting JARVIS kernel on port 8170...
    set "KERNEL_UP=0"
    powershell -NoProfile -Command "$env:J_BROWSER_BRIDGE_TOKEN='%J_BROWSER_BRIDGE_TOKEN%'; Start-Process -FilePath '%PY%' -ArgumentList '%~dp0jbrowser-bridge\server.py','--backend','kernel' -WindowStyle Hidden" >nul 2>&1
)

REM ── 2. WebSocket bridge (8171) ──────────────────────────────────
call :PORT_LIVE 8171
if not errorlevel 1 (
    echo   [ok] ORBIT Bridge already running on port 8171
    set "BRIDGE_UP=1"
) else (
    echo   [..] Starting WebSocket bridge on port 8171...
    set "BRIDGE_UP=0"
    powershell -NoProfile -Command "$env:J_BROWSER_BRIDGE_TOKEN='%J_BROWSER_BRIDGE_TOKEN%'; Start-Process -FilePath '%PY%' -ArgumentList '%~dp0orbit-browser\python\server.py','--port','8171','--bridge-port','8170' -WindowStyle Hidden" >nul 2>&1
)

REM ── 3. Launch the browser FIRST (parallel to service boot) ──────
REM The browser does NOT need the kernel/bridge at paint time: it
REM self-reconnects (10 attempts, exp backoff) and the 8171 bridge
REM proxies to 8170 per-request. Waiting for services here only added
REM seconds of dead cold-start; the race instead is launcher overhead
REM vs Python import time, and the browser wins that race comfortably.
REM Services keep booting underneath; late-arriving JARVIS features
REM light up when their socket connects.
set "BROWSER_LAUNCHED=0"
if exist "%~dp0orbit-browser\node_modules\electron\dist\electron.exe" (
    echo   [..] Launching browser...
    set "BROWSER_LAUNCHED=1"
    REM Direct spawn: no intermediate wait-window.ps1 powershell (saves a
    REM ~0.5s process startup on the critical path). The single-instance
    REM lock handles re-runs. NO -WindowStyle Hidden here: the hidden
    REM startup state would suppress the browser window itself
    REM (ready-to-show never surfaces it). Electron is a GUI app - no
    REM console appears without the flag.
    cd /d "%~dp0orbit-browser"
    powershell -NoProfile -Command "Start-Process -FilePath 'node_modules\electron\dist\electron.exe' -ArgumentList '.' -WorkingDirectory '.'" >nul 2>&1
    cd /d "%~dp0"
)

REM ── 4. Wait for BOTH services (fast ceiling — browser already up) ─
REM No longer gates the browser: this loop only decides whether the
REM console prints "ready" or "still booting" before closing. 8s is
REM plenty for the common warm path; a cold kernel keeps booting fine
REM in its own hidden process.
if "!KERNEL_UP!"=="1" if "!BRIDGE_UP!"=="1" goto SERVICES_READY

set "WAIT=0"
:WAIT_LOOP
set /a WAIT+=1
if !WAIT! GTR 8 goto SERVICES_TIMEOUT

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

:SERVICES_TIMEOUT
echo   [..] JARVIS services still booting - they will connect shortly
goto LAUNCH_DONE

:SERVICES_READY
echo   [ok] JARVIS online

:LAUNCH_DONE

REM ── 5. Ensure Electron is present (only reached when it was MISSING
REM at section 3 — normally the browser is already launching) ──────────
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
if not exist "node_modules\electron\dist\electron.exe" call %NPM_CMD% >nul 2>&1
cd /d "%~dp0"

:ELECTRON_OK
if not exist "%~dp0orbit-browser\node_modules\electron\dist\electron.exe" (
    echo   [!!] Electron install failed - run "npm install" in orbit-browser.
    ping -n 6 127.0.0.1 >nul
    exit /b 1
)

REM ── 6. Launch the browser DETACHED (fallback path — only when
REM Electron was missing at section 3 and got installed in section 5;
REM the normal path already launched the browser in section 3).
if "!BROWSER_LAUNCHED!"=="1" goto ALREADY_LAUNCHED
echo   [..] Launching browser...
cd /d "%~dp0orbit-browser"
powershell -NoProfile -Command "Start-Process -FilePath 'node_modules\electron\dist\electron.exe' -ArgumentList '.' -WorkingDirectory '.'" >nul 2>&1
cd /d "%~dp0"

:ALREADY_LAUNCHED
REM ── 7. Close this console immediately ────────────────────────────
exit