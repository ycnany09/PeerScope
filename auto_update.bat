@echo off
cd /d "%~dp0"
title PeerScope Auto Update
echo ==========================================================
echo  PeerScope auto update is running. Please do not close.
echo  If there is new quarterly data, this can take about 1 hour.
echo ==========================================================
where python >NUL 2>NUL
if errorlevel 1 (
  echo [ERROR] Python not found.
  timeout /t 30
  exit /b 1
)
python auto_update.py
echo.
echo This window will close in 30 seconds. Log: auto_update.log
timeout /t 30
