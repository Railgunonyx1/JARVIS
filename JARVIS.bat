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

title JARVIS MK-X
color 0B
set "MODE=agent"

REM Launch in Windows Terminal on first run.
REM Uses JARVIS_WT=1 env var to prevent infinite loop.
if not "%JARVIS_WT%"=="1" (
    where wt.exe >nul 2>nul
    if not errorlevel 1 (
        set "JARVIS_WT=1"
        start "" wt.exe -d "%~dp0" cmd /k "set JARVIS_WT=1&& "%~f0""
        exit /b
    )
)

REM Direct CLI arguments
if not "%~1"=="" goto argmode

REM Interactive menu
:menu
cls
echo.
echo   +---------------------------------------------+
echo   ^|          JARVIS MK-X  -  Terminal Agent     ^|
echo   +---------------------------------------------+
echo   ^|                                              ^|
echo   ^|  [1]  Chat        Interactive terminal chat ^|
echo   ^|  [2]  Plan        Read-only plan mode       ^|
echo   ^|  [3]  Controlled  Confirm every action      ^|
echo   ^|  [4]  Smart       Dynamic autonomy          ^|
echo   ^|  [5]  One-shot    Single goal, one answer   ^|
echo   ^|  [6]  Perf        Performance data          ^|
echo   ^|  [7]  Tests       Run test suite            ^|
echo   ^|  [8]  Install     Update dependencies       ^|
echo   ^|  [Q]  Quit                                 ^|
echo   +---------------------------------------------+
echo.
echo   Quick: JARVIS.bat chat ^| plan ^| smart
echo.
set /p choice="  JARVIS> "
if "%choice%"=="" goto menu
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
echo   Invalid option.
timeout /t 2 >nul
goto menu

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
"%PY%" -m cli --mode %MODE%
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
echo.
"%PY%" -m cli --mode %MODE% "%goal%"
pause
goto quit
:perf
"%PY%" -m cli perf summary
pause
goto quit
:tests
"%PY%" -m pytest tests -q
pause
goto quit
:install
echo   Updating dependencies...
"%PY%" -m pip install -r requirements.txt
pause
goto quit
:help
echo.
echo   JARVIS.bat [chat^|plan^|controlled^|smart^|oneshot^|perf^|tests^|help]
echo.
echo     chat        interactive terminal chat
echo     plan        read-only plan mode
echo     controlled  confirm every action
echo     smart       dynamic autonomy by risk
echo     oneshot     single goal, single answer
echo     perf        performance data
echo     tests       run the test suite
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
