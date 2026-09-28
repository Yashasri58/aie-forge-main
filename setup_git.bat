@echo off
REM Run once before using SYNC_GRAPH_ON_APPROVE=true
set SERVICES_DIR=%~dp0services
if exist "%SERVICES_DIR%\.git" (
    echo [OK] services/ is already a git repository
    goto :eof
)
echo Setting up git repo in %SERVICES_DIR%...
git -C "%SERVICES_DIR%" init
git -C "%SERVICES_DIR%" config user.email "forge-ai@capgemini.com"
git -C "%SERVICES_DIR%" config user.name "Forge AI"
git -C "%SERVICES_DIR%" add -A
git -C "%SERVICES_DIR%" commit -m "Initial state before AI codegen"
echo [DONE] services/ git repo initialized.
