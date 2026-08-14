@echo off
title JARVIS MK-X - Autonomous Engineering Agent
color 0a

:: ============================================================================
:: JARVIS MK-X - Autonomous Engineering Agent
:: Launches daemon and opens UI — backend messages from JARVIS
:: ============================================================================

:: Change to the web directory
pushd web

:: Check if we're in the right directory
if not exist package.json (
    exit /b 1
)

:: Start the JARVIS Daemon (WebSocket server on ws://localhost:8787)
:: launched in background — output goes to daemon log
start "JARVIS Daemon" /min cmd /c "%~dp0venv\Scripts\python.exe daemon\jarvis_daemon_handler.py"

:: Wait for daemon to initialize
timeout /t 3 /nobreak >nul

:: Start the Vite development server (may be skipped if port in use)
findstr /c:" listening on" "%~dp0..\..\..\web\logs\vite.log" 2>nul | find "5173" >nul
if errorlevel 1 (
    start /b cmd /c "npm run dev" >nul 2>&1
)
timeout /t 3 /nobreak >nul

:: Open the JARVIS UI — this connects to the daemon via WebSocket
:: and shows all backend messages (DAEMON ONLINE, task events, etc.)
start "" "file:///C:/Users/aayan/Downloads/jarvis-mkx-command-center.html"

:: Keep window open
:waitloop
timeout /t 30 /nobreak >nul
goto waitloop