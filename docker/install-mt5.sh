#!/usr/bin/env bash
# Descarga e instala MetaTrader 5 en el prefijo Wine (silencioso).
#
# Si la instalación silenciosa no funciona (el instalador de MT5 cambia
# de versión sin avisar), NO falla: deja el instalador cacheado en
# /opt/mt5setup.exe y el entrypoint lo lanza en modo gráfico para
# completarlo desde noVNC la primera vez.
set -Eeuo pipefail

INSTALLER=/opt/mt5setup.exe
# URL oficial actual (metatrader5.com/en/download). La vieja
# download.mt5setup.com dejó de existir; la dejamos como fallback.
URLS=(
  "https://download.terminal.free/cdn/web/metaquotes.ltd/mt5/mt5setup.exe"
  "https://download.mt5setup.com/"
)
WINEPREFIX="${WINEPREFIX:-/wineprefix}"

find_mt5() {
  find "${WINEPREFIX}/drive_c" -iname terminal64.exe -print -quit 2>/dev/null || true
}

if [ -n "$(find_mt5)" ]; then
  echo "[mt5] ya instalado → $(find_mt5)"
  exit 0
fi

if [ ! -s "${INSTALLER}" ]; then
  ok=0
  for url in "${URLS[@]}"; do
    echo "[mt5] descargando ${url}..."
    if curl -fsSL --retry 3 --connect-timeout 20 -o "${INSTALLER}.tmp" "${url}"; then
      # Sanity check: debe ser un PE de Windows, no una página de error
      if head -c 2 "${INSTALLER}.tmp" | grep -q 'MZ'; then
        mv "${INSTALLER}.tmp" "${INSTALLER}"
        ok=1
        break
      fi
      echo "[mt5] la descarga no parece un .exe válido, pruebo otra fuente"
      rm -f "${INSTALLER}.tmp"
    fi
  done
  if [ "${ok}" != "1" ]; then
    echo "[mt5] ERROR: no se pudo descargar el instalador de MT5."
    exit 1
  fi
fi

attempt() {
  echo "[mt5] instalación silenciosa: $*"
  timeout 240 wine "${INSTALLER}" "$@" >/tmp/mt5-setup.log 2>&1 || true
  timeout 20 wineserver -w >/dev/null 2>&1 || wineserver -k >/dev/null 2>&1 || true
  sleep 2
}

# El instalador actual de MT5 espera interacción incluso con /S: los
# intentos silenciosos solo agregan minutos de timeout. Se dejan detrás
# de MT5_SILENT=1 por si una versión futura los soporta.
if [ "${MT5_SILENT:-0}" = "1" ]; then
  attempt /S
  if [ -z "$(find_mt5)" ]; then
    attempt /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
  fi
fi

if [ -n "$(find_mt5)" ]; then
  echo "[mt5] instalado → $(find_mt5)"
else
  echo "[mt5] la instalación silenciosa no confirmó terminal64.exe."
  echo "[mt5] Se usará el instalador interactivo (noVNC) en el primer arranque."
  echo "[mt5] log:"
  tail -n 20 /tmp/mt5-setup.log 2>/dev/null || true
fi
exit 0
