@echo off
rem ============================================================================
rem JARVIS MK-X Launcher
rem Launches the new Textual terminal UI
rem ============================================================================

rem Change to JARVIS directory
cd /d "%~dp0"

rem Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Error: Python is not installed or not in PATH.
    echo.
    pause
    exit /b 1
)

rem Launch the new Textual TUI
echo.
echo launching JARVIS Terminal UI...
echo.
echo The UI will feature:
echo   - System stats (CPU/RAM/Disk) with 20-second refresh
echo   - Token usage display: X / Y tokens (Z%)
echo   - Todo list (Ctrl+T to toggle)
echo   - Context panel (Ctrl+C to toggle, larger window)
echo   - Command input at jarvis> prompt
echo.
python -m ui.tui
exit /b 0