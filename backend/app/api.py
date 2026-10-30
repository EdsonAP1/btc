"""API HTTP + WebSocket del bot."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .config import deep_merge, load_config, patch_config
from .core.backtester import BacktestConfig, run_backtest
from .core.metrics import compute_metrics

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- modelos
class StartRequest(BaseModel):
    mode: str | None = None
    confirm_real: bool = False


class StopRequest(BaseModel):
    close_positions: bool = False


class BacktestRequest(BaseModel):
    timeframe: str | None = None
    bars: int = Field(default=5000, ge=200, le=50000)
    start: str | None = None
    end: str | None = None
    initial_balance: float | None = None
    risk_pct: float | None = None
    spread_points: int | None = None
    commission_per_lot: float | None = None
    params: dict[str, Any] | None = None
    force_sim: bool = False


class TrainRequest(BaseModel):
    timeframe: str | None = None
    bars: int = Field(default=8000, ge=500, le=100000)
    horizon: int = Field(default=3, ge=1, le=20)
    force_sim: bool = False


# ---------------------------------------------------------------- helpers
def _engine(request: Request):
    return request.app.state.engine


def _store(request: Request):
    return request.app.state.store


def _market(request: Request):
    return request.app.state.market


# ---------------------------------------------------------------- health
@router.get("/health")
def health(request: Request) -> dict:
    market = _market(request)
    return {
        "status": "ok",
        "mt5": market.mt5_available(),
        "symbol": market.symbol,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/status")
async def status(request: Request) -> dict:
    return await asyncio.to_thread(_engine(request).status)


# ---------------------------------------------------------------- bot
@router.post("/bot/start")
async def bot_start(request: Request, body: StartRequest | None = None) -> dict:
    engine = _engine(request)
    try:
        return await engine.start(
            body.mode if body else None,
            confirm_real=bool(body and body.confirm_real),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/bot/stop")
async def bot_stop(request: Request, body: StopRequest | None = None) -> dict:
    engine = _engine(request)
    return await engine.stop(close_positions=bool(body and body.close_positions))


@router.post("/bot/panic")
async def bot_panic(request: Request) -> dict:
    engine = _engine(request)
    result = await engine.stop(close_positions=True)
    return {"stopped": True, "status": result}


# ---------------------------------------------------------------- mercado
@router.get("/candles")
def candles(request: Request, timeframe: str = "M5", limit: int = 400) -> dict:
    market = _market(request)
    df = market.candles(timeframe, min(max(limit, 50), 2000))
    return {
        "symbol": market.symbol,
        "timeframe": timeframe,
        "candles": [
            {
                "time": str(row.time),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
            for row in df.itertuples()
        ],
    }


@router.get("/symbols/btc")
async def btc_symbols(request: Request) -> dict:
    market = _market(request)
    await asyncio.to_thread(market.mt5_available)
    return market.symbol_status()


@router.post("/symbols/rescan")
async def rescan_symbol(request: Request) -> dict:
    market = _market(request)
    ok = await asyncio.to_thread(market.refresh_mt5)
    return {"connected": ok, **(await asyncio.to_thread(market.symbol_status))}


# ---------------------------------------------------------------- trades
@router.get("/trades")
def trades(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    mode: str | None = None,
) -> dict:
    total, items = _store(request).list_trades(limit=limit, offset=offset, status=status, mode=mode)
    return {"total": total, "items": items}


@router.get("/metrics")
def metrics(request: Request, mode: str | None = None) -> dict:
    cfg = load_config()
    initial = float(cfg["backtest"]["initial_balance"])
    closed = _store(request).all_closed_trades(mode)
    if mode == "live":
        # Para la cuenta real la curva arranca en el balance implícito inicial.
        try:
            account = _market(request).account()
            total = sum(float(t.get("pnl") or 0) for t in closed)
            initial = float(account.get("balance") or initial) - total
        except Exception:  # noqa: BLE001
            pass
    return compute_metrics(closed, initial_balance=initial)


# ---------------------------------------------------------------- config
@router.get("/config")
def get_config() -> dict:
    return load_config()


@router.patch("/config")
async def update_config(request: Request, patch: dict[str, Any]) -> dict:
    merged = patch_config(patch)
    engine = _engine(request)
    engine.config = merged
    from .core.risk import RiskManager

    engine.risk = RiskManager(merged["risk"])
    return {"config": merged, "note": "reiniciá el bot si cambiaste símbolo o timeframe"}


# ---------------------------------------------------------------- backtest
@router.post("/backtest")
async def backtest(request: Request, body: BacktestRequest) -> dict:
    cfg = load_config()
    market = _market(request)
    tf = body.timeframe or cfg["timeframe"]
    bars = body.bars or int(cfg["backtest"]["bars"])

    try:
        df = await asyncio.to_thread(market.candles, tf, bars, body.force_sim)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"sin datos: {exc}") from exc

    if body.start or body.end:
        times = df["time"].astype(str)
        mask = times.notna()
        if body.start:
            mask &= times >= body.start
        if body.end:
            mask &= times <= body.end
        df = df[mask].reset_index(drop=True)
    if len(df) < 100:
        raise HTTPException(status_code=400, detail="muy pocas velas para el rango pedido")

    params = deep_merge(cfg["strategy"], body.params or {})
    symbol_info = market.symbol_info() or {}
    raw_spread = body.spread_points if body.spread_points is not None else cfg["backtest"].get("spread_points")
    bt_cfg = BacktestConfig(
        initial_balance=float(body.initial_balance or cfg["backtest"]["initial_balance"]),
        risk_pct=float(body.risk_pct or cfg["backtest"]["risk_pct"]),
        spread_points=None if raw_spread is None else int(raw_spread),
        point=float(symbol_info.get("point") or 0.01),
        contract_size=float(symbol_info.get("contract_size") or 1.0),
        commission_per_lot=float(body.commission_per_lot or cfg["backtest"]["commission_per_lot"]),
    )

    result = await asyncio.to_thread(run_backtest, df, params, bt_cfg)
    report = compute_metrics(result.trades, initial_balance=bt_cfg.initial_balance)

    run_id = uuid.uuid4().hex[:12]
    payload = {
        "id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "params": {
            "timeframe": tf,
            "bars": len(df),
            "strategy": params,
            "initial_balance": bt_cfg.initial_balance,
            "risk_pct": bt_cfg.risk_pct,
            "spread_points": result.stats.get("spread_points"),
            "symbol": market.symbol,
            "source": "sim" if body.force_sim or not market.mt5_available() else "mt5",
        },
        "metrics": report,
        "equity_curve": result.equity_curve,
        "trades": result.trades,
        "status": "done",
    }
    _store(request).save_backtest(payload)
    return {
        "run_id": run_id,
        "metrics": report,
        "stats": result.stats,
        "params": payload["params"],
        "trades": result.trades[-300:],
        "equity_curve": result.equity_curve,
    }


@router.get("/backtests")
def list_backtests(request: Request, limit: int = 20) -> dict:
    return {"items": _store(request).list_backtests(limit)}


@router.get("/backtests/{run_id}")
def get_backtest(request: Request, run_id: str) -> dict:
    run = _store(request).get_backtest(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="backtest no encontrado")
    return run


# ---------------------------------------------------------------- ML
@router.get("/ml/status")
def ml_status() -> dict:
    from .ml.model import model_status

    return model_status()


@router.post("/ml/train")
async def ml_train(request: Request, body: TrainRequest) -> dict:
    from .ml.model import train_and_save

    cfg = load_config()
    market = _market(request)
    tf = body.timeframe or cfg["timeframe"]
    df = await asyncio.to_thread(market.candles, tf, body.bars, body.force_sim)
    try:
        metrics = await asyncio.to_thread(train_and_save, df, cfg["strategy"], body.horizon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "metrics": metrics}


# ---------------------------------------------------------------- websocket
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    engine = websocket.app.state.engine
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    def on_message(message: dict) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, message)
        except RuntimeError:
            pass

    engine.subscribe(on_message)
    try:
        await websocket.send_json({"type": "status", "data": await asyncio.to_thread(engine.status)})
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        engine.unsubscribe(on_message)
