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
REM Note: keep_alive and model-specific settings live in config/models.toml
REM and providers/ollama_provider.py — not here. BAT only configures the
REM daemon process and proxy bypass for localhost connections.
set "OLLAMA_FLASH_ATTENTION=1"
set "OLLAMA_HOST=127.0.0.1:11434"
set "NO_PROXY=127.0.0.1,localhost,::1"
set "no_proxy=127.0.0.1,localhost,::1"

REM ── Quick dispatch (no Ollama needed) ─────────────────────────────────
if /i "%~1"=="" goto ensure_ollama
if /i "%~1"=="" goto ensure_ollama
if /i "%~1"=="help" goto help
if /i "%~1"=="--help" goto help
if /i "%~1"=="tests" goto tests
if /i "%~1"=="perf" goto perf
goto ensure_ollama

REM ── Verify Ollama is installed ────────────────────────────────────────
:ensure_ollama
where ollama >nul 2>&1
if %errorlevel%==0 goto check_running
REM Ollama not on PATH — check common install location
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
    goto check_running
)
echo.
echo   Ollama is not installed or not on PATH.
echo   Install from: https://ollama.com/download
echo.
echo   JARVIS can still run with cloud providers, but local models won't work.
echo.
set /p "_continue=  Continue without Ollama? (y/n): "
if /i "%_continue%"=="y" goto launch
if /i "%_continue%"=="Y" goto launch
goto quit

REM ── Check if daemon is running ────────────────────────────────────────
:check_running
"%PY%" -c "import socket; s=socket.socket(); s.settimeout(1); s.connect_ex(('127.0.0.1',11434)); s.close()" 2>nul
if %errorlevel%==0 goto ollama_ready

REM ── Not running — start it with progressive wait ──────────────────────
echo Starting Ollama...
start "" ollama serve 2>nul

REM Progressive timeout: 1s, 2s, 3s, 5s, 5s, 5s = 21s total
set "OLLAMA_WAIT=0"
set "OLLAMA_LIMIT=21"
:wait_loop
if %OLLAMA_WAIT% geq %OLLAMA_LIMIT% goto ollama_timeout

if %OLLAMA_WAIT% lss 1 (set /a "_sleep=1") else if %OLLAMA_WAIT% lss 3 (set /a "_sleep=2") else (set /a "_sleep=3")
timeout /t %_sleep% /nobreak >nul 2>&1
set /a "OLLAMA_WAIT+=_sleep"

"%PY%" -c "import socket; s=socket.socket(); s.settimeout(1); s.connect_ex(('127.0.0.1',11434)); s.close()" 2>nul
if %errorlevel%==0 goto ollama_ready
goto wait_loop

:ollama_timeout
echo.
echo   WARNING: Ollama not responding after %OLLAMA_LIMIT%s.
echo.
echo   [1] Retry startup
echo   [2] Continue without Ollama
echo   [3] Exit
echo.
set /p "_choice=  Choose: "
if "%_choice%"=="1" goto ensure_ollama
if "%_choice%"=="2" goto launch
goto quit

:ollama_ready
echo Ollama ready.

REM ── Launch JARVIS ─────────────────────────────────────────────────────
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
echo   Type /skills inside JARVIS to see all skills
goto quit

:quit
endlocal
exit /b
