@echo off
REM Career narrative drill -- why sales / why this company / the gap answer.
cd /d "%~dp0"
".venv\Scripts\python.exe" mock_call.py --narrative %*
echo.
pause
