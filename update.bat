@echo off
setlocal
cd /d "%~dp0"
if "%1"=="" (
    echo Usage: update.bat path\to\new-version-folder
    echo Extract the new version zip and pass the extracted folder.
    pause & exit /b 1
)
echo Stopping flowjAI...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0flowjai-service.ps1" stop >nul 2>&1
echo Backing up database...
:: SQLite backup API, not a file copy: the newest records may still be in flowjai.db-wal
if exist "data\flowjai.db" venv\Scripts\python.exe -c "import sqlite3;s=sqlite3.connect(r'data\flowjai.db');d=sqlite3.connect(r'data\flowjai.db.backup');s.backup(d);d.close();s.close()"
echo Copying new files...
xcopy /E /I /Y /Q "%1\backend" "backend" >nul
xcopy /E /I /Y /Q "%1\frontend\dist" "frontend\dist" >nul
if exist "%1\wheels" xcopy /E /I /Y /Q "%1\wheels" "wheels" >nul
echo Running database migrations...
call venv\Scripts\activate.bat
cd backend & python -m alembic upgrade head & cd ..
echo Update complete. Run launch.bat or start-background.bat to start.
pause
