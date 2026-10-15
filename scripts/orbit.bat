@echo off
setlocal
chcp 65001 >nul 2>&1

REM ── JARVIS Orbit — Browser Launcher ─────────────────────────────
REM Double-click this to launch JARVIS Orbit, just like Chrome.
REM
REM What it does:
REM   1. Starts the JARVIS bridge (if not running)
REM   2. Launches Chromium with the JARVIS extension
REM   3. Shows status in the terminal

REM Always cd to the project root
cd /d "%~dp0.."

REM Force UTF-8 for Python
set "PYTHONIOENCODING=utf-8"

REM Detect Python
set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

title JARVIS Orbit
color 0B

REM Relaunch in Windows Terminal if available (better rendering)
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
if "%1"=="--debug" goto debug
if "%1"=="-d" goto debug

REM Normal launch
echo   [●] Starting JARVIS Orbit...
echo.
"%PY%" scripts\orbit_launch.py %*
goto end

:firstrun
echo   [●] First-run setup...
echo.
"%PY%" scripts\orbit_launch.py --first-run
goto end

:debug
echo   [●] Debug mode...
echo.
"%PY%" scripts\orbit_launch.py --debug
goto end

:end
if errorlevel 1 (
    echo.
    echo   [✗] Launch failed. Check the output above.
    echo.
)
pause
