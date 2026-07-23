@echo off
chcp 65001 >nul
setlocal
title DeltaEngine 1M Launcher

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0DeltaEngine1M-Manager.ps1" -Action Start
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo DeltaEngine 1M startup failed. Nothing outside the 1M product was stopped.
    pause
)
exit /b %EXIT_CODE%
