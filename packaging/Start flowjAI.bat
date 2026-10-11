@echo off
cd /d "%~dp0"
:: Starting by hand resumes the watchdog if stop.bat had paused it
if exist "data\watchdog.paused" del "data\watchdog.paused"
:: Let other PCs and the bench tablet on this network connect (port 8000, local
:: subnet only). Needs administrator rights the first time; harmless if it fails.
netsh advfirewall firewall show rule name="FlowJAI Inventory (LAN)" >nul 2>&1
if errorlevel 1 netsh advfirewall firewall add rule name="FlowJAI Inventory (LAN)" dir=in action=allow protocol=TCP localport=8000 remoteip=LocalSubnet profile=any >nul 2>&1
:: --lan is remembered, so double-clicking flowjai-inventory.exe later keeps it
start "" "%~dp0flowjai-inventory.exe" --lan
