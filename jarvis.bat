@echo off
title JARVIS MK-X - Autonomous Engineering Agent
color 0a

:: ============================================================================
:: JARVIS MK-X - Autonomous Engineering Agent
:: Launches the React frontend (Vite) and opens the application in browser
:: The JARVIS daemon should be running separately for full functionality
:: ============================================================================

echo.
echo ============================================================================
echo  JARVIS MK-X - Autonomous Engineering Agent
echo ============================================================================

:: Change to the web directory
pushd web

:: Check if we're in the right directory
if not exist package.json (
    echo.
    ERROR: Could not find package.json. Are you in the correct directory?
    pause
    exit /b 1
)

echo.
echo Starting JARVIS MK-X Frontend...
echo.

:: Start Vite development server in background
:: The server will output its URL (typically http://localhost:5173)
start /b cmd /c "npm run dev"

:: Wait a moment for the server to start
timeout /t 3 /nobreak >nul

:: Get the local IP address for the URL
for /f "tokens=2 skipws" in ('ipconfig ^| findstr "IPv4 Address"') do set LOCAL_IP=%%a

echo.
echo JARVIS MK-X is starting up...
echo.
echo  Frontend: http://localhost:5173
echo.
echo  Please ensure the JARVIS daemon is running for full functionality.
echo  To start the daemon, see the roadmap or documentation.
echo.
echo  Press Ctrl+C to stop this launcher or close this window
echo.

:: Open the default browser to the JARVIS interface
start "" "http://localhost:5173"

:: Keep the batch window open
:waitloop
timeout /t 30 /nobreak >nul
goto waitloop