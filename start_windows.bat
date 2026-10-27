@echo off
title Construction Site Safety Monitor
color 0A

echo ============================================================
echo   CONSTRUCTION SITE SAFETY MONITORING SYSTEM
echo   AI + YOLOv8 + Arduino IoT Gateway
echo ============================================================
echo.

:: Navigate into the actual project subfolder
cd /d "%~dp0SAFETY-MANAGEMENT-CONSTRUCTION"

:: Use the .venv Python from the parent folder
set VENV_PYTHON=%~dp0.venv\Scripts\python.exe

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment not found!
    echo Run:  python -m venv .venv  then  pip install -r requirements.txt
    pause
    exit /b 1
)

echo [OK] venv found: %VENV_PYTHON%
echo [OK] Working dir: %cd%
echo.
echo Starting server on http://127.0.0.1:5000
echo Press Ctrl+C to stop.
echo.

"%VENV_PYTHON%" main.py
pause
