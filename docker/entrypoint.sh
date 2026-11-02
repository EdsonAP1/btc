#!/usr/bin/env bash
# ==============================================================
#  BTC Bot · entrypoint del contenedor
#
#  1. Xvfb (pantalla virtual) + noVNC opcional
#  2. Prefijo Wine: Python y MT5 (instalación perezosa)
#  3. Backend (uvicorn con Python de Windows vía Wine)
#  4. Watchdog: health-check, auto-arranque del bot, backup diario
# ==============================================================
set -uo pipefail

log() { echo "[entrypoint $(date '+%Y-%m-%d %H:%M:%S')] $*"; }

export WINEPREFIX="${WINEPREFIX:-/wineprefix}"
export WINEARCH=win64
export WINEDEBUG=-all
export DISPLAY=:99
export WINEDLLOVERRIDES=mscoree,mshtml=
# La config vive en el volumen de datos (se crea sola con defaults).
export BTC_BOT_CONFIG='Z:\app\backend\data\config.json'

PORT="${PORT:-8000}"
BASE="http://127.0.0.1:${PORT}"
PY='C:\Python312\python.exe'
PY_EXE="${WINEPREFIX}/drive_c/Python312/python.exe"
MARKER=/tmp/btc-autostart.done

cd /app || exit 1

find_mt5() {
  find "${WINEPREFIX}/drive_c" -iname terminal64.exe -print -quit 2>/dev/null || true
}

# ---------------------------------------------------------------- 1) Xvfb
if ! pgrep -f "Xvfb :99" >/dev/null 2>&1; then
  log "iniciando Xvfb (display :99)"
  Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp -ac >/tmp/xvfb.log 2>&1 &
  sleep 1
fi

# ---------------------------------------------------------------- 2) noVNC
if [ "${ENABLE_VNC:-1}" = "1" ]; then
  if ! pgrep -f x11vnc >/dev/null 2>&1; then
    x11vnc -display :99 -forever -shared -nopw -rfbport 5900 -quiet \
      >/tmp/x11vnc.log 2>&1 &
  fi
  if ! pgrep -f websockify >/dev/null 2>&1; then
    websockify --web /usr/share/novnc 6080 localhost:5900 \
      >/tmp/websockify.log 2>&1 &
  fi
  log "noVNC en el puerto 6080 → http://<servidor>:6080/vnc.html"
fi

# ------------------------------------------------- 3) Python (perezoso)
if [ ! -x "${PY_EXE}" ]; then
  log "Python de Windows ausente → instalando (solo la primera vez)"
  xvfb-run -a /opt/docker/install-python.sh || log "ERROR: falló la instalación de Python"
fi

REQ=/opt/requirements.txt
STAMP="${WINEPREFIX}/.reqstamp"
if [ -x "${PY_EXE}" ] && [ -f "${REQ}" ]; then
  new_stamp=$(md5sum "${REQ}" | awk '{print $1}')
  if [ "$(cat "${STAMP}" 2>/dev/null || true)" != "${new_stamp}" ]; then
    log "requirements cambió → actualizando dependencias Python..."
    if wine "${PY}" -m pip install --no-warn-script-location -r 'Z:\opt\requirements.txt'; then
      echo "${new_stamp}" > "${STAMP}"
      log "dependencias al día"
    else
      log "AVISO: pip falló; se reintentará en el próximo arranque"
    fi
  fi
fi

# ------------------------------------------------------ 4) MT5 (perezoso)
if [ -z "$(find_mt5)" ]; then
  log "MetaTrader 5 no está instalado en el prefijo"
  MT5_SILENT=0 xvfb-run -a /opt/docker/install-mt5.sh || true
  if [ -z "$(find_mt5)" ]; then
    if [ "${ENABLE_VNC:-1}" = "1" ] && [ -f /opt/mt5setup.exe ]; then
      log "lanzando el instalador GRÁFICO → completalo desde noVNC y reiniciá el contenedor"
      wine /opt/mt5setup.exe >/tmp/mt5-gui.log 2>&1 &
    else
      log "AVISO: MT5 sin instalar. Activá ENABLE_VNC=1 para instalarlo desde el navegador."
    fi
  else
    log "MT5 instalado ✓ ($(find_mt5))"
  fi
fi

# ----------------------------------------------------------- 5) backend
log "iniciando backend (uvicorn) en :${PORT}"
wine "${PY}" -m uvicorn app.main:app --app-dir 'Z:\app\backend' \
  --host 0.0.0.0 --port "${PORT}" --no-access-log &
API_PID=$!

cleanup() {
  log "señal de parada recibida → cerrando backend"
  kill "${API_PID}" 2>/dev/null
  pkill -f 'app.main:app' 2>/dev/null
  exit 0
}
trap cleanup INT TERM

# --------------------------------------------------------- 6) salud API
log "esperando el API (máx 180s)..."
api_ok=0
for _ in $(seq 1 180); do
  if curl -fsS --max-time 3 "${BASE}/api/health" >/dev/null 2>&1; then
    api_ok=1
    break
  fi
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    log "ERROR: el backend murió al arrancar"
    exit 1
  fi
  sleep 1
done
if [ "${api_ok}" = "1" ]; then
  log "API respondiendo ✓"
else
  log "AVISO: el API no respondió en 180s; el monitoreo sigue igual"
fi

# -------------------------------------------------- 7) auto-arranque
autostart() {
  [ "${AUTOSTART:-1}" = "1" ] || { log "AUTOSTART=0 → bot no se auto-arranca"; return 0; }
  [ ! -f "${MARKER}" ] || return 0

  local mode="${AUTOSTART_MODE:-paper}"
  local confirm="${AUTOSTART_CONFIRM_REAL:-false}"
  local tries=0 code

  # En live, esperamos a que MT5 conecte (el terminal se lanza solo).
  if [ "${mode}" = "live" ]; then
    log "live: esperando conexión con MT5 (máx 5 min)..."
    local i=0 mt5ok=""
    while [ "${i}" -lt 30 ]; do
      mt5ok=$(curl -fsS --max-time 5 "${BASE}/api/health" 2>/dev/null \
        | grep -o '"mt5":[a-z]*' | head -n1 | cut -d: -f2 || true)
      [ "${mt5ok}" = "true" ] && break
      i=$((i + 1))
      sleep 10
    done
    [ "${mt5ok}" = "true" ] || log "AVISO: MT5 no conectó todavía. Entrá al terminal (noVNC) y reiniciá."
  fi

  while [ "${tries}" -lt 10 ]; do
    tries=$((tries + 1))
    code=$(curl -sS --max-time 60 -o /tmp/autostart.json -w '%{http_code}' \
      -X POST "${BASE}/api/bot/start" -H 'Content-Type: application/json' \
      -d "{\"mode\":\"${mode}\",\"confirm_real\":${confirm}}" 2>/dev/null || echo 000)
    if [ "${code}" = "200" ]; then
      log "bot auto-arrancado en modo ${mode} ✓"
      touch "${MARKER}"
      return 0
    fi
    log "auto-arranque ${tries}/10 → HTTP ${code}: $(head -c 300 /tmp/autostart.json 2>/dev/null || true)"
    sleep 30
  done
  log "AVISO: no se pudo auto-arrancar. Arrancalo desde el panel cuando MT5 esté listo."
  touch "${MARKER}"
}
if [ "${api_ok}" = "1" ]; then
  autostart
fi

# -------------------------------------------- 8) monitoreo + backup
bh=$((10#${BACKUP_HOUR:-4}))
bk=$((10#${BACKUP_KEEP:-7}))
fails=0
last_backup=""
log "monitoreo activo · backup diario ≥ ${bh}h · retención ${bk} días"
while true; do
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    log "ERROR: uvicorn terminó inesperadamente → reiniciando contenedor"
    exit 1
  fi

  if curl -fsS --max-time 5 "${BASE}/api/health" >/dev/null 2>&1; then
    fails=0
  else
    fails=$((fails + 1))
    log "aviso: API sin responder (${fails}/3)"
    if [ "${fails}" -ge 3 ]; then
      log "ERROR: API inservible tras 3 intentos → reiniciando contenedor"
      exit 1
    fi
  fi

  today=$(date +%F)
  hour=$((10#$(date +%H)))
  if [ "${today}" != "${last_backup}" ] && [ "${hour}" -ge "${bh}" ]; then
    if [ -f /app/backend/data/bot.db ]; then
      mkdir -p /app/backend/data/backups
      if sqlite3 /app/backend/data/bot.db \
          ".backup '/app/backend/data/backups/bot-${today}.db'"; then
        last_backup="${today}"
        log "backup: backups/bot-${today}.db"
        find /app/backend/data/backups -name 'bot-*.db' -mtime "+${bk}" -delete 2>/dev/null
      else
        log "AVISO: backup falló (se reintenta en 60s)"
        sleep 60
      fi
    else
      last_backup="${today}"
    fi
  fi

  sleep 20
done
