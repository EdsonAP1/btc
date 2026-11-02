# syntax=docker/dockerfile:1
# ==============================================================
#  BTC Bot · Ubuntu Server + Wine + MetaTrader 5 + Python Win
#
#  El backend corre con Python de Windows dentro de Wine porque
#  el paquete oficial MetaTrader5 solo existe para Windows.
#  El frontend se compila en una etapa aparte y se sirve desde
#  FastAPI (mismo puerto, sin dependencias en runtime).
# ==============================================================
ARG PYTHON_VERSION=3.12.10
ARG NODE_VERSION=22

# ---------------------------------------------------------------- frontend
FROM node:${NODE_VERSION}-bookworm AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- backend
FROM ubuntu:24.04
ARG PYTHON_VERSION

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    WINEPREFIX=/wineprefix \
    WINEARCH=win64 \
    WINEDEBUG=-all \
    WINEDLLOVERRIDES=mscoree,mshtml= \
    DISPLAY=:99 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Wine desde el repositorio oficial WineHQ (no el de Ubuntu: ese trae
# Wine 9.0 que NO implementa ucrtbase.dll.crealf, y ni numpy ni el
# instalador de MT5 pueden arrancar sin él — crealf llegó en Wine 10.1+,
# y WineHQ noble trae 11.0). Xvfb = pantalla virtual; noVNC = para
# instalar/loguear MT5 desde el navegador. El prefijo se puebla después.
RUN dpkg --add-architecture i386 \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg \
      xvfb xauth x11vnc novnc websockify \
      procps sqlite3 unzip cabextract \
      fonts-dejavu-core fonts-wine \
 && mkdir -pm755 /etc/apt/keyrings \
 && curl -fsSL -o /etc/apt/keyrings/winehq-archive.key \
      https://dl.winehq.org/wine-builds/winehq.key \
 && curl -fsSL -o /etc/apt/sources.list.d/winehq-noble.sources \
      https://dl.winehq.org/wine-builds/ubuntu/dists/noble/winehq-noble.sources \
 && apt-get update \
 && apt-get install -y --install-recommends winehq-stable \
 && rm -rf /var/lib/apt/lists/* \
 && wine --version

# Prefijo Wine base (se puebla en el primer build; en runtime se
# monta un volumen encima que arranca con esta copia).
RUN mkdir -p /wineprefix \
 && (timeout 120 xvfb-run -a wineboot --init || true) \
 && (timeout 30 wineserver --wait || true)

# ------------------------------------------------- Python de Windows
COPY docker/install-python.sh /opt/docker/install-python.sh
RUN chmod +x /opt/docker/install-python.sh \
 && xvfb-run -a /opt/docker/install-python.sh

# Dependencias de Python (incluye MetaTrader5: wheel win_amd64).
# El hash se guarda para re-sincronizar si requirements.txt cambia
# en un volumen ya existente.
COPY backend/requirements.txt /opt/requirements.txt
RUN xvfb-run -a wine 'C:\Python312\python.exe' -m pip install \
      --no-warn-script-location -r 'Z:\opt\requirements.txt' \
 && md5sum /opt/requirements.txt | awk '{print $1}' > /wineprefix/.reqstamp

# ------------------------------------------------------- MetaTrader 5
COPY docker/install-mt5.sh /opt/docker/install-mt5.sh
RUN chmod +x /opt/docker/install-mt5.sh \
 && MT5_SILENT=0 xvfb-run -a /opt/docker/install-mt5.sh

# --------------------------------------------------------------- app
COPY backend/ /app/backend/
COPY --from=frontend /src/dist /app/frontend/dist/
COPY docker/entrypoint.sh /opt/docker/entrypoint.sh
RUN chmod +x /opt/docker/entrypoint.sh \
 && mkdir -p /app/backend/data

WORKDIR /app
EXPOSE 8000 6080
ENTRYPOINT ["/opt/docker/entrypoint.sh"]
