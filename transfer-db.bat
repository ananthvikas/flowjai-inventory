@echo off
setlocal enabledelayedexpansion
title flowjAI - transfer database
cd /d "%~dp0"
echo.
echo  ==========================================
echo    flowjAI - bring a database into this copy
echo  ==========================================
echo.
echo  Use this instead of copying flowjai.db by hand. A hand copy can lose the
echo  newest records and can corrupt the copied file.
echo.
set "MODE="
if exist "venv\Scripts\python.exe" set "MODE=python"
if not defined MODE if exist "flowjai-inventory.exe" set "MODE=exe"
if not defined MODE (
    echo  ERROR: run launch.bat ^(or "Start flowjAI.bat"^) once first.
    pause & exit /b 1
)
set "SRC=%~1"
if "%SRC%"=="" (
    echo  Tip: you can drag the OLD app folder onto this file.
    echo.
    set /p "SRC=Path of the OLD app folder (or its flowjai.db): "
)
if "%SRC%"=="" ( echo  Nothing entered. & pause & exit /b 1 )
set "SRC=%SRC:"=%"
:: a trailing backslash would escape the closing quote when passed on
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"

echo.
echo  Stopping flowjAI (any copy running on port 8000)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0flowjai-service.ps1" stop >nul

if "%MODE%"=="python" (
    venv\Scripts\python.exe backend\tools\transfer_db.py "%SRC%"
) else (
    rem The exe has no console of its own: it writes to data\logs\transfer.log
    start "" /wait "%~dp0flowjai-inventory.exe" --transfer-db "%SRC%"
    set "RC=!errorlevel!"
    type "data\logs\transfer.log"
    cmd /c exit !RC!
)
if errorlevel 1 (
    echo  Transfer did NOT complete. Nothing was started.
    pause & exit /b 1
)

echo  Starting flowjAI (database upgrades run automatically)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0flowjai-service.ps1" start
start http://localhost:8000
echo.
pause
