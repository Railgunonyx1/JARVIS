@echo off
REM Build custom JARVIS models with optimized parameters.
REM Run once after pulling base models: models\setup.bat

echo Building JARVIS custom models...

echo [1/3] qwen-interrupt (1.5B, optimized for speed)
ollama create jarrvis-interrupt -f "%~dp0Modelfile.qwen-interrupt"
if %errorlevel% neq 0 echo FAILED to build jarrvis-interrupt

echo [2/3] qwen-normal (3B, optimized for coding)
ollama create jarrvis-normal -f "%~dp0Modelfile.qwen-normal"
if %errorlevel% neq 0 echo FAILED to build jarrvis-normal

echo [3/3] qwen-heavy (4B, optimized for reasoning)
ollama create jarrvis-heavy -f "%~dp0Modelfile.qwen-heavy"
if %errorlevel% neq 0 echo FAILED to build jarrvis-heavy

echo.
echo Done. Custom models: jarrvis-interrupt, jarrvis-normal, jarrvis-heavy
echo These are aliases — base models still exist for Ollama updates.
