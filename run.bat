@echo off
REM Procore SDR mock cold call trainer -- double-click to run a normal-difficulty call.
REM You can also pass options, e.g.:  run.bat -d hostile
cd /d "%~dp0"
".venv\Scripts\python.exe" mock_call.py %*
echo.
pause
