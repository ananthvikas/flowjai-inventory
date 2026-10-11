@echo off
echo Downloading Python packages for offline use...
cd /d "%~dp0"
if not exist "wheels" mkdir wheels
pip download --dest wheels -r backend\requirements.txt ^
    --platform win_amd64 --python-version 311 ^
    --implementation cp --only-binary=:all: 2>nul
if errorlevel 1 pip download --dest wheels -r backend\requirements.txt
echo Done. Include the wheels\ folder in your distribution.
pause
