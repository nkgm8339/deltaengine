@echo off
chcp 65001 >nul
setlocal
title DeltaEngine 30M Stop

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0DeltaEngine30M-Manager.ps1" -Action Stop
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
