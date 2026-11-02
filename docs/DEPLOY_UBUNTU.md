# Despliegue 24/7 en Ubuntu Server (Docker + Wine + MetaTrader 5)

> **¿Por qué Wine?** La API oficial de MetaTrader 5 solo existe para
> Windows. Este despliegue corre el backend con **Python de Windows dentro
> de Wine**, con MT5 instalado en el mismo prefijo — la misma arquitectura
> que en tu PC, pero headless en tu servidor.

---

## 1. Requisitos

| Requisito | Mínimo | Recomendado |
|---|---|---|
| Ubuntu Server | 22.04 / 24.04 | 24.04 LTS |
| RAM | 2 GB | 4 GB (Wine + MT5 usan ~1.5 GB) |
| Disco | 10 GB libres | 20 GB (imagen + MT5 + backups) |
| Red | acceso a internet (MT5 se conecta a tu bróker) | — |
| Cuenta | MT5 **demo** primero | — |

---

## 2. Instalar Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# cerrá sesión y volvé a entrar (para usar docker sin sudo)
docker version
```

## 3. Clonar y configurar

```bash
git clone https://github.com/EdsonAP1/btc.git ~/btc
cd ~/btc
cp .env.example .env
nano .env        # revisá TZ, AUTOSTART_MODE, etc.
```

**Variables clave de `.env`:**

| Variable | Default | Qué hace |
|---|---|---|
| `AUTOSTART` | `1` | El bot se inicia solo al levantar el contenedor |
| `AUTOSTART_MODE` | `paper` | `paper` (precios reales, dinero virtual) / `live` / `sim` |
| `AUTOSTART_CONFIRM_REAL` | `false` | Poné `true` solo para operar real con confirmación |
| `HTTP_BIND` | `0.0.0.0` | `127.0.0.1` si solo querés acceso por SSH tunnel |
| `VNC_BIND` | `127.0.0.1` | Interfaz de MT5 — **no la expongas a internet** |
| `ENABLE_VNC` | `1` | `0` después de instalar/loguear MT5 |
| `TZ` | `America/La_Paz` | Hora de logs y backups |

## 4. Construir y levantar

```bash
cd ~/btc
docker compose build        # 10-20 min la primera vez (baja Wine, Python, MT5)
docker compose up -d
docker compose logs -f      # Ctrl+C para dejar de seguir los logs
```

En el primer arranque el contenedor:

1. Crea el prefijo Wine e instala **Python de Windows** (si no existe).
2. Instala **MetaTrader 5** (silencioso; si falla, abre el instalador
   gráfico en noVNC para que lo completes — ver paso 5).
3. Arranca el backend en `:8000` y espera a que esté sano.
4. **Auto-arranca el bot** en el modo configurado en `.env`.

## 5. Primera vez: instalar y loguear MT5 (una sola vez)

MT5 necesita una instalación inicial + login con tu cuenta del bróker.
Se hace desde el navegador por **noVNC**:

```bash
# Desde tu PC: abrí un tunnel SSH al servidor
ssh -L 6080:localhost:6080 usuario@IP_DEL_SERVIDOR
```

1. Abrí <http://127.0.0.1:6080/vnc.html> en tu navegador.
2. **Si MT5 no estaba instalado**: verás el instalador → siguiente →
   siguiente → finalizar.
3. En MT5: *Archivo → Abrir una cuenta → tu bróker* → login y contraseña.
   **✅ marcá "Guardar información de la cuenta"** (para el auto-login).
4. Verificá la conexión:

   ```bash
   curl -s http://127.0.0.1:8000/api/health
   # esperado: {"status":"ok","mt5":true, ...}
   ```

5. Reiniciá el contenedor para que el auto-arranque use MT5:

   ```bash
   docker compose restart
   ```

6. Cuando todo funcione: poné `ENABLE_VNC=0` en `.env` y
   `docker compose up -d` (noVNC queda desactivado).

> **Tip:** si preferís, dejá `ENABLE_VNC=1` — el puerto 6080 solo está
> publicado en `127.0.0.1` por defecto, así que desde afuera solo es
> accesible por SSH tunnel.

## 6. Operar

- **Panel:** <http://IP_DEL_SERVIDOR:8000> (o por SSH tunnel si
  `HTTP_BIND=127.0.0.1`).
- **Primera semana en `paper`** (default): precios reales de MT5, dinero
  virtual — validá estrategia y entorno sin riesgo.
- **Para pasar a `live`:** editá `.env`:

  ```bash
  AUTOSTART_MODE=live
  AUTOSTART_CONFIRM_REAL=true   # confirmación explícita para cuenta REAL
  ```

  y `docker compose up -d` para aplicar. El bot **no opera en real sin
  esa confirmación** (y si la cuenta es demo, no la pide).

- **Detener sin apagar el servidor:** `docker compose stop`
- **Apagar todo:** `docker compose down` (los volúmenes con datos se
  conservan).

## 7. Operación 24/7

| Mecanismo | Qué garantiza |
|---|---|
| `restart: unless-stopped` | El contenedor levanta solo tras crash o reboot del servidor |
| Health-check (`/api/health`) | Docker marca unhealthy si el API no responde |
| Watchdog del entrypoint | Reinicia el contenedor si el API falla 3 veces seguidas o uvicorn muere |
| Auto-arranque del bot | Cada vez que el contenedor levanta, el bot arranca en el modo de `.env` |
| Backup diario de `bot.db` | Copia a `backups/bot-YYYY-MM-DD.db` (retención configurable) |
| Logs rotados (10MB × 5) | Los logs nunca llenan el disco |

El **pico de equity** (drawdown) y los trades se persisten en SQLite, así
que los límites de riesgo sobreviven reinicios.

### Comandos útiles

```bash
docker compose ps                    # estado
docker compose logs -f --tail 100    # logs recientes
docker compose restart               # reiniciar (bot relanza solo)
docker compose exec btc-bot curl -s http://127.0.0.1:8000/api/status
docker compose exec btc-bot ls /app/backend/data/backups
docker stats                         # CPU/RAM
```

### Actualizar el bot

```bash
cd ~/btc && git pull
docker compose build && docker compose up -d
# los datos (bot.db, config, sesión MT5) viven en volúmenes: no se pierden
```

### Copiar los backups a tu PC

```bash
scp usuario@IP:/tmp/bot-backups/* .   # o desde el contenedor:
docker compose cp btc-bot:/app/backend/data/backups ./backups
```

## 8. Seguridad

- **La API no tiene autenticación** (pensada para localhost). Nunca la
  expongas a internet: usá `HTTP_BIND=127.0.0.1` + SSH tunnel, o Tailscale/
  WireGuard para acceder desde tus dispositivos.
- `VNC_BIND=127.0.0.1` por defecto — **no lo cambies a 0.0.0.0** si tu
  red no es privada (el VNC no tiene contraseña).
- Si exponés el panel en la LAN, limitá con firewall:

  ```bash
  sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp
  ```

## 9. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `docker compose build` falla en Python/MT5 | Red o cambio del instalador | Reintentá; mirá `docker compose build --progress=plain` |
| `wine: unimplemented function ucrtbase.dll.crealf` | Wine viejo (el de los repos de Ubuntu, 9.0, no implementa `crealf`; lo necesitan numpy y MT5) | La imagen ya instala **WineHQ 11.0** — reconstruí con `docker compose build --no-cache` y asegurate de tener conectividad a `dl.winehq.org` |
| `"mt5": false` en health | MT5 no instalado o sin login | Abrí noVNC (paso 5), instalá y logueá; `docker compose restart` |
| El bot no arranca solo | `AUTOSTART=0` o start falló | Mirá `docker compose logs` — el motivo queda en el log |
| `MT5 no conectado` en logs | Terminal cerrado o cuenta desconectada | Entrá por noVNC, revisá MT5, reiniciá |
| El bot se detiene por riesgo | Límite de drawdown/diario alcanzado | Revisá panel → riesgo; subí límites en Ajustes si corresponde |
| `cotas de recursos` / contenedor killed | RAM insuficiente | Subí RAM o bajá `shm_size` |
| Wine/MT5 se rompe tras update | MT5 auto-actualizó | `docker compose down && docker volume rm btc-bot-wineprefix && docker compose build && docker compose up -d` → **repetir paso 5** (login) |
| Quiero empezar de cero con datos | — | `docker compose down && docker volume rm btc-bot-data` (borra trades y config) |

### Diagnóstico rápido

```bash
docker compose exec btc-bot bash -c 'ls /wineprefix/drive_c/ | head'
docker compose exec btc-bot bash -c 'wine "C:\Python312\python.exe" -c "import MetaTrader5; print(MetaTrader5.__version__)"'
docker compose exec btc-bot curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
```
