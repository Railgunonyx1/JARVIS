@echo off
setlocal
chcp 65001 >nul 2>&1

rem Relaunch inside Windows Terminal when available; fall back to the
rem current console host otherwise.
if not "%JARVIS_WT%"=="1" (
    where wt.exe >nul 2>nul
    if not errorlevel 1 (
        set "JARVIS_WT=1"
        start "" wt.exe cmd /k call "%~f0"
        exit /b
    )
)

title JARVIS MK-X
color 0B
cd /d "%~dp0.."

cls
echo.
echo   JARVIS MK-X
echo   MARK LXXXV - Cloud-First AI Assistant
echo ---------------------------------------------------------
echo.
echo   What would you like to do?
echo.
echo     [1]  Chat       Interactive terminal chat
echo     [2]  One-shot   Type a goal, get one answer
echo     [3]  Perf       Show persisted performance data
echo     [4]  Tests      Run the test suite
echo     [5]  Install    Install or update dependencies
echo     [Q]  Quit       Exit JARVIS
echo.
echo ---------------------------------------------------------
echo.

set /p choice="  jarvis> "

if "%choice%"=="" exit /b
if /i "%choice%"=="1" goto chat
if /i "%choice%"=="2" goto oneshot
if /i "%choice%"=="3" goto perf
if /i "%choice%"=="4" goto tests
if /i "%choice%"=="5" goto install
if /i "%choice%"=="q" goto quit

echo.
echo   Invalid option. Try again.
timeout /t 2 >nul
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
