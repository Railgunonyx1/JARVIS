@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

REM ── JARVIS Orbit — Quick Start ─────────────────────────────────
REM 1. Starts the JARVIS kernel backend (port 8170)
REM 2. Starts the WebSocket bridge (port 8171)
REM 3. Launches the Electron browser, then closes this console.
REM
REM Idempotent: if either service is already listening, it is reused
REM (no duplicate spawns / EADDRINUSE windows on re-run).
REM Services run as hidden, detached processes and keep running
REM until you close them.

cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

REM ── Resolve Python (venv first, then system) ───────────────────
set "PY="
if exist "%~dp0..\venv\Scripts\python.exe" set "PY=%~dp0..\venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\.venv\Scripts\python.exe" set "PY=%~dp0..\.venv\Scripts\python.exe"
if not defined PY set "PY=python"

echo.
echo   ● ORBIT — Starting JARVIS Browser...
echo.

REM ── 1. Start JARVIS kernel backend (8170) ──────────────────────
powershell -NoProfile -Command "$c = New-Object System.Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',8170); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo   [✓] JARVIS kernel already running on port 8170
    goto KERNEL_READY
)
echo   [●] Starting JARVIS kernel on port 8170...
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '%~dp0..\jbrowser-bridge\server.py','--backend','kernel' -WindowStyle Hidden" >nul 2>&1

REM ── 2. Start WebSocket bridge (8171) ───────────────────────────
powershell -NoProfile -Command "$c = New-Object System.Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',8171); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo   [✓] ORBIT Bridge already running on port 8171
    goto BRIDGE_READY
)
echo   [●] Starting WebSocket bridge on port 8171...
powershell -NoProfile -Command "Start-Process -FilePath '%PY%' -ArgumentList '%~dp0python\server.py','--port','8171','--bridge-port','8170' -WindowStyle Hidden" >nul 2>&1

REM ── 3. Wait for services ───────────────────────────────────────
set "WAIT=0"

:WAIT_KERNEL
set /a WAIT+=1
if !WAIT! GTR 15 goto KERNEL_READY
powershell -NoProfile -Command "$c = New-Object System.Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',8170); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto KERNEL_READY
ping -n 2 127.0.0.1 >nul
goto WAIT_KERNEL

:KERNEL_READY
echo   [✓] JARVIS kernel ready

set "WAIT=0"

:WAIT_BRIDGE
set /a WAIT+=1
if !WAIT! GTR 15 goto BRIDGE_READY
powershell -NoProfile -Command "$c = New-Object System.Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',8171); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto BRIDGE_READY
ping -n 2 127.0.0.1 >nul
goto WAIT_BRIDGE

:BRIDGE_READY
echo   [✓] Bridge started

REM ── 4. Launch the browser (detached) and close this console ───
echo.
echo   [●] Launching browser...
echo.

if exist "%~dp0node_modules\electron\dist\electron.exe" (
    powershell -NoProfile -Command "Start-Process -FilePath '%~dp0node_modules\electron\dist\electron.exe' -ArgumentList '.' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
) else (
    echo   [!] Electron not installed. Running: npm install
    call npm install >nul 2>&1
    powershell -NoProfile -Command "Start-Process -FilePath '%~dp0node_modules\electron\dist\electron.exe' -ArgumentList '.' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
)

exit