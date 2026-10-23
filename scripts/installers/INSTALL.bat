@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title JARVIS MK-X - Dependency Installer

REM ── JARVIS MK-X — Windows dependency installer ─────────────────────
REM Installs everything the project needs, in order:
REM   1. Python 3.11+ detection (venv\ preferred, then py -3.11, then python)
REM   2. Virtual environment (venv\, created once, reused after)
REM   3. Runtime dependencies from requirements.txt
REM   4. Dev tools (pytest, ruff)
REM   5. Orbit browser npm dependencies (skipped if Node.js is absent)
REM   6. Optional Playwright Chromium engine:  INSTALL.bat /playwright
REM Idempotent — safe to re-run; satisfied steps are fast no-ops.

cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "RC=0"

set "PLAYWRIGHT=0"
if /i "%~1"=="/playwright" set "PLAYWRIGHT=1"

echo.
echo   JARVIS MK-X - Dependency Installer
echo   ==================================

REM ── 1. Resolve Python 3.11+ ────────────────────────────────────
set "PY="
if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" -c "import sys" >nul 2>&1 && set "PY=%~dp0venv\Scripts\python.exe"
)
if not defined PY (
    py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
)
if not defined PY (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo   [!!] Python 3.11+ not found.
    echo        Install from https://www.python.org/downloads/ and check
    echo        "Add python.exe to PATH", then re-run this installer.
    goto FAIL
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo   [ok] Python: %%v

REM ── 2. Create / reuse the virtual environment ──────────────────
if exist "%~dp0venv\Scripts\python.exe" goto VENV_READY
echo   [..] Creating virtual environment in venv\ ...
%PY% -m venv venv
if errorlevel 1 (
    echo   [!!] venv creation failed.
    goto FAIL
)
set "PY=%~dp0venv\Scripts\python.exe"
:VENV_READY
set "PIP=%PY% -m pip"

REM ── 3. Runtime dependencies ────────────────────────────────────
echo   [..] Installing runtime dependencies (requirements.txt)...
%PIP% install --upgrade pip -q
%PIP% install -r requirements.txt
if errorlevel 1 (
    echo   [!!] pip install -r requirements.txt failed.
    goto FAIL
)
echo   [ok] Runtime dependencies installed.

REM ── 4. Dev / test tools ────────────────────────────────────────
echo   [..] Installing dev tools (requirements-dev.txt)...
%PIP% install -r requirements-dev.txt
if errorlevel 1 (
    echo   [!!] Dev tool install failed.
    goto FAIL
)
echo   [ok] Dev tools installed.

REM ── 4b. Precompile bytecode (fast startup) ──────────────────────
echo   [..] Precompiling bytecode for fast startup...
%PY% scripts\precompile.py
if errorlevel 1 (
    echo   [!!] Precompile failed.
    goto FAIL
)
echo   [ok] Bytecode precompiled.

REM ── 5. Orbit browser npm dependencies ──────────────────────────
if not exist "%~dp0orbit-browser\package.json" goto NO_NODE_APP
where npm >nul 2>&1
if errorlevel 1 (
    echo   [!!] Node.js/npm not found - skipping Orbit browser deps.
    echo        Install Node.js 20+ from https://nodejs.org/ then re-run.
    goto NO_NODE_APP
)
if exist "%~dp0orbit-browser\node_modules\electron\dist\electron.exe" goto NPM_OK
echo   [..] Installing Orbit browser dependencies (npm)...
pushd "%~dp0orbit-browser"
if exist "package-lock.json" (
    call npm ci --prefer-offline --no-audit --no-fund
) else (
    call npm install --prefer-offline --no-audit --no-fund
)
set "NPM_RC=!errorlevel!"
popd
if not "!NPM_RC!"=="0" (
    echo   [!!] npm install failed in orbit-browser.
    goto FAIL
)
:NPM_OK
echo   [ok] Orbit browser dependencies installed.
:NO_NODE_APP

REM ── 6. Optional Playwright Chromium engine ─────────────────────
if "%PLAYWRIGHT%"=="1" (
    echo   [..] Installing Playwright Chromium engine...
    %PIP% install playwright
    if errorlevel 1 goto FAIL
    %PY% -m playwright install chromium
    if errorlevel 1 goto FAIL
    echo   [ok] Playwright Chromium installed.
)

echo.
echo   [ok] INSTALL COMPLETE
echo        Launch the agent:     JARVIS.bat
echo        Run the test suite:   venv\Scripts\python.exe -m pytest tests -q
echo        Run the app directly: venv\Scripts\python.exe -m cli
echo.
goto END

:FAIL
echo.
echo   [!!] INSTALL FAILED - see errors above.
echo.
set "RC=1"

:END
pause
exit /b %RC%
