#!/usr/bin/env bash
# Instala Python de Windows (con pip) dentro del prefijo Wine.
# Idempotente: si ya está instalado, no hace nada.
set -Eeuo pipefail

VER="${PYTHON_VERSION:-3.12.10}"
WINEPREFIX="${WINEPREFIX:-/wineprefix}"
PYDIR="${WINEPREFIX}/drive_c/Python312"
INSTALLER=/opt/python-installer.exe
URL="https://www.python.org/ftp/python/${VER}/python-${VER}-amd64.exe"

if [ -x "${PYDIR}/python.exe" ]; then
  echo "[py] ya instalado en ${PYDIR}"
  exit 0
fi

echo "[py] descargando Python ${VER}..."
curl -fsSL --retry 3 --connect-timeout 20 -o "${INSTALLER}" "${URL}"

echo "[py] instalando en C:\\Python312 (silencioso)..."
timeout 300 wine "${INSTALLER}" /quiet \
  InstallAllUsers=1 PrependPath=0 Include_test=0 Include_pip=1 \
  Include_doc=0 Shortcuts=0 AssociateFiles=0 \
  'TargetDir=C:\Python312' >/tmp/py-setup.log 2>&1 || true
timeout 20 wineserver -w >/dev/null 2>&1 || wineserver -k >/dev/null 2>&1 || true

if [ ! -x "${PYDIR}/python.exe" ]; then
  echo "[py] ERROR: python.exe no se instaló. Último log:"
  tail -n 40 /tmp/py-setup.log 2>/dev/null || true
  exit 1
fi

echo "[py] verificando..."
wine 'C:\Python312\python.exe' --version
wine 'C:\Python312\python.exe' -m pip --version
echo "[py] OK"
