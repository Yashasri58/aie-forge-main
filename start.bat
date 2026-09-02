@echo off
title Cross-Border Wire Transfer System - Startup
color 0A

echo.
echo ===============================================
echo   Cross-Border Wire Transfer System
echo   Starting all services...
echo ===============================================
echo.

cd /d "%~dp0services"

echo [1/8] Starting Account Service (Port 3001)...
start "Account Service - 3001" /D "account-service" cmd /c "npm start"
timeout /t 2 /nobreak >nul

echo [2/8] Starting FX Service (Port 3005)...
start "FX Service - 3005" /D "fx-service" cmd /c "npm start"
timeout /t 2 /nobreak >nul

echo [3/8] Starting Validation Service (Port 3003)...
start "Validation Service - 3003" /D "validation-service" cmd /c "npm start"
timeout /t 2 /nobreak >nul

echo [4/8] Starting Ledger Service (Port 3004)...
start "Ledger Service - 3004" /D "ledger-service" cmd /c "npm start"
timeout /t 2 /nobreak >nul

echo [5/8] Starting Audit Service (Port 3006)...
start "Audit Service - 3006" /D "audit-service" cmd /c "npm start"
timeout /t 2 /nobreak >nul

echo [6/8] Starting Payment Processor (Port 3002)...
start "Payment Processor - 3002" /D "payment-processor" cmd /c "npm start"
timeout /t 2 /nobreak >nul

echo [7/8] Starting Gateway Service (Port 3000)...
start "Gateway Service - 3000" /D "gateway-service" cmd /c "npm start"
timeout /t 2 /nobreak >nul

echo [8/8] Starting Payment UI (Port 8080)...
start "Payment UI - 8080" /D "payment-ui" cmd /c "npm start"
timeout /t 3 /nobreak >nul

echo.
echo ===============================================
echo   All services started!
echo ===============================================
echo.
echo   Services:
echo   - Account Service:     http://localhost:3001
echo   - Payment Processor:   http://localhost:3002
echo   - Validation Service:  http://localhost:3003
echo   - Ledger Service:      http://localhost:3004
echo   - FX Service:          http://localhost:3005
echo   - Audit Service:       http://localhost:3006
echo   - Gateway (API):       http://localhost:3000
echo   - Web UI:              http://localhost:8080
echo.
echo ===============================================
echo   Opening browser...
echo ===============================================
echo.

timeout /t 2 /nobreak >nul
start http://localhost:8080

echo.
echo Press any key to exit this window...
echo (Services will continue running in their own windows)
pause >nul
