@echo off
chcp 65001 >nul 2>&1
title JARVIS MK-X
color 0B
cd /d "%~dp0"

cls
echo.
echo   JARVIS MK-X
echo   MARK LXXXV - Cloud-First AI Assistant
echo.
echo ---------------------------------------------------------
echo.
echo   What would you like to do?
echo.
echo     [1]  Full Mode     Desktop + Voice + Camera + Gestures
echo     [2]  Desktop       Arc Reactor HUD with voice control
echo     [3]  Voice         Microphone input + Speaker output
echo     [4]  Text          Terminal chat, no voice
echo     [5]  Health        Run system diagnostics
echo     [6]  Install       Install or update dependencies
echo     [Q]  Quit          Exit JARVIS
echo.
echo ---------------------------------------------------------
echo.

set /p choice="  jarvis> "

if "%choice%"=="" exit /b
if /i "%choice%"=="1" goto full
if /i "%choice%"=="2" goto desktop
if /i "%choice%"=="3" goto voice
if /i "%choice%"=="4" goto text
if /i "%choice%"=="5" goto health
if /i "%choice%"=="6" goto install
if /i "%choice%"=="q" goto quit

echo.
echo   Invalid option. Try again.
timeout /t 2 >nul
exit /b

:full
echo   Launching Full Mode...
start "" "venv\Scripts\pythonw.exe" launcher.py --full
exit /b

:desktop
echo   Launching Desktop HUD...
start "" "venv\Scripts\pythonw.exe" launcher.py --gui
exit /b

:voice
echo   Launching Voice Mode...
start "" "venv\Scripts\pythonw.exe" launcher.py --voice
exit /b

:text
echo   Launching Text Mode...
start "" "venv\Scripts\pythonw.exe" launcher.py --text
exit /b

:health
echo   Running diagnostics...
start "" "venv\Scripts\python.exe" launcher.py --health
pause
exit /b

:install
echo   Updating dependencies...
start "" "venv\Scripts\python.exe" launcher.py --install
pause
exit /b

:quit
echo.
echo   Goodbye, sir.
exit /b
