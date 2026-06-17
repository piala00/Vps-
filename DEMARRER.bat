@echo off
title NEXORA v2.0
color 17
echo.
echo  ======================================
echo         NEXORA v2.0
echo     Hamadou Youssouf - GTC Bertoua
echo  ======================================
echo.

REM Trouver Python
set PYTHON=
for %%P in (python python3 py) do (
    %%P --version >nul 2>&1 && set PYTHON=%%P && goto :found
)
echo Python non trouve. Installez Python depuis python.org
pause & exit /b 1

:found
echo Python trouve : %PYTHON%
echo Installation des dependances...
%PYTHON% -m pip install flask pyodbc openpyxl python-telegram-bot Pillow --quiet

echo Demarrage de NEXORA...
%PYTHON% run.py
if errorlevel 1 (
    echo.
    echo Erreur au demarrage. Verifiez les logs.
    pause
)
