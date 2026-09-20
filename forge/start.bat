@echo off
title Forge - AI Code Graph
color 0A

echo.
echo ===============================================
echo   Forge - AI Code Graph
echo   Starting backend...
echo ===============================================
echo.

REM %~dp0 already has a trailing backslash and this script lives inside forge\
set FORGE_DIR=%~dp0
set VENV_PYTHON=%FORGE_DIR%code_graph\venv\Scripts\python.exe
set FRONTEND_DIR=%FORGE_DIR%frontend\dist

REM ── Check venv exists ──────────────────────────────────────────────────────
if not exist "%VENV_PYTHON%" (
    echo ERROR: Virtual environment not found.
    echo Run: cd forge\code_graph ^&^& python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM ── Check graph database exists ────────────────────────────────────────────
if not exist "%FORGE_DIR%..\data\code_graph.kuzu" (
    echo WARNING: Graph database not found at ..\data\code_graph.kuzu
    echo Run: cd forge\code_graph ^&^& python visualize_graph.py
    echo.
    echo Continuing anyway - the server will warn on startup.
    echo.
)

REM ── Check frontend is built ────────────────────────────────────────────────
if not exist "%FRONTEND_DIR%\index.html" (
    echo Frontend not built. Building now...
    echo.
    cd /d "%FORGE_DIR%..\hsbc_CodeGraph_test\frontend"
    call npm install --silent
    call npm run build
    if errorlevel 1 (
        echo ERROR: Frontend build failed. Check Node.js is installed.
        pause
        exit /b 1
    )
    cd /d "%FORGE_DIR%"
    echo Frontend built successfully.
    echo.
)

REM ── Start FastAPI backend ──────────────────────────────────────────────────
echo [1/1] Starting Forge API + UI (Port 8000)...
start "Forge API - 8000" /D "%FORGE_DIR%" cmd /c "%VENV_PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul

echo.
echo ===============================================
echo   Forge is running!
echo ===============================================
echo.
echo   Graph Explorer:   http://localhost:8000
echo   Impact Analyst:   http://localhost:8000  (click tab)
echo   API Docs:         http://localhost:8000/docs
echo.
echo ===============================================
echo   Opening browser...
echo ===============================================
echo.

timeout /t 2 /nobreak >nul
start http://localhost:8000

echo Press any key to exit this window.
echo (Forge server will continue running in its own window)
pause >nul
