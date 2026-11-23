@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unregister-ScheduledTask -TaskName 'PeerScope Auto Update' -Confirm:$false"
if errorlevel 1 (
  echo Scheduled task was not found. Nothing to remove.
) else (
  echo Auto update has been turned off.
)
pause
