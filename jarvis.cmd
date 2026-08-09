@echo off
cd /d "%~dp0"

rem Relaunch inside Windows Terminal when available; fall back to the
rem current console host otherwise.
if not "%JARVIS_WT%"=="1" (
    where wt.exe >nul 2>nul
    if not errorlevel 1 (
        set "JARVIS_WT=1"
        start "" wt.exe cmd /k call "%~f0" %*
        exit /b
    )
)

venv\Scripts\python.exe -m cli %*
