@echo off
REM ── JARVIS Orbit - Launch (compat) ───────────────────────────────
REM Thin wrapper for the canonical root launcher (JARVIS.bat), kept so
REM existing shortcuts/scripts that call orbit-browser\start.bat still work.
call "%~dp0..\JARVIS.bat" %*
exit /b %errorlevel%