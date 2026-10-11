@echo off
title flowjAI - Stopping
cd /d "%~dp0"
echo Stopping flowjAI Inventory Manager...
:: Stops the server however it was started (background service or launch.bat),
:: and pauses the watchdog so it doesn't start it straight back up.
:: (The old version ran "taskkill /im uvicorn.exe", which never matched: the
::  server runs as python.exe, so it silently did nothing.)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0flowjai-service.ps1" stop
echo Done. Run start-background.bat (or launch.bat) to start again.
timeout /t 4 /nobreak >nul
