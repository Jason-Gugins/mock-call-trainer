@echo off
REM STAR story drill -- 3 stories, number + full situation/task/action/result arc.
cd /d "%~dp0"
".venv\Scripts\python.exe" mock_call.py --star %*
echo.
pause
