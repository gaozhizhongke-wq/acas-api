@echo off
chcp 65001 >nul
echo ==========================================
echo ACAS v2 - 本地开发模式 (无需 Docker)
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found in PATH
    pause
    exit /b 1
)

REM Check if in correct directory
if not exist "src\api\main.py" (
    echo Error: Please run this script from acas-v2 directory
    pause
    exit /b 1
)

REM Check if dependencies installed
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install dependencies
        pause
        exit /b 1
    )
)

echo Starting ACAS v2 in development mode...
echo.

python start_dev.py

pause
