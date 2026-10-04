@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
    if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist .env copy .env.example .env >nul
.venv\Scripts\python.exe AI_Video_Studio_V7_5_Backend_V4Voice.py
pause
exit /b
:fail
echo Khong khoi tao duoc. Kiem tra Python va ket noi mang.
pause
exit /b 1
