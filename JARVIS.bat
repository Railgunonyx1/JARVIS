@echo off
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"

REM ══════════════════════════════════════════════════════════════════════
REM   JARVIS MK-X — Terminal Launcher (Optimized)
REM   Launches JARVIS in terminal mode (Python CLI)
REM ══════════════════════════════════════════════════════════════════════

set "OLLAMA_HOST=127.0.0.1:11434"
set "OLLAMA_MAX_LOADED_MODELS=1"
set "OLLAMA_NUM_PARALLEL=1"

REM ── Detect Python ─────────────────────────────────────────────────────
set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"
set "PYTHONIOENCODING=utf-8"

REM ── Ensure Ollama is running ──────────────────────────────────────────
where ollama >nul 2>&1
if %errorlevel%==0 goto check_ollama
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
    goto check_ollama
)
echo [WARN] Ollama not found — launching in offline mode.
goto launch

:check_ollama
"%PY%" -c "import socket,sys; s=socket.socket(); s.settimeout(1); rc=s.connect_ex(('127.0.0.1',11434)); s.close(); sys.exit(0 if rc==0 else 1)" 2>nul
if %errorlevel%==0 goto ollama_ready

echo Starting Ollama...
start "" ollama serve >nul 2>&1
set "WAIT=0"
:wait_ollama
if %WAIT% geq 10 goto launch
timeout /t 2 /nobreak >nul
set /a "WAIT+=2"
"%PY%" -c "import socket,sys; s=socket.socket(); s.settimeout(1); rc=s.connect_ex(('127.0.0.1',11434)); s.close(); sys.exit(0 if rc==0 else 1)" 2>nul
if %errorlevel%==0 goto ollama_ready
goto wait_ollama

:ollama_ready
echo Ollama ready.

:launch
echo.
echo   JARVIS MK-X — Terminal Mode
echo.

"%PY%" -m cli --mode agent
goto quit

:quit
endlocal
exit /b
