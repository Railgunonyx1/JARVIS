@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

REM ── Detect Python ─────────────────────────────────────────────────────
set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

set "PYTHONIOENCODING=utf-8"

REM ── Ollama environment ────────────────────────────────────────────────
REM 2 models resident (1.5B for interrupts + 3B for main tasks)
set "OLLAMA_FLASH_ATTENTION=1"
set "OLLAMA_NUM_PARALLEL=2"
set "OLLAMA_MAX_LOADED_MODELS=2"
set "OLLAMA_KEEP_ALIVE=10m"
set "OLLAMA_HOST=127.0.0.1:11434"

REM ── Dispatch commands that don't need Ollama ──────────────────────────
if /i "%~1"=="help" goto help
if /i "%~1"=="--help" goto help
if /i "%~1"=="tests" goto tests
if /i "%~1"=="perf" goto perf

REM ── Find Ollama executable ────────────────────────────────────────────
set "OLLAMA_EXE="
if exist "C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe" (
    set "OLLAMA_EXE=C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe"
)
if not defined OLLAMA_EXE (
    where ollama >nul 2>&1 && set "OLLAMA_EXE=ollama"
)

REM ── Start Ollama if not running ───────────────────────────────────────
set "OLLAMA_RUNNING=0"
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /i "ollama.exe" >nul 2>&1
if not errorlevel 1 set "OLLAMA_RUNNING=1"

if "%OLLAMA_RUNNING%"=="0" (
    if defined OLLAMA_EXE (
        echo Starting Ollama server...
        start "" "!OLLAMA_EXE!" serve
        REM Wait for Ollama to be ready (up to 20 seconds)
        set /a _tries=0
        :wait_ollama
        set /a _tries+=1
        if !_tries! GEQ 20 goto ollama_ready
        REM Simple TCP check — faster than PowerShell HTTP
        powershell -NoProfile -Command "$c = New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1', 11434); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
        if not errorlevel 1 goto ollama_ready
        goto wait_ollama
        :ollama_ready
        echo Ollama ready.
    ) else (
        echo WARNING: Ollama not found. Install from https://ollama.com
        echo Continuing without local models...
    )
) else (
    echo Ollama already running.
)

REM ── Preload models ────────────────────────────────────────────────────
REM Always preload 1.5B (instant interrupt response)
REM Preload 3B (main coding model) in background
set "PRELOAD_EXE=ollama"
if defined OLLAMA_EXE set "PRELOAD_EXE=!OLLAMA_EXE!"

echo Preloading models...
start /B "" "!PRELOAD_EXE!" pull qwen2.5:1.5b >nul 2>&1
start /B "" "!PRELOAD_EXE!" pull qwen2.5:3b >nul 2>&1
REM Also keep 1.5B warm (load into memory)
start /B "" "!PRELOAD_EXE!" run qwen2.5:1.5b "hi" >nul 2>&1

REM ── Launch JARVIS ─────────────────────────────────────────────────────
echo.
if not "%~1"=="" goto argmode
"%PY%" -m cli --mode agent
goto quit

:argmode
if /i "%~1"=="chat" goto chat
if /i "%~1"=="agent" goto chat
if /i "%~1"=="plan" goto plan
if /i "%~1"=="controlled" goto controlled
if /i "%~1"=="smart" goto smart
if /i "%~1"=="oneshot" goto oneshot
goto chat

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
set /p goal="  goal> "
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
echo   Models: 1.5B (interrupts) + 3B (coding) preloaded
echo   Ollama: http://127.0.0.1:11434
echo.
goto quit

:quit
endlocal
exit /b
