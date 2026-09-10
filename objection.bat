@echo off
REM Objection first-15s reflex drill -- label / negative-reverse / feel-felt-found.
cd /d "%~dp0"
".venv\Scripts\python.exe" mock_call.py --objection %*
echo.
pause
