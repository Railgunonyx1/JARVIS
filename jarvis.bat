@echo off
title JARVIS MK-X - Autonomous Engineering Agent
color 0a
cd /d "%~dp0"

:: ============================================================================
:: JARVIS MK-X - Autonomous Engineering Agent
:: Launches the daemon, opens the command center, then closes this window.
:: ============================================================================

:: Launcher window closes automatically once everything is up.

if not exist "venv\Scripts\python.exe" (
    echo JARVIS venv not found. Run: python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

:: Start the JARVIS daemon (WebSocket bridge on ws://127.0.0.1:8787/ws).
:: The handler spawns the daemon fully detached (no window) and returns.
"venv\Scripts\python.exe" "daemon\jarvis_daemon_handler.py"

:: Give the daemon a moment to bind the socket.
timeout /t 4 /nobreak >nul

:: Open the JARVIS command center (connects to the daemon over WebSocket).
start "" "file:///C:/Users/aayan/Downloads/jarvis-mkx-command-center.html"

:: Done — close the launcher window.
exit /b 0
