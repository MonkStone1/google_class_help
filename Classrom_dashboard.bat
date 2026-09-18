@echo off
title Google Class Help

echo ========================================
echo       Google Class Help
echo ========================================
echo.

cd /d D:\Documents\google_class_help

echo [1/2] Starting backend...
start "Google Class Help - Backend" cmd /k "cd /d D:\Documents\google_class_help\backend && ..\.venv\Scripts\activate.bat && uvicorn main:app --reload"

timeout /t 3 /nobreak >nul

echo [2/2] Starting frontend...
start "Google Class Help - Frontend" cmd /k "cd /d D:\Documents\google_class_help\frontend && npm run dev"

echo.
echo ========================================
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://localhost:5173
echo ========================================
echo.
echo Both servers have been started.
pause