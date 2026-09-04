@echo off
rem J-Browser launcher  (real Chrome + JARVIS)
rem Pass "firstrun" as an argument to open the extensions page for one-time loading.
setlocal
set "SCRIPT_DIR=%~dp0"
if /i "%~1"=="firstrun" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\jbrowser-launcher.ps1" -FirstRun
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\jbrowser-launcher.ps1"
)
echo.
echo Press any key to close this window...
pause >nul
endlocal
