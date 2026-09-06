@echo off
setlocal
chcp 65001 >nul 2>&1

REM ── JARVIS Orbit — Browser Launcher ─────────────────────────────
REM This is the Orbit browser — a custom Electron browser with JARVIS.
REM It is NOT Google Chrome. It ships with its own Chromium.
REM
REM Double-click this to launch JARVIS Orbit.

REM Always cd to the directory containing this bat (the project root)
cd /d "%~dp0"

REM Force UTF-8 for Python
set "PYTHONIOENCODING=utf-8"

REM Detect Python
set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

title JARVIS Orbit
color 0B

REM Relaunch in Windows Terminal when available (better rendering)
if not "%JARVIS_WT%"=="1" (
    where wt.exe >nul 2>nul
    if not errorlevel 1 (
        set "JARVIS_WT=1"
        start "" wt.exe "%~f0"
        exit /b
    )
)

cls
echo.
echo   ╔═══════════════════════════════════════════════╗
echo   ║                                               ║
echo   ║   ● ORBIT — JARVIS Browser                    ║
echo   ║                                               ║
echo   ║   Nothing Design System                       ║
echo   ║   Chromium + Native Intelligence              ║
echo   ║                                               ║
echo   ╚═══════════════════════════════════════════════╝
echo.

REM Parse arguments
if "%1"=="--first-run" goto firstrun
if "%1"=="-f" goto firstrun
if "%1"=="--dev" goto dev

REM Normal launch
echo   [●] Starting JARVIS Orbit...
echo.

REM Start the WebSocket bridge in background
start /b "" "%PY%" orbit-browser\python\server.py

REM Wait for bridge to start
timeout /t 2 /nobreak >nul

REM Launch the Electron browser
cd orbit-browser
if exist "node_modules\.bin\electron" (
    call npx electron .
) else (
    echo   [!] Electron not installed. Running: npm install
    call npm install
    call npx electron .
)
goto end

:firstrun
echo   [●] First-run setup...
echo.
cd orbit-browser
if not exist "node_modules" (
    echo   [●] Installing dependencies...
    call npm install
)
echo   [●] Starting browser...
call npx electron .
goto end

:dev
echo   [●] Dev mode...
echo.
start /b "" "%PY%" orbit-browser\python\server.py
timeout /t 2 /nobreak >nul
cd orbit-browser
call npx electron . --dev
goto end

:end
if errorlevel 1 (
    echo.
    echo   [✗] Launch failed. Check the output above.
    echo.
)
pause
