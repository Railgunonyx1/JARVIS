@echo off
setlocal
chcp 65001 >/dev/null 2>&1

REM JARVIS MK-X scripts/start.bat
REM Relaunches inside Windows Terminal when available.

if not "%JARVIS_WT%"=="1" (
    where wt.exe >/dev/null 2>/dev/null
    if not errorlevel 1 (
        set "JARVIS_WT=1"
        start "" wt.exe "%~f0"
        exit /b
    )
)

title JARVIS MK-X
color 0B
cd /d "%~dp0.."

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
timeout /t 2 >/dev/null
exit /b

:chat
echo.
echo   Type /help for commands, /exit to quit.
echo.
"venv\Scripts\python.exe" -m cli
exit /b

:oneshot
echo.
set /p goal="  goal> "
if "%goal%"=="" goto chat
echo.
"venv\Scripts\python.exe" -m cli "%goal%"
pause
exit /b

:perf
"venv\Scripts\python.exe" -m cli perf summary
pause
exit /b

:tests
"venv\Scripts\python.exe" -m pytest tests -q
pause
exit /b

:install
echo   Updating dependencies...
"venv\Scripts\python.exe" -m pip install -r requirements.txt
pause
exit /b

:quit
echo.
echo   Goodbye, sir.
exit /b
