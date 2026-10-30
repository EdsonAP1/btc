"""Backtester bar-a-bar con las mismas reglas que el motor en vivo.

Supuestos explícitos (conservadores):
  * La señal se evalúa al cierre de la vela i y se ejecuta al open de la i+1.
  * Si en una misma vela se tocan SL y TP, se asume SL (peor caso).
  * El spread se paga en la entrada y en la salida.
  * Break-even, trailing y parciales se actualizan al cierre de cada vela y
    aplican desde la vela siguiente (sin look-ahead).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..config import DEFAULTS
from .management import ManagedPosition, apply_management
from .strategy import prepare, signal_at


@dataclass
class BacktestConfig:
    initial_balance: float = 10000.0
    risk_pct: float = 1.0
    spread_points: int | None = None  # None = mediana de las velas
    point: float = 0.01
    contract_size: float = 1.0
    commission_per_lot: float = 0.0
    max_bars_hold: int = 0  # 0 = sin límite
    management: dict | None = None  # None = defaults del bot


@dataclass
class BacktestResult:
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def _round_lot(volume: float, step: float = 0.01, min_lot: float = 0.01, max_lot: float = 100.0) -> float:
    if step <= 0:
        step = 0.01
    lots = round(volume / step) * step
    lots = max(min_lot, min(max_lot, lots))
    return round(lots, 2)


def run_backtest(
    df: pd.DataFrame,
    params: dict,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    cfg = config or BacktestConfig()
    data = prepare(df.reset_index(drop=True), params).reset_index(drop=True)

    if cfg.spread_points is None:
        if "spread" in data.columns:
            spread_points = float(data["spread"].median() or 0.0)
        else:
            spread_points = 30.0
    else:
        spread_points = float(cfg.spread_points)
    spread = spread_points * cfg.point
    half_spread = spread / 2.0
    value_per_unit = cfg.contract_size
    management = cfg.management if cfg.management is not None else DEFAULTS["management"]
    digits = max(0, int(round(-math.log10(cfg.point)))) if cfg.point > 0 else 2

    equity = cfg.initial_balance
    pos: ManagedPosition | None = None
    trades: list[dict] = []
    curve: list[dict] = [{"time": str(data["time"].iloc[0]), "equity": round(equity, 2)}]
    last_exit_bar = -10**9
    cooldown = int(params.get("cooldown_bars", 0))

    warmup = max(
        int(params["ema_slow"]),
        int(params["atr_period"]),
        int(params["rsi_period"]),
        int(params.get("trend_ema") or 0),
        int(params.get("donchian_period") or 0),
        int(params.get("bb_period") or 0),
    ) + 2

    def close_position(exit_price: float, reason: str, when: Any) -> None:
        nonlocal equity, pos
        assert pos is not None
        remaining_pnl = (exit_price - pos.entry) * pos.direction * pos.volume * value_per_unit
        commission = cfg.commission_per_lot * pos.initial_volume * 2
        pnl = round(pos.realized_pnl + remaining_pnl - commission, 2)
        equity = round(equity + pnl, 2)
        trades.append(
            {
                "side": pos.side,
                "volume": pos.initial_volume,
                "open_time": str(pos.open_time),
                "open_price": round(pos.entry, 5),
                "close_time": str(when),
                "close_price": round(exit_price, 5),
                "sl": round(pos.initial_sl, 5),
                "sl_final": round(pos.sl, 5),
                "tp": round(pos.tp, 5),
                "pnl": pnl,
                "commission": round(commission, 2),
                "r_multiple": round(pnl / pos.risk_amount, 2) if pos.risk_amount else 0.0,
                "exit_reason": reason,
                "status": "closed",
            }
        )
        curve.append({"time": str(when), "equity": equity})
        pos = None

    for i in range(warmup, len(data) - 1):
        bar = data.iloc[i]
        nxt = data.iloc[i + 1]

        # ------------------------------------------------------- gestión abierta
        if pos is not None:
            exit_price: float | None = None
            exit_reason = ""
            high, low = float(bar["high"]), float(bar["low"])
            if pos.direction > 0:
                if low <= pos.sl:
                    exit_price, exit_reason = pos.sl - half_spread, "sl"
                elif high >= pos.tp:
                    exit_price, exit_reason = pos.tp - half_spread, "tp"
            else:
                if high >= pos.sl:
                    exit_price, exit_reason = pos.sl + half_spread, "sl"
                elif low <= pos.tp:
                    exit_price, exit_reason = pos.tp + half_spread, "tp"

            if exit_price is None and cfg.max_bars_hold and (i - pos.entry_bar) >= cfg.max_bars_hold:
                exit_price, exit_reason = float(bar["close"]), "time"

            if exit_price is not None:
                close_position(exit_price, exit_reason, bar["time"])
                last_exit_bar = i
            else:
                # Break-even, trailing y parciales sobre el extremo de la vela.
                extreme = high if pos.direction > 0 else low
                actions = apply_management(
                    pos,
                    price=extreme,
                    atr=float(bar["atr"]),
                    config=management,
                    digits=digits,
                )
                last_fill = None
                for action in actions:
                    if action["type"] != "partial":
                        continue
                    fill = float(action["trigger_price"])
                    volume = float(action["volume"])
                    pos.realized_pnl += (fill - pos.entry) * pos.direction * volume * value_per_unit
                    last_fill = fill
                if pos.volume <= 0 and last_fill is not None:
                    close_position(last_fill, "partials", bar["time"])
                    last_exit_bar = i

        # ------------------------------------------------------- nueva entrada
        if pos is None and (i - last_exit_bar) > cooldown:
            signal = signal_at(data, i, params)
            if signal.action in ("buy", "sell") and signal.sl and signal.tp:
                entry = float(nxt["open"]) + (half_spread if signal.action == "buy" else -half_spread)
                sl_dist = abs(entry - float(signal.sl))
                if sl_dist > 0:
                    risk_amount = equity * cfg.risk_pct / 100.0
                    volume = _round_lot(risk_amount / (sl_dist * value_per_unit))
                    if volume > 0:
                        pos = ManagedPosition(
                            side=signal.action,
                            entry=entry,
                            sl=float(signal.sl),
                            tp=float(signal.tp),
                            initial_sl=float(signal.sl),
                            volume=volume,
                            initial_volume=volume,
                            risk_amount=risk_amount,
                            extreme=entry,
                            open_time=nxt["time"],
                            entry_bar=i + 1,
                        )

    # Cierre forzado al final de la serie.
    if pos is not None:
        last = data.iloc[-1]
        close_position(float(last["close"]), "eof", last["time"])

    stats = {
        "initial_balance": cfg.initial_balance,
        "final_equity": round(equity, 2),
        "bars": len(data),
        "from": str(data["time"].iloc[0]),
        "to": str(data["time"].iloc[-1]),
        "spread_points": round(spread_points, 1),
    }
    return BacktestResult(trades=trades, equity_curve=curve, stats=stats)
