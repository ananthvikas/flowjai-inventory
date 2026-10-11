@echo off
title flowjAI - start
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0flowjai-service.ps1" start
start http://localhost:8000
timeout /t 3 /nobreak >nul
