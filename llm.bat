@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" mock_call.py --llm %*
pause
