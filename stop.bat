@echo off
title Cross-Border Wire Transfer System - Shutdown
color 0C

echo.
echo ===============================================
echo   Cross-Border Wire Transfer System
echo   Stopping all services...
echo ===============================================
echo.

echo Stopping Node.js processes on service ports...
echo.

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    echo Stopping Gateway Service (PID: %%a)
    taskkill /PID %%a /F >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3001 " ^| findstr "LISTENING"') do (
    echo Stopping Account Service (PID: %%a)
    taskkill /PID %%a /F >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3002 " ^| findstr "LISTENING"') do (
    echo Stopping Payment Processor (PID: %%a)
    taskkill /PID %%a /F >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3003 " ^| findstr "LISTENING"') do (
    echo Stopping Validation Service (PID: %%a)
    taskkill /PID %%a /F >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3004 " ^| findstr "LISTENING"') do (
    echo Stopping Ledger Service (PID: %%a)
    taskkill /PID %%a /F >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3005 " ^| findstr "LISTENING"') do (
    echo Stopping FX Service (PID: %%a)
    taskkill /PID %%a /F >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3006 " ^| findstr "LISTENING"') do (
    echo Stopping Audit Service (PID: %%a)
    taskkill /PID %%a /F >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8080 " ^| findstr "LISTENING"') do (
    echo Stopping Payment UI (PID: %%a)
    taskkill /PID %%a /F >nul 2>&1
)

echo.
echo ===============================================
echo   All services stopped!
echo ===============================================
echo.

pause
