@echo off
title JARVIS MK-X
cd /d "%~dp0"
color 0B

:menu
cls
echo.
echo     J A R V I S   MK-X
echo.
echo     1  Desktop    Arc Reactor HUD
echo     2  Text       Terminal chat
echo     3  Voice      Mic + Speaker
echo     4  Full       All features
echo.
echo     5  Health     Run diagnostics
echo     6  Install    Update dependencies
echo     Q  Exit
echo.
set /p "choice=  > "

if /i "%choice%"=="1" (
    echo Starting Desktop...
    start "JARVIS" /MIN "%~dp0venv\Scripts\python.exe" "%~dp0main.py" --desktop
    exit
)
if /i "%choice%"=="2" (
    echo Starting Text Mode...
    "%~dp0venv\Scripts\python.exe" "%~dp0main.py" --text
    goto menu
)
if /i "%choice%"=="3" (
    echo Starting Voice...
    start "JARVIS" /MIN "%~dp0venv\Scripts\python.exe" "%~dp0main.py" --voice
    exit
)
if /i "%choice%"=="4" (
    echo Starting Full...
    start "JARVIS" /MIN "%~dp0venv\Scripts\python.exe" "%~dp0main.py" --full
    exit
)
if /i "%choice%"=="5" (
    "%~dp0venv\Scripts\python.exe" "%~dp0main.py" --health
    pause
    goto menu
)
if /i "%choice%"=="6" (
    "%~dp0venv\Scripts\python.exe" -m pip install -r requirements.txt
    pause
    goto menu
)
if /i "%choice%"=="q" exit
goto menu
