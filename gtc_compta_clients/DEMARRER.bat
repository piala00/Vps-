@echo off
chcp 1252 >nul
cd /d "%~dp0"
if exist "C:\Program Files\PyManager\python.exe" (
    "C:\Program Files\PyManager\python.exe" run.py
) else (
    python run.py
)
if errorlevel 1 pause
