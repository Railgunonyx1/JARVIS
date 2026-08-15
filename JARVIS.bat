@echo off
setlocal
chcp 65001 >nul 2>&1

rem JARVIS MK-X launcher (terminal-first).
rem Relaunch inside Windows Terminal when available; fall back to the
rem current console host otherwise.
if not "%JARVIS_WT%"=="1" (
    where wt.exe >nul 2>nul
    if not errorlevel 1 (
        set "JARVIS_WT=1"
        start "" wt.exe cmd /k call "%~f0" %*
        exit /b
    )
)

title JARVIS MK-X
color 0B
cd /d "%~dp0"

rem Pick the venv python; fall back to PATH python.
set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY set "PY=python"

rem Default to the interactive terminal (v2 Rich UI).
set "MODE=agent"

if "%~1"=="" goto menu
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

:menu
cls
echo.
echo   JARVIS MK-X - terminal-first autonomous agent
echo ---------------------------------------------------------
echo.
echo   [1]  Chat        Interactive terminal chat (agent mode)
echo   [2]  Plan        Read-only plan mode
echo   [3]  Controlled  Confirm every consequential action
echo   [4]  Smart       Dynamic autonomy by risk
echo   [5]  One-shot    Type a goal, get one answer
echo   [6]  Perf        Show persisted performance data
echo   [7]  Tests       Run the test suite
echo   [8]  Install     Install or update dependencies
echo   [Q]  Quit        Exit JARVIS
echo.
echo   Shortcuts: JARVIS.bat chat ^| plan ^| controlled ^| smart ^| oneshot
echo ---------------------------------------------------------
echo.
set /p choice="  jarvis> "

if "%choice%"=="" exit /b
if /i "%choice%"=="1" goto chat
if /i "%choice%"=="2" goto plan
if /i "%choice%"=="3" goto controlled
if /i "%choice%"=="4" goto smart
if /i "%choice%"=="5" goto oneshot
if /i "%choice%"=="6" goto perf
if /i "%choice%"=="7" goto tests
if /i "%choice%"=="8" goto install
if /i "%choice%"=="q" goto quit

echo.
echo   Invalid option. Try again.
timeout /t 2 >nul
exit /b

:chat
"%PY%" -m cli --mode %MODE%
exit /b

:plan
"%PY%" -m cli --mode plan
exit /b

:controlled
"%PY%" -m cli --mode controlled
exit /b

:smart
"%PY%" -m cli --mode smart
exit /b

:oneshot
echo.
set /p goal="  goal> "
if "%goal%"=="" exit /b
echo.
"%PY%" -m cli --mode %MODE% "%goal%"
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

:help
echo.
echo   JARVIS.bat [chat^|plan^|controlled^|smart^|oneshot^|perf^|tests^|help]
echo.
echo     (no args)   show this menu
echo     chat        interactive terminal chat (default mode: agent)
echo     plan        read-only plan mode
echo     controlled  confirm every consequential action
echo     smart       dynamic autonomy by risk
echo     oneshot     single goal, single answer
echo     perf        show persisted performance data
echo     tests       run the test suite
echo.
exit /b

:unknown
echo.
echo   Unknown argument: %1
echo   Try: JARVIS.bat help
echo.
exit /b

:quit
echo.
echo   Goodbye, sir.
exit /b
