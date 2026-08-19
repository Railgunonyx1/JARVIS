@echo off
setlocal
chcp 65001 >nul 2>&1

REM Always cd to the directory containing this bat file
cd /d "%~dp0.."

REM JARVIS MK-X scripts/start.bat
REM Relaunches inside Windows Terminal when available.

if not "%JARVIS_WT%"=="1" (
    where wt.exe >nul 2>nul
    if not errorlevel 1 (
        set "JARVIS_WT=1"
        start "" wt.exe "%~f0"
        exit /b
    )
)

REM Force UTF-8 for Python
set "PYTHONIOENCODING=utf-8"

REM Detect Python (same logic as JARVIS.bat)
set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist "..\venv\Scripts\python.exe" set "PY=..\venv\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

title JARVIS MK-X
color 0B

cls
echo.
echo   +=============================================+
echo   ^|          JARVIS MK-X  -  Terminal Agent     ^|
echo   +=============================================+
echo   ^|                                              ^|
echo   ^|  [1]  Chat       Interactive terminal chat  ^|
echo   ^|  [2]  One-shot   Single goal, one answer    ^|
echo   ^|  [3]  Perf       Performance data           ^|
echo   ^|  [4]  Tests      Run the test suite         ^|
echo   ^|  [5]  Install    Update dependencies        ^|
echo   ^|  [Q]  Quit                                  ^|
echo   +=============================================+
echo.
echo   Quick: scripts/start.bat chat
echo.

set /p choice="  JARVIS> "

if "%choice%"=="" exit /b
if /i "%choice%"=="1" goto chat
if /i "%choice%"=="2" goto oneshot
if /i "%choice%"=="3" goto perf
if /i "%choice%"=="4" goto tests
if /i "%choice%"=="5" goto install
if /i "%choice%"=="q" goto quit

echo.
echo   Invalid option.
timeout /t 2 >nul
exit /b

:chat
echo.
echo   Type /help for commands, /exit to quit.
echo.
"%PY%" -m cli
exit /b

:oneshot
echo.
set /p goal="  goal> "
if "%goal%"=="" goto chat
echo.
"%PY%" -m cli "%goal%"
pause
exit /b

:perf
"%PY%" -m cli perf summary
pause
exit /b

:tests
"%PY%" -m pytest tests -q
pause
exit /b

:install
echo   Updating dependencies...
"%PY%" -m pip install -r requirements.txt
pause
exit /b

:quit
echo.
echo   Goodbye, sir.
exit /b
