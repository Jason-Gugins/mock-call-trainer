@echo off
REM Pain-reveal drill -- 10 shots or 3 minutes. Cost question + speed only.
cd /d "%~dp0"
".venv\Scripts\python.exe" mock_call.py --drill %*
echo.
pause
