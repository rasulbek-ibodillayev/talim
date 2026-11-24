@echo off
cd /d "%~dp0"
start "Sayt" cmd /k "venv\Scripts\activate && python app.py"
timeout /t 3 >nul
start http://127.0.0.1:8000
