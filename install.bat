@echo off
title Cross-Border Wire Transfer System - Install Dependencies
color 0B

echo.
echo ===============================================
echo   Cross-Border Wire Transfer System
echo   Installing dependencies for all services...
echo ===============================================
echo.

cd /d "%~dp0services"

echo [1/8] Installing Account Service dependencies...
cd account-service
call npm install
cd ..
echo.

echo [2/8] Installing FX Service dependencies...
cd fx-service
call npm install
cd ..
echo.

echo [3/8] Installing Validation Service dependencies...
cd validation-service
call npm install
cd ..
echo.

echo [4/8] Installing Ledger Service dependencies...
cd ledger-service
call npm install
cd ..
echo.

echo [5/8] Installing Audit Service dependencies...
cd audit-service
call npm install
cd ..
echo.

echo [6/8] Installing Payment Processor dependencies...
cd payment-processor
call npm install
cd ..
echo.

echo [7/8] Installing Gateway Service dependencies...
cd gateway-service
call npm install
cd ..
echo.

echo [8/8] Installing Payment UI dependencies...
cd payment-ui
call npm install
cd ..
echo.

echo.
echo ===============================================
echo   All dependencies installed!
echo ===============================================
echo.
echo   You can now run start.bat to launch the system.
echo.

pause
