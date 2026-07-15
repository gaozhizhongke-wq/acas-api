@echo off
chcp 65001 >nul
echo ==========================================
echo ACAS v2 - Africa Commodity Analytics System
echo ==========================================
echo.

REM Check if running in correct directory
if not exist "docker-compose.yml" (
    echo Error: docker-compose.yml not found in current directory
    echo Please run this script from the acas-v2 directory
echo.
    pause
    exit /b 1
)

echo Starting ACAS v2 services...
echo This will start: PostgreSQL, Redis, and API server
echo.

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo Error: Docker is not running or not installed
    echo Please start Docker Desktop first
    pause
    exit /b 1
)

echo Docker is running, starting services...
docker-compose up -d

if errorlevel 1 (
    echo.
    echo Error starting services. Trying to build first...
    docker-compose build
    docker-compose up -d
)

echo.
echo ==========================================
echo Services started!
echo.
echo API:        http://localhost:8000
echo Health:     http://localhost:8000/health
echo Docs:       http://localhost:8000/docs
echo Prometheus: http://localhost:9090
echo.
echo To view logs: docker-compose logs -f api
echo To stop:      docker-compose down
echo ==========================================
pause
