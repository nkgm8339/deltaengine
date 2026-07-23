@echo off
chcp 65001 >nul
setlocal
title DeltaEngine 30M Launcher

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0DeltaEngine30M-Manager.ps1" -Action Start
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo DeltaEngine 30M startup failed. No 1M process or data was modified.
    pause
)
exit /b %EXIT_CODE%
