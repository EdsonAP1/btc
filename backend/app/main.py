"""Punto de entrada: FastAPI + estáticos del frontend."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import ensure_config_file, load_config
from .db import Store
from .engine import Engine
from .market import Market

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("btc-bot")

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
DIST_DIR = PROJECT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = ensure_config_file()
    store = Store()
    market = Market(cfg)
    engine = Engine(store, market, cfg)

    app.state.store = store
    app.state.market = market
    app.state.engine = engine

    # Intento de conexión temprano, sin bloquear el arranque si falla.
    try:
        await asyncio.to_thread(market.mt5_available)
        log.info("MT5 conectado: %s · símbolo %s", market.client.connected, market.symbol)
    except Exception as exc:  # noqa: BLE001
        log.warning("MT5 no disponible (%s). Se usará modo simulado para datos.", exc)

    yield

    await engine.stop()
    store.close()
    try:
        market.client.disconnect()
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title="BTC Trading Bot", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def index():
    if DIST_DIR.exists():
        return FileResponse(DIST_DIR / "index.html")
    return JSONResponse(
        {
            "name": "BTC Trading Bot API",
            "docs": "/docs",
            "hint": "El frontend no está compilado. Ejecutá `npm run build` en frontend/ o usá el dev server en :5173",
        }
    )


if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        candidate = DIST_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")


def run() -> None:
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        "app.main:app",
        host=cfg["server"]["host"],
        port=int(cfg["server"]["port"]),
        reload=False,
    )


if __name__ == "__main__":
    run()
