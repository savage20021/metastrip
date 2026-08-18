@echo off
title metastrip
rem open the app once the server has had a moment to start
start "" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:8377"
"%~dp0.venv\Scripts\python.exe" -m metastrip.webapp
pause
