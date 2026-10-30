@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   BTC Bot - instalacion
echo ============================================================
echo.

REM ---------------------------------------------------------- 1. Python
echo [1/7] Verificando Python...
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: No se encontro Python.
    echo Instalalo desde https://www.python.org/downloads/ y marca "Add Python to PATH".
    goto :fail
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo.
    echo ERROR: Se necesita Python 3.10 o superior.
    python --version
    goto :fail
)
python -c "import sys; sys.exit(1 if 'WindowsApps' in sys.executable else 0)"
if errorlevel 1 (
    echo.
    echo ERROR: El Python de la Microsoft Store no sirve para crear entornos virtuales.
    echo Instala Python desde python.org.
    goto :fail
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo       %%v

REM ---------------------------------------------------------- 2. Node
echo [2/7] Verificando Node.js...
where node >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: No se encontro Node.js.
    echo Instalalo desde https://nodejs.org/ ^(version 18 o superior^).
    goto :fail
)
node -e "process.exit(process.versions.node.split('.')[0] >= 18 ? 0 : 1)"
if errorlevel 1 (
    echo.
    echo ERROR: Se necesita Node.js 18 o superior.
    node --version
    goto :fail
)
node --version

REM ---------------------------------------------------------- 3. venv
echo [3/7] Entorno virtual...
if exist ".venv\Scripts\python.exe" (
    echo       .venv ya existe, se reutiliza.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: no se pudo crear el entorno virtual.
        goto :fail
    )
    echo       .venv creado.
)

REM ---------------------------------------------------------- 4. pip
echo [4/7] Dependencias de Python...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 (
    echo.
    echo ERROR: fallo la instalacion de dependencias de Python.
    goto :fail
)

REM ---------------------------------------------------------- 5. npm
echo [5/7] Dependencias del frontend...
pushd "frontend"
if exist "node_modules" (
    echo       node_modules ya existe, se reutiliza.
) else (
    call npm install --no-fund --no-audit
    if errorlevel 1 (
        popd
        echo.
        echo ERROR: fallo npm install.
        goto :fail
    )
)

REM ---------------------------------------------------------- 6. build
echo [6/7] Compilando el panel...
call npm run build
if errorlevel 1 (
    popd
    echo.
    echo ERROR: fallo la compilacion del frontend.
    goto :fail
)
popd

REM ---------------------------------------------------------- 7. config
echo [7/7] Configuracion y MetaTrader...
if not exist "backend\config.json" (
    ".venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'backend'); from app.config import ensure_config_file; ensure_config_file()"
    echo       config.json creado con valores por defecto.
) else (
    echo       config.json ya existe.
)

set "MT5="
if exist "%ProgramFiles%\MetaTrader 5\terminal64.exe" set "MT5=%ProgramFiles%\MetaTrader 5\terminal64.exe"
if exist "%ProgramFiles(x86)%\MetaTrader 5\terminal64.exe" set "MT5=%ProgramFiles(x86)%\MetaTrader 5\terminal64.exe"
if defined MT5 (
    echo       MetaTrader 5 encontrado.
) else (
    echo       AVISO: no se encontro MetaTrader 5.
    echo       El modo Simulado funciona igual; para operar hace falta el
    echo       terminal abierto y con la sesion iniciada.
)

echo.
echo ============================================================
echo   Instalacion completa.
echo.
echo   Para arrancar:  start.bat
echo   Panel:          http://127.0.0.1:8000
echo ============================================================
echo.
pause
exit /b 0

:fail
echo.
echo ============================================================
echo   La instalacion se detuvo por un error.
echo ============================================================
pause
exit /b 1
