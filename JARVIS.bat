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

REM ── Quick dispatch (no Ollama needed) ─────────────────────────────────
if /i "%~1"=="help" goto help
if /i "%~1"=="--help" goto help
if /i "%~1"=="tests" goto tests
if /i "%~1"=="perf" goto perf

REM ── Start Ollama if not running ───────────────────────────────────────
where ollama >nul 2>&1
if %errorlevel% equ 0 (
    tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /i "ollama.exe" >nul 2>&1
    if %errorlevel% neq 0 (
        echo Starting Ollama...
        start "" ollama serve
        timeout /t 3 /nobreak >nul 2>&1
        echo Ollama started.
    ) else (
        echo Ollama running.
    )
) else (
    REM Try known install path
    if exist "C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe" (
        tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /i "ollama.exe" >nul 2>&1
        if %errorlevel% neq 0 (
            echo Starting Ollama...
            start "" "C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe" serve
            timeout /t 3 /nobreak >nul 2>&1
            echo Ollama started.
        ) else (
            echo Ollama running.
        )
    ) else (
        echo WARNING: Ollama not found. Local models unavailable.
    )
)

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
goto quit

:quit
endlocal
exit /b
