@echo off
REM Setup Script for Multi-Course Attendance Management Portal (Windows)
REM This script creates a virtual environment, installs dependencies, and initializes the database

echo ================================================================
echo   Multi-Course Attendance Management Portal - Setup Script
echo ================================================================
echo.

REM Navigate to script directory
cd /d "%~dp0"

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python 3 and try again.
    pause
    exit /b 1
)

echo Python found
echo.

REM Create virtual environment
echo Creating virtual environment...
if exist "venv" (
    echo Virtual environment already exists. Skipping creation.
) else (
    python -m venv venv
    echo Virtual environment created
)
echo.

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
echo Virtual environment activated
echo.

REM Install dependencies for Module-B
echo Installing dependencies for Module-B...
cd Module-B
python -m pip install --upgrade pip
pip install -r requirements.txt
echo Dependencies installed
echo.

REM Initialize database
echo Initializing database...
python init_db.py
echo Database initialized
echo.

REM Success message
echo ================================================================
echo                    Setup Complete!
echo ================================================================
echo.
echo To start the application:
echo.
echo   1. Activate the virtual environment (if not already active):
echo      venv\Scripts\activate.bat
echo.
echo   2. Navigate to Module-B:
echo      cd Module-B
echo.
echo   3. Run the application:
echo      python run.py
echo.
echo   4. Open your browser and visit:
echo      http://localhost:5050
echo.
echo Default credentials:
echo   Username: admin
echo   Password: password123
echo.
echo ================================================================
pause
