@echo off
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"

REM ── Detect Python ─────────────────────────────────────────────────────
set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"
set "PYTHONIOENCODING=utf-8"

REM ── Ollama environment ────────────────────────────────────────────────
set "OLLAMA_FLASH_ATTENTION=1"
set "OLLAMA_NUM_PARALLEL=2"
set "OLLAMA_MAX_LOADED_MODELS=2"
set "OLLAMA_KEEP_ALIVE=10m"
set "OLLAMA_HOST=127.0.0.1:11434"
set "NO_PROXY=127.0.0.1,localhost"
set "no_proxy=127.0.0.1,localhost"

REM ── Quick dispatch (no Ollama needed) ─────────────────────────────────
if /i "%~1"=="" goto ensure_ollama
if /i "%~1"=="help" goto help
if /i "%~1"=="--help" goto help
if /i "%~1"=="tests" goto tests
if /i "%~1"=="perf" goto perf
goto ensure_ollama

REM ── Fast Ollama check via Python socket (no tasklist /FI hang) ────────
:ensure_ollama
python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect_ex(('127.0.0.1',11434)); s.close()" 2>nul
if %errorlevel%==0 goto ollama_ready

REM ── Not running — start it ────────────────────────────────────────────
echo Starting Ollama...
start "" ollama serve 2>nul
set OLLAMA_WAIT=0
:wait_loop
if %OLLAMA_WAIT% geq 8 goto ollama_timeout
timeout /t 1 /nobreak >nul 2>&1
set /a OLLAMA_WAIT+=1
python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect_ex(('127.0.0.1',11434)); s.close()" 2>nul
if %errorlevel%==0 goto ollama_ready
goto wait_loop

:ollama_timeout
echo WARNING: Ollama not responding after 8s.

:ollama_ready

:launch
if /i "%~1"=="" goto interactive
if /i "%~1"=="chat" goto interactive
if /i "%~1"=="agent" goto interactive
if /i "%~1"=="plan" goto plan
if /i "%~1"=="controlled" goto controlled
if /i "%~1"=="smart" goto smart
if /i "%~1"=="oneshot" goto oneshot
goto interactive

:interactive
"%PY%" -m cli --mode agent
goto quit

:plan
"%PY%" -m cli --mode plan
goto quit

:controlled
"%PY%" -m cli --mode controlled
goto quit

:smart
"%PY%" -m cli --mode smart
goto quit

:oneshot
set /p "goal=  goal> "
if "%goal%"=="" goto quit
"%PY%" -m cli --mode agent "%goal%"
goto quit

:perf
"%PY%" -m cli perf summary
goto quit

:tests
"%PY%" -m pytest tests -q
goto quit

:help
echo.
echo   JARVIS.bat [chat^|plan^|controlled^|smart^|oneshot^|perf^|tests^|help]
echo.
echo   Quick start: double-click JARVIS.bat
echo   Type /skills inside JARVIS to see all 31 skills
goto quit

:quit
endlocal
exit /b
