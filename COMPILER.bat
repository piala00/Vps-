@echo off
title NEXORA - Compilation
color 0A
echo.
echo  ======================================
echo     NEXORA v2.0 - Compilation
echo  ======================================
echo.

REM Verifier Python
python --version >nul 2>&1 || (echo Python requis & pause & exit /b 1)

REM Installer PyInstaller
echo [1/4] Installation PyInstaller...
pip install pyinstaller --quiet

REM Compiler NEXORA.exe
echo [2/4] Compilation NEXORA.exe...
pyinstaller NEXORA.spec --clean --noconfirm
if errorlevel 1 (echo Erreur compilation & pause & exit /b 1)

REM Compiler le launcher C++
echo [3/4] Compilation launcher C++...
where g++ >nul 2>&1 && (
    g++ -o dist\NEXORA_Setup_Launcher.exe installer\setup_builder.cpp ^
        -mwindows -static -lshlwapi
) || (
    echo g++ non trouve - skipping C++ compilation
)

REM Instructions Inno Setup
echo [4/4] Pour creer le setup.exe :
echo   1. Installer Inno Setup depuis jrsoftware.org
echo   2. Ouvrir installer\nexora_setup.iss
echo   3. Compiler avec Ctrl+F9
echo.
echo Compilation terminee !
echo    NEXORA.exe se trouve dans : dist\
pause
