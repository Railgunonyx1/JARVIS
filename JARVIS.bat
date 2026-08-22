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
if /i "%~1"=="" goto launch_jarvis
if /i "%~1"=="help" goto help
if /i "%~1"=="--help" goto help
if /i "%~1"=="tests" goto tests
if /i "%~1"=="perf" goto perf

REM ── Check if Ollama is already running ────────────────────────────────
echo Starting Ollama...
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /i "ollama.exe" >nul 2>&1
if not errorlevel 1 goto ollama_ready

REM ── Start Ollama ─────────────────────────────────────────────────────
where ollama >nul 2>&1
if not errorlevel 1 goto start_by_name
if exist "C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe" goto start_by_path
echo WARNING: Ollama not found. Local models unavailable.
goto launch_jarvis

:start_by_name
start "" ollama serve
goto wait_for_ollama

:start_by_path
start "" "C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe" serve
goto wait_for_ollama

:wait_for_ollama
REM Wait up to 15 seconds for Ollama port to open
set OLLAMA_READY=0
set OLLAMA_WAIT=0
:wait_loop
if %OLLAMA_WAIT% geq 15 goto ollama_timeout
timeout /t 1 /nobreak >nul 2>&1
set /a OLLAMA_WAIT+=1
REM Check if port 11434 is listening
python -c "import socket; s=socket.socket(); s.settimeout(1); r=s.connect_ex(('127.0.0.1',11434)); s.close(); exit(0 if r==0 else 1)" 2>nul
if not errorlevel 1 (
    set OLLAMA_READY=1
    goto ollama_ready
)
goto wait_loop

:ollama_timeout
echo WARNING: Ollama not responding after 15s. Local models may be unavailable.

:ollama_ready
if "%OLLAMA_READY%"=="1" echo Ollama is ready.

:launch_jarvis
if /i "%~1"=="" goto interactive
if /i "%~1"=="chat" goto chat
if /i "%~1"=="agent" goto chat
if /i "%~1"=="plan" goto plan
if /i "%~1"=="controlled" goto controlled
if /i "%~1"=="smart" goto smart
if /i "%~1"=="oneshot" goto oneshot
goto chat

:interactive
"%PY%" -m cli --mode agent
goto quit

:chat
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
goto quit

:error_exit
echo.
echo ============================================
echo   JARVIS exited with an error.
echo   Check the messages above for details.
echo ============================================
timeout /t 5 /nobreak >nul 2>&1

:quit
endlocal
exit /b
