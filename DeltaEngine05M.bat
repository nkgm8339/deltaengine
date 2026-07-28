@echo off
chcp 65001 > nul
setlocal

set "ROOT=%~dp0"
set "PROJ=%ROOT%Delta_Engine_Pro4web"
set "COMPOSE_PROJECT_NAME=delta_engine_pro4web"
set "URL=http://localhost:18080"

if /i "%1"=="stop" goto :stop

echo ==============================
echo  DeltaEngine05M  Starting...
echo ==============================

cd /d "%PROJ%"
if errorlevel 1 (
    echo ERROR: Delta_Engine_Pro4web folder not found: %PROJ%
    pause
    exit /b 1
)

docker info > nul 2>&1
if errorlevel 1 (
    echo Docker Desktop is not running. Please start it first.
    pause
    exit /b 1
)

docker rm -f deltaengine_05m-deltaengine_clone-1 > nul 2>&1
docker compose -p delta_engine_pro4web up --build -d
if errorlevel 1 (
    echo docker compose up failed.
    pause
    exit /b 1
)

echo Waiting for server...
:wait
timeout /t 2 /nobreak > nul
curl -s -o nul -w "%%{http_code}" "%URL%/health" 2>nul | findstr "200" > nul
if errorlevel 1 goto :wait

echo ==============================
echo  Ready: %URL%
echo  To stop: DeltaEngine05M.bat stop
echo ==============================
start "" "%URL%"
goto :eof

:stop
echo Stopping DeltaEngine...
cd /d "%PROJ%"
docker compose -p delta_engine_pro4web down
echo Stopped.
pause
goto :eof

