@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if errorlevel 1 (
    python -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r server\requirements.txt
if errorlevel 1 goto failed
echo.
echo Demo support installed. Close the old helper and run Start-Windows.cmd again.
pause
exit /b 0
:failed
echo Installation failed. Check Python and your internet connection.
pause
exit /b 1
