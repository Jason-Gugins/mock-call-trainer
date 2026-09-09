@echo off
REM Paraphrase drill -- say the same idea a different way every time.
REM Any wording you've already used gets rejected, including the lines from the
REM playbooks and everything you said in past reps.
REM
REM   paraphrase.bat                      opener, 10 shots
REM   paraphrase.bat --beat hook
REM   paraphrase.bat --beat all --reps 14
REM   paraphrase.bat --list-beats
REM   paraphrase.bat --text               type instead of speaking
cd /d "%~dp0"
".venv\Scripts\python.exe" mock_call.py --paraphrase %*
echo.
pause
