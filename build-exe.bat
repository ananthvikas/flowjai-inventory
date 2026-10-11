@echo off
setlocal enabledelayedexpansion
title Build flowjAI Inventory Manager (packaged)
color 0E

echo.
echo  ======================================================
echo    flowjAI Inventory Manager - build packaged version
echo  ======================================================
echo.
echo  Output: dist\flowjAI\  - copy that whole FOLDER to another PC.
echo  The target PC needs nothing installed.
echo.

pushd "%~dp0"

:: -- 1. Prerequisites ----------------------------------------------------------

echo  [1/5] Checking prerequisites...

where node >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  ERROR: Node.js not found. Install from https://nodejs.org/
    pause & exit /b 1
)

set "PYTHON="
py -3.11 --version >nul 2>&1 && set "PYTHON=py -3.11"
if not defined PYTHON py -3.12 --version >nul 2>&1 && set "PYTHON=py -3.12"
if not defined PYTHON python --version >nul 2>&1 && set "PYTHON=python"
if not defined PYTHON (
    color 0C
    echo  ERROR: Python 3.11 or 3.12 not found.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('%PYTHON% --version 2^>^&1') do echo  Python: %%v
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo  Node:   %%v
echo.

:: -- 2. Python environment ------------------------------------------------------
:: Build from the app's venv, NOT the system Python. PyInstaller packages whatever
:: the building Python has installed; if a backend package is missing there, the
:: build still "succeeds" and the exe crashes on start on the other PC.

echo  [2/5] Preparing the Python environment...
if not exist "venv\Scripts\python.exe" (
    %PYTHON% -m venv venv
    if errorlevel 1 ( color 0C & echo  ERROR: could not create venv. & pause & exit /b 1 )
)
set "VPY=%CD%\venv\Scripts\python.exe"
"%VPY%" -m pip install --quiet --prefer-binary -r backend\requirements.txt pyinstaller
if errorlevel 1 ( color 0C & echo  ERROR: package install failed. & pause & exit /b 1 )
echo  Packages OK.
echo.

:: -- 3. Frontend ----------------------------------------------------------------

echo  [3/5] Building the web interface...
pushd frontend
if not exist "node_modules" (
    echo  Installing Node dependencies...
    call npm install
)
call npm run build
if errorlevel 1 (
    color 0C
    echo  ERROR: frontend build failed.
    popd & pause & exit /b 1
)
popd
if not exist "frontend\dist\index.html" (
    color 0C
    echo  ERROR: frontend\dist\index.html not found.
    pause & exit /b 1
)
echo.

:: -- 4. Package -----------------------------------------------------------------

echo  [4/5] Packaging (1-3 minutes)...
if exist "build" rmdir /s /q "build"
if exist "dist"  rmdir /s /q "dist"
"%VPY%" -m PyInstaller --noconfirm flowjai-inventory.spec
if errorlevel 1 (
    color 0C
    echo.
    echo  ERROR: packaging failed - see the output above.
    pause & exit /b 1
)
echo.

:: -- 5. Add the helper scripts ---------------------------------------------------

echo  [5/5] Adding start/stop/restart/transfer tools...
set "OUT=dist\flowjAI"
copy /y "packaging\Start flowjAI.bat" "%OUT%\" >nul
copy /y "packaging\README.txt"        "%OUT%\" >nul
for %%f in (stop.bat transfer-db.bat start-background.bat install-autorestart.bat uninstall-autorestart.bat flowjai-service.ps1 run-hidden.vbs BUILD_VERSION.txt RELEASE_NOTES.md) do (
    if exist "%%f" copy /y "%%f" "%OUT%\" >nul
)
if not exist "%OUT%\flowjai-inventory.exe" (
    color 0C
    echo  ERROR: %OUT%\flowjai-inventory.exe missing.
    pause & exit /b 1
)

color 0A
echo.
echo  ======================================================
echo    Build complete:  dist\flowjAI\
echo  ======================================================
echo.
echo    Copy the WHOLE dist\flowjAI folder to the other PC (e.g. C:\flowjAI),
echo    not just the .exe - it needs the _internal folder beside it.
echo    Then follow README.txt in that folder.
echo.
echo    To bring the data across: on the other PC, drag this app folder
echo    onto transfer-db.bat. Don't copy flowjai.db by hand.
echo.
pause
popd
