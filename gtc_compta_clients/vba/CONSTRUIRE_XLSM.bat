@echo off
chcp 1252 >nul
REM Construit le classeur macro GTC_PREPARATION_JOURNALIERE.xlsm (Excel requis)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0CONSTRUIRE_XLSM.ps1"
if errorlevel 1 (
  echo [ERREUR] Construction impossible. Verifier : Excel installe et acces au modele VBA autorise.
) else (
  echo [OK] GTC_PREPARATION_JOURNALIERE.xlsm cree.
)
pause
