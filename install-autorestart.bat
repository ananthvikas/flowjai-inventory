@echo off
setlocal
title flowjAI - install background service
cd /d "%~dp0"
set "ROOT=%CD%"

echo.
echo  ==========================================
echo    flowjAI - background running + auto-restart
echo  ==========================================
echo.
echo  This sets up three things in Windows Task Scheduler:
echo    1. Daily restart at a fixed time
echo    2. Watchdog every 2 minutes: restarts the app if it stops responding,
echo       and starts it if it isn't running (e.g. after the PC reboots)
echo    3. The app runs hidden - no black window to click into or close
echo.
echo  Run launch.bat at least once first, so the Python environment exists.
echo.
if not exist "venv\Scripts\python.exe" if not exist "flowjai-inventory.exe" (
    echo  ERROR: flowjAI isn't set up in this folder yet.
    echo  Run launch.bat ^(or "Start flowjAI.bat" for the packaged version^) once, close it,
    echo  then run this again.
    pause
    exit /b 1
)

set "RTIME=06:30"
set /p "RTIME=Daily restart time, 24-hour HH:MM [06:30]: "

schtasks /Create /F /TN "flowjAI\Daily restart" /SC DAILY /ST %RTIME% /TR "wscript.exe \"%ROOT%\run-hidden.vbs\" restart" >nul
if errorlevel 1 goto fail
schtasks /Create /F /TN "flowjAI\Watchdog" /SC MINUTE /MO 2 /TR "wscript.exe \"%ROOT%\run-hidden.vbs\" check" >nul
if errorlevel 1 goto fail

echo.
echo  Stopping any copy started from launch.bat and starting it in the background...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\flowjai-service.ps1" start

echo.
echo  Done.
echo    - Daily restart at %RTIME%
echo    - Watchdog every 2 minutes
echo    - Log: %ROOT%\data\logs\watchdog.log
echo.
echo  From now on just open http://localhost:8000 in the browser - no need to
echo  start the app by hand.
echo  To stop it for maintenance: stop.bat   To start again: start-background.bat
echo.
pause
exit /b 0

:fail
echo.
echo  ERROR: could not create the scheduled tasks.
echo  Try right-clicking this file and choosing "Run as administrator".
pause
exit /b 1
