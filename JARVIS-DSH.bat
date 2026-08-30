@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

title JARVIS MK-X - DeepSeek Harness

echo.
echo ==============================================================
echo   JARVIS MK-X - DeepSeek Harness
echo ==============================================================
echo.

REM --------------------------------------------------------------
REM OLLAMA ENVIRONMENT
REM --------------------------------------------------------------

set "OLLAMA_HOST=127.0.0.1:11434"
set "OLLAMA_MAX_LOADED_MODELS=1"
set "OLLAMA_NUM_PARALLEL=1"

REM --------------------------------------------------------------
REM CHECK NODE.JS
REM --------------------------------------------------------------

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js was not found in PATH.
    echo [INFO] DeepSeek Harness requires Node.js.
    echo.
    pause
    exit /b 1
)

echo [OK] Node.js detected.

REM --------------------------------------------------------------
REM FREE PORT 3080
REM --------------------------------------------------------------

echo [INFO] Checking port 3080...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3080" ^| findstr "LISTENING"') do (
    if defined %%a (
        echo [INFO] Stopping stale process %%a on port 3080...
        taskkill /PID %%a /F >nul 2>&1
        if errorlevel 1 echo [WARN] Failed to kill process %%a
    )
)

timeout /t 1 /nobreak >nul

REM --------------------------------------------------------------
REM OLLAMA
REM --------------------------------------------------------------

where ollama >nul 2>&1
if not errorlevel 1 goto CHECK_OLLAMA

REM Check common install location
set "OLLAMA_FOUND=0"
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_FOUND=1"
if "!OLLAMA_FOUND!"=="1" (
    set "PATH=%LOCALAPPDATA%\Programs\Ollama;!PATH!"
)
goto AFTER_OLLAMA_PATH

:AFTER_OLLAMA_PATH

if "!OLLAMA_FOUND!"=="0" (
    echo [WARN] Ollama was not found. Continuing without Ollama.
    goto LAUNCH_DSH
)

:CHECK_OLLAMA

echo [INFO] Checking Ollama on 127.0.0.1:11434...

powershell -NoProfile -Command "try { $c = New-Object System.Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 11434); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto OLLAMA_READY

echo [INFO] Starting Ollama...
start "" /min ollama serve

set "WAIT=0"

:WAIT_OLLAMA

if !WAIT! GEQ 15 goto OLLAMA_TIMEOUT

timeout /t 1 /nobreak >nul
set /a WAIT+=1

powershell -NoProfile -Command "try { $c = New-Object System.Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 11434); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto OLLAMA_READY

goto WAIT_OLLAMA

:OLLAMA_READY

echo [OK] Ollama ready.
goto LAUNCH_DSH

:OLLAMA_TIMEOUT
echo [WARN] Ollama did not become ready within 15 seconds.
echo [INFO] Continuing with DeepSeek Harness.
goto LAUNCH_DSH

REM --------------------------------------------------------------
REM DEEPSEEK HARNESS
REM --------------------------------------------------------------

:LAUNCH_DSH

echo.
echo ==============================================================
echo   Starting DeepSeek Harness
echo ==============================================================
echo   URL: http://127.0.0.1:3080
echo ==============================================================
echo.

REM Use an installed dsh if available.
where dsh >nul 2>&1
if not errorlevel 1 (
    echo [OK] Using installed dsh CLI.
    start "DSH" cmd /c dsh web
    if errorlevel 1 echo [WARN] dsh CLI may not be available or failed to start.
    echo [OK] DSH started in a new window.
    goto DONE
)

REM Official fallback: run the published package through npx.
echo [INFO] dsh was not found globally.
echo [INFO] Starting DeepSeek Harness through npx...
echo.

start "DSH" cmd /c npx @deepseek-ai/dsh web
if errorlevel 1 echo [WARN] npx @deepseek-ai/dsh may not be available or failed to start.
echo [OK] DSH started in a new window.

:DONE

echo.
echo Close the DSH window to stop.
echo.

endlocal
pause
exit /b
