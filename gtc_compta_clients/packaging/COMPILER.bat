@echo off
chcp 1252 >nul
REM ===========================================================
REM  GTC Comptabilite Clients - compilation Windows (PyInstaller)
REM  Resultat : packaging\dist\GTC_Compta_Clients\GTC_Compta_Clients.exe
REM ===========================================================
cd /d "%~dp0"
if exist "C:\Program Files\PyManager\python.exe" (
    set "PYTHON=C:\Program Files\PyManager\python.exe"
    goto :python_ok
)
python --version >nul 2>&1 && set "PYTHON=python" && goto :python_ok
py --version >nul 2>&1 && set "PYTHON=py" && goto :python_ok
echo [ERREUR] Python 3 introuvable. Installer Python 3.11 ou plus recent.
pause
exit /b 1
:python_ok
echo [1/3] Installation des dependances...
"%PYTHON%" -m pip install -r ..\requirements-dev.txt
if errorlevel 1 goto :erreur
echo [2/3] Tests automatiques...
pushd ..
"%PYTHON%" -m pytest -q
if errorlevel 1 (
    popd
    goto :erreur
)
popd
echo [3/3] Compilation...
"%PYTHON%" -m PyInstaller --noconfirm --clean --distpath dist --workpath work gtc_compta.spec
if errorlevel 1 goto :erreur
copy /Y ..\config.example.json dist\GTC_Compta_Clients\config.json >nul
echo.
echo [OK] Application : packaging\dist\GTC_Compta_Clients\GTC_Compta_Clients.exe
echo      Editer config.json (mode sql, serveur, bases) avant la premiere utilisation.
pause
exit /b 0
:erreur
echo [ERREUR] Compilation interrompue.
pause
exit /b 1
