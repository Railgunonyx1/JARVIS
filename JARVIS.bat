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

REM Launch in Windows Terminal on first run only.
set "_mark=%TEMP%\jarvis_wt_launched"
if not exist "%_mark%" (
    where wt.exe >nul 2>nul
    if not errorlevel 1 (
        echo. > "%_mark%"
        start "" wt.exe -d "%~dp0" "%~f0"
        exit /b
    )
)
del "%_mark%" 2>nul

REM Direct CLI arguments - go straight to the mode
if not "%~1"=="" goto argmode

REM Default: interactive chat mode - no menu, straight to agent
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
goto unknown

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
echo.
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
:unknown
echo.
echo   Unknown argument: %1
echo   Try: JARVIS.bat help
echo.
goto quit
:quit
endlocal
exit /b
