@echo off
cd /d "%~dp0.."
if not exist "..\.venv\Scripts\python.exe" (
  echo Python environment not found. Follow Role04/README.md first.
  pause
  exit /b 1
)
"..\.venv\Scripts\python.exe" scripts\serve_web.py --open-browser
if errorlevel 1 pause
