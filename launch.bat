@echo off
setlocal enabledelayedexpansion
title flowjAI Inventory Manager
color 0A

echo.
echo  ==========================================
echo    flowjAI Inventory Manager - Starting
echo  ==========================================
echo.

:: Change to the folder containing this batch file
:: Quotes around path handle spaces in folder names
pushd "%~dp0"
if errorlevel 1 (
    echo ERROR: Could not navigate to app folder.
    echo Make sure the folder path does not contain special characters.
    pause
    exit /b 1
)

echo  Working folder: %CD%
echo.

:: Already running (e.g. as the background service)? Just open it - starting a
:: second copy would fail on port 8000 and leave a confusing error window.
curl.exe -s -m 3 http://127.0.0.1:8000/health >nul 2>&1
if not errorlevel 1 (
    echo  flowjAI is already running. Opening it in the browser...
    start http://localhost:8000
    timeout /t 3 /nobreak >nul
    exit /b 0
)

:: Find Python. 3.11 is the version the release build is made and tested with;
:: 3.12 also works. Falls back to whatever "python" is on PATH.
set "PYTHON="
py -3.11 --version >nul 2>&1 && set "PYTHON=py -3.11"
if not defined PYTHON py -3.12 --version >nul 2>&1 && set "PYTHON=py -3.12"
if not defined PYTHON python --version >nul 2>&1 && set "PYTHON=python"
if not defined PYTHON (
    color 0C
    echo  ERROR: Python was not found.
    echo.
    echo  Please ask IT to install Python 3.11:
    echo  https://www.python.org/downloads/
    echo  IMPORTANT: tick "Add Python to PATH" during install.
    echo.
    echo  After installing Python, run this file again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('%PYTHON% --version 2^>^&1') do echo  Found: %%v
echo.

:: Create virtual environment if missing
if not exist "venv\Scripts\activate.bat" (
    echo  First run - setting up Python environment...
    echo  This takes 2-3 minutes. Please wait.
    echo.
    %PYTHON% -m venv venv
    if errorlevel 1 (
        color 0C
        echo  ERROR: Could not create virtual environment.
        echo  Try running as Administrator.
        pause
        exit /b 1
    )
    echo  Environment created.
    echo.
)

:: Activate virtual environment
call venv\Scripts\activate.bat
if errorlevel 1 (
    color 0C
    echo  ERROR: Could not activate virtual environment.
    echo  Delete the venv\ folder and try again.
    pause
    exit /b 1
)

:: Install / verify Python packages
echo  Installing/checking required packages...
if exist "wheels\" (
    pip install --quiet --no-index --find-links="wheels" -r backend\requirements.txt
    if errorlevel 1 (
        echo  Offline install failed, trying with internet...
        pip install --quiet --prefer-binary -r backend\requirements.txt
    )
) else (
    pip install --quiet --prefer-binary -r backend\requirements.txt
)

if errorlevel 1 (
    color 0C
    echo  ERROR: Failed to install required packages.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)
echo  Packages OK.
echo.

if not exist "data\logs" mkdir "data\logs"
:: Starting by hand resumes the watchdog if stop.bat had paused it
if exist "data\watchdog.paused" del "data\watchdog.paused"

:: Get local IP for network sharing
set LOCAL_IP=
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1" ^| findstr /v "Hamachi" ^| findstr /v "VirtualBox" ^| findstr /v "Hyper-V"') do (
    if not defined LOCAL_IP (
        set LOCAL_IP=%%a
        set LOCAL_IP=!LOCAL_IP: =!
    )
)

:: Open Windows Firewall for port 8000 (local subnet only - not internet)
echo  Setting up firewall rule for network access...
netsh advfirewall firewall show rule name="FlowJAI Inventory (LAN)" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="FlowJAI Inventory (LAN)" dir=in action=allow protocol=TCP localport=8000 remoteip=LocalSubnet profile=any >nul 2>&1
    if errorlevel 1 (
        echo  NOTE: Could not add firewall rule ^(admin rights may be needed^).
        echo        Other devices may not be able to connect.
        echo.
    ) else (
        echo  Firewall rule added ^(LAN only^).
        echo.
    )
) else (
    echo  Firewall rule already exists.
    echo.
)

echo  ==========================================
echo    flowjAI Inventory Manager
echo  ==========================================
echo.
echo  On this computer:     http://localhost:8000
if defined LOCAL_IP (
    echo  From other computers: http://!LOCAL_IP!:8000
)
echo.
echo  First run: the browser opens a setup page to create your admin account.
echo.
echo  NOTE: Keep this window open while using the app.
echo        Close it to stop the app.
echo        Do NOT click inside this window: Windows pauses the app while
echo        text is selected here, which looks like the app has frozen.
echo        (install-autorestart.bat runs it hidden instead.)
echo.

:: run.py does the rest, exactly as the packaged .exe does: creates the schema on
:: a fresh install (or applies pending upgrades, refusing to start if one fails),
:: never loads demo data, opens the browser, and listens on the LAN (--lan).
python run.py --lan
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    color 0C
    echo  flowjAI stopped with an error - see the messages above.
) else (
    echo  Server stopped.
)
popd
pause
