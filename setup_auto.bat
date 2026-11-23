@echo off
cd /d "%~dp0"
where python >NUL 2>NUL
if errorlevel 1 (
  echo [ERROR] Python not found.
  pause
  exit /b 1
)
where git >NUL 2>NUL
if errorlevel 1 (
  echo [ERROR] Git not found. Install Git for Windows from https://git-scm.com/download/win and run this file again.
  pause
  exit /b 1
)
python auto_update.py --setup
if errorlevel 1 (
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a = New-ScheduledTaskAction -Execute '%~dp0auto_update.bat' -WorkingDirectory '%~dp0'; $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 12:00; $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 6); Register-ScheduledTask -TaskName 'PeerScope Auto Update' -Action $a -Trigger $t -Settings $s -Force | Out-Null"
if errorlevel 1 (
  echo [ERROR] Could not register the scheduled task.
  pause
  exit /b 1
)
echo.
echo ==========================================================
echo  Done. PeerScope will update every Monday 12:00.
echo  If the PC is off at that time, it runs when the PC is turned on next.
echo  To stop: double-click remove_auto.bat
echo ==========================================================
pause
