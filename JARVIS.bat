@echo off
setlocal
chcp 65001 >nul 2>&1
title JARVIS Orbit

REM -- JARVIS Orbit - Browser Launcher -----------------------------
REM This is the Orbit browser - a custom Electron browser with JARVIS.
REM It is NOT Google Chrome. It ships with its own Chromium.
REM
REM Double-click this to launch JARVIS Orbit.
REM All services start hidden; once the browser window is up, this
REM console closes itself. Nothing but the browser window remains.

cd /d "%~dp0"

REM Pass through first-run / dev flags to the real launcher
if "%1"=="--first-run" goto passthrough
if "%1"=="-f" goto passthrough
if "%1"=="--dev" goto passthrough

REM Normal launch: delegate to orbit-browser\start.bat
call "%~dp0orbit-browser\start.bat"
exit /b %errorlevel%

:passthrough
call "%~dp0orbit-browser\start.bat" %1
exit /b %errorlevel%
