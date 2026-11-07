@echo off
cd /d C:\Users\Admin\Desktop\newSite
start "Sayt" cmd /k "venv\Scripts\activate && python app.py"
start "Bot" cmd /k "venv\Scripts\activate && python bot.py"
timeout /t 3 >nul
start http://127.0.0.1:8000