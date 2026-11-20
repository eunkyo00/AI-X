@echo off
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" (
  echo Run the initial setup command in this folder first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" Role04\scripts\launch_gui.py
if errorlevel 1 pause
