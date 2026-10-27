@echo off
title SITEGUARD V1 - Original (Port 5000)
color 0A
echo ============================================================
echo   SITEGUARD V1 - Original Construction Safety Monitor
echo   Port: 5000  ^|  http://127.0.0.1:5000
echo ============================================================
echo.
cd /d "%~dp0SAFETY-MANAGEMENT-CONSTRUCTION"
set VENV="%~dp0.venv\Scripts\python.exe"
echo [OK] Starting V1 on port 5000...
echo.
%VENV% main.py
pause
