@echo off
cd /d "%~dp0"
where python >NUL 2>NUL
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python from python.org and check "Add python.exe to PATH".
  pause
  exit /b 1
)
echo Installing required package (first time only)...
python -m pip install --quiet --disable-pip-version-check requests
python collect_kr.py %*
echo.
pause
