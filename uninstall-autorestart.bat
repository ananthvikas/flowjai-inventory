@echo off
title flowjAI - remove background service
cd /d "%~dp0"
schtasks /Delete /F /TN "flowjAI\Daily restart" >nul 2>&1
schtasks /Delete /F /TN "flowjAI\Watchdog" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0flowjai-service.ps1" stop
echo Scheduled tasks removed and the background server stopped.
echo Use launch.bat to run the app in a window again.
pause
