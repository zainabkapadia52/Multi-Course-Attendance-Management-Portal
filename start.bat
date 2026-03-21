@echo off
REM Quick start script for the application (Windows)
REM Run this after completing setup.bat

cd /d "%~dp0"

REM Check if virtual environment exists
if not exist "venv" (
    echo Virtual environment not found!
    echo Please run setup.bat first
    pause
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Navigate to Module-B and run the app
cd Module-B

echo Starting Multi-Course Attendance Management Portal...
echo Server will run on http://localhost:5050
echo.
echo Press Ctrl+C to stop the server
echo.

python run.py
pause
