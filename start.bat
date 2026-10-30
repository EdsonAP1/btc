@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Falta la instalacion. Ejecuta primero setup.bat
    echo.
    pause
    exit /b 1
)

echo Levantando el bot en http://127.0.0.1:8000 ...
start "BTC Bot - servidor" /D "%~dp0" cmd /k scripts\server.cmd

timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:8000
exit /b 0
