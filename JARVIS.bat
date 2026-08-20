@echo off
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"

REM Detect Python
set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

REM Force UTF-8 for Rich output
set "PYTHONIOENCODING=utf-8"

REM ── Start Ollama if not running ───────────────────────────────────────
netstat -an 2>nul | findstr ":11434" >nul 2>&1
if errorlevel 1 (
    set "OLLAMA_EXE="
    if exist "C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe"
    if not defined OLLAMA_EXE where ollama >nul 2>&1 && set "OLLAMA_EXE=ollama"
    if defined OLLAMA_EXE (
        echo Starting Ollama...
        start "" "%OLLAMA_EXE%" serve
        ping -n 4 127.0.0.1 >nul 2>&1
    )
)

REM ── Launch JARVIS ─────────────────────────────────────────────────────
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
if /i "%~1"=="perf" goto perf
if /i "%~1"=="tests" goto tests
if /i "%~1"=="help" goto help
if /i "%~1"=="--help" goto help
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
goto quit
:quit
endlocal
exit /b
