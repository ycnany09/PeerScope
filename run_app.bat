@echo off
cd /d "%~dp0"
where python >NUL 2>NUL
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python from python.org.
  pause
  exit /b 1
)
echo Installing required packages (first time can take a few minutes)...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
python run_local.py %*
pause
