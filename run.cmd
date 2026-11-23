@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Please run setup.cmd first.
  pause
  exit /b 1
)
start "Prism Compare" ".venv\Scripts\pythonw.exe" "src\app.py" %*
