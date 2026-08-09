@echo off
chcp 65001 >nul 2>&1
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
echo     [2]  Dashboard  Textual system dashboard
echo     [3]  One-shot   Type a goal, get one answer
echo     [4]  Daemon     Start the background kernel daemon
echo     [5]  Perf       Show persisted performance data
echo     [6]  Tests      Run the test suite
echo     [7]  Install    Install or update dependencies
echo     [Q]  Quit       Exit JARVIS
echo.
echo ---------------------------------------------------------
echo.

set /p choice="  jarvis> "

if "%choice%"=="" exit /b
if /i "%choice%"=="1" goto chat
if /i "%choice%"=="2" goto dashboard
if /i "%choice%"=="3" goto oneshot
if /i "%choice%"=="4" goto daemon
if /i "%choice%"=="5" goto perf
if /i "%choice%"=="6" goto tests
if /i "%choice%"=="7" goto install
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

:dashboard
echo.
"venv\Scripts\python.exe" -m cli tui
exit /b

:oneshot
echo.
set /p goal="  goal> "
if "%goal%"=="" goto chat
echo.
"venv\Scripts\python.exe" -m cli "%goal%"
pause
exit /b

:daemon
echo   Starting daemon...
"venv\Scripts\python.exe" -m cli daemon start
echo.
"venv\Scripts\python.exe" -m cli daemon status
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
