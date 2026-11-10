@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m server.scout --open
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    python -m server.scout --open
  ) else (
    py -3 -m server.scout --open
  )
)
echo.
echo If Python is missing, install Python 3.10 or newer from python.org and enable Add Python to PATH.
pause
