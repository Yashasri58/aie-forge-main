@echo off
title Forge - Shutdown
color 0C

echo.
echo Stopping Forge (port 8000)...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo Stopping PID %%a
    taskkill /PID %%a /F >nul 2>&1
)

echo Done.
timeout /t 2 /nobreak >nul
