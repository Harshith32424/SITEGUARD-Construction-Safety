@echo off
title SITEGUARD V2 - Premium Metallic Edition (Port 5001)
color 03
echo ============================================================
echo   SITEGUARD V2 - Premium Metallic Chic Edition
echo   Port: 5001  ^|  http://127.0.0.1:5001
echo   Run create_supervisor.py FIRST if first-time setup
echo ============================================================
echo.
cd /d "%~dp0version-2"
set VENV="%~dp0.venv\Scripts\python.exe"
echo [OK] Starting V2 on port 5001...
echo.
%VENV% app_v2.py
pause
