@echo off
title metastrip (phone mode)
rem open the QR page once the server has had a moment to start
start "" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:8377/phone"
"%~dp0.venv\Scripts\python.exe" -m metastrip.webapp --lan
pause
