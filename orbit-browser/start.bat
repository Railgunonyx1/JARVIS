@echo off
setlocal
chcp 65001 >nul 2>&1

REM ── JARVIS Orbit — Quick Start ─────────────────────────────────
REM Starts the WebSocket bridge + Electron browser.

cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

REM Detect Python
set "PY="
if exist "..\venv\Scripts\python.exe" set "PY=..\venv\Scripts\python.exe"
if not defined PY set "PY=python"

echo.
echo   ● ORBIT — Starting JARVIS Browser...
echo.

REM Start WebSocket bridge in background
echo   [●] Starting WebSocket bridge on port 8171...
start /b "" "%PY%" python\server.py --port 8171 --bridge-port 8170 >nul 2>&1

REM Wait for bridge to start
timeout /t 2 /nobreak >nul
echo   [✓] Bridge started

REM Check if JARVIS backend is running
echo   [●] Checking JARVIS backend on port 8170...
curl -s http://127.0.0.1:8170/status >nul 2>&1
if errorlevel 1 (
    echo   [!] JARVIS backend not running on port 8170
    echo   [!] Start it with: python jbrowser-bridge\server.py --backend kernel
    echo   [!] Or run: python -m cli
    echo.
    echo   Continuing anyway (offline mode)...
) else (
    echo   [✓] JARVIS backend connected
)

echo.
echo   [●] Launching browser...
echo.

REM Launch Electron
call npx electron .

echo.
echo   ● ORBIT — Browser closed
pause
