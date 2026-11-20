@echo off
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" py -3.13 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r Role04\requirements-search.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" Role04\scripts\prepare_search.py
if errorlevel 1 goto failed
".venv\Scripts\python.exe" Role04\scripts\launch_gui.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Setup or startup failed. Check the message above.
pause
exit /b 1
