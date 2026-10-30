"""Estrategias de entrada.

`signal_at()` es la ÚNICA fuente de verdad: la usa el motor en vivo y el
backtester, así lo que se prueba es exactamente lo que se opera.

Estrategias disponibles:
  * ema_rsi_atr    - tendencia (cruce EMA + filtro RSI)
  * donchian       - ruptura del canal de N velas
  * mean_reversion - reversión a la media (Bollinger + RSI)
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import indicators


@dataclass
class Signal:
    action: str  # "buy" | "sell" | "flat"
    reason: str
    confidence: float
    price: float
    sl: float | None = None
    tp: float | None = None
    atr: float | None = None

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "confidence": round(self.confidence, 3),
            "price": round(self.price, 5),
            "sl": round(self.sl, 5) if self.sl else None,
            "tp": round(self.tp, 5) if self.tp else None,
            "atr": round(self.atr, 5) if self.atr else None,
        }


def prepare(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    return indicators.enrich(df, params)


# --------------------------------------------------------------------- utils
def _flat(reason: str, price: float, atr: float | None = None) -> Signal:
    return Signal("flat", reason, 0.0, price, atr=atr)


def _levels(side: str, price: float, atr: float, params: dict) -> tuple[float, float]:
    sl_mult = float(params["sl_atr"])
    tp_mult = float(params["tp_atr"])
    if side == "buy":
        return price - atr * sl_mult, price + atr * tp_mult
    return price + atr * sl_mult, price - atr * tp_mult


def _ml_rejects(side: str, params: dict, ml_prob: float | None) -> str | None:
    if not params.get("use_ml") or ml_prob is None:
        return None
    threshold = float(params.get("ml_threshold", 0.55))
    if side == "buy" and ml_prob < threshold:
        return f"ML no confirma long ({ml_prob:.2f})"
    if side == "sell" and ml_prob > 1 - threshold:
        return f"ML no confirma short ({ml_prob:.2f})"
    return None


def _volatility_ok(row, params: dict) -> bool:
    atr_pct = float(row.get("atr_pct") or 0.0)
    return atr_pct >= float(params.get("min_atr_pct", 0.0))


# ---------------------------------------------------------------- estrategias
def _ema_rsi_atr(df: pd.DataFrame, index: int, params: dict, ml_prob_up: float | None) -> Signal:
    row = df.iloc[index]
    price = float(row["close"])

    if pd.isna(row.get("atr")) or pd.isna(row.get("ema_slow")) or pd.isna(row.get("rsi")):
        return _flat("indicadores sin calentar", price)

    atr_value = float(row["atr"])
    if not _volatility_ok(row, params):
        return _flat("volatilidad baja", price, atr_value)

    ema_fast = float(row["ema_fast"])
    ema_slow = float(row["ema_slow"])
    rsi_value = float(row["rsi"])

    long_ok = ema_fast > ema_slow and price > ema_fast and rsi_value < float(params["rsi_long_max"])
    short_ok = ema_fast < ema_slow and price < ema_fast and rsi_value > float(params["rsi_short_min"])

    trend_period = int(params.get("trend_ema") or 0)
    if trend_period > 0:
        ema_trend = row.get("ema_trend")
        if pd.isna(ema_trend):
            return _flat("EMA de tendencia sin calentar", price, atr_value)
        long_ok = long_ok and price > float(ema_trend)
        short_ok = short_ok and price < float(ema_trend)

    if not (long_ok or short_ok):
        return _flat("sin alineación de tendencia", price, atr_value)

    side = "buy" if long_ok else "sell"
    rejection = _ml_rejects(side, params, ml_prob_up)
    if rejection:
        return _flat(rejection, price, atr_value)

    sl, tp = _levels(side, price, atr_value, params)
    conf = min(1.0, 0.5 + abs(ema_fast - ema_slow) / max(atr_value, 1e-9) * 0.2)
    if ml_prob_up is not None:
        conf = (conf + (ml_prob_up if side == "buy" else 1 - ml_prob_up)) / 2
    reason = f"EMA{params['ema_fast']}{'>' if side == 'buy' else '<'}{params['ema_slow']} · RSI {rsi_value:.1f}"
    return Signal(side, reason, conf, price, sl, tp, atr_value)


def _donchian(df: pd.DataFrame, index: int, params: dict, ml_prob_up: float | None) -> Signal:
    row = df.iloc[index]
    price = float(row["close"])
    atr_value = float(row["atr"]) if not pd.isna(row.get("atr")) else 0.0
    if atr_value <= 0:
        return _flat("ATR sin calentar", price)
    if not _volatility_ok(row, params):
        return _flat("volatilidad baja", price, atr_value)

    upper = row.get("donchian_high")
    lower = row.get("donchian_low")
    if pd.isna(upper) or pd.isna(lower):
        return _flat("canal Donchian sin calentar", price, atr_value)

    long_ok = price > float(upper)
    short_ok = price < float(lower)

    trend_period = int(params.get("trend_ema") or 0)
    if trend_period > 0:
        ema_trend = row.get("ema_trend")
        if pd.isna(ema_trend):
            return _flat("EMA de tendencia sin calentar", price, atr_value)
        long_ok = long_ok and price > float(ema_trend)
        short_ok = short_ok and price < float(ema_trend)

    if not (long_ok or short_ok):
        return _flat("sin ruptura del canal", price, atr_value)

    side = "buy" if long_ok else "sell"
    rejection = _ml_rejects(side, params, ml_prob_up)
    if rejection:
        return _flat(rejection, price, atr_value)

    sl, tp = _levels(side, price, atr_value, params)
    level = float(upper) if side == "buy" else float(lower)
    conf = min(1.0, 0.55 + abs(price - level) / max(atr_value, 1e-9) * 0.15)
    period = int(params.get("donchian_period", 20))
    return Signal(side, f"ruptura {period} velas", conf, price, sl, tp, atr_value)


def _mean_reversion(df: pd.DataFrame, index: int, params: dict, ml_prob_up: float | None) -> Signal:
    row = df.iloc[index]
    price = float(row["close"])
    atr_value = float(row["atr"]) if not pd.isna(row.get("atr")) else 0.0
    if atr_value <= 0:
        return _flat("ATR sin calentar", price)
    if not _volatility_ok(row, params):
        return _flat("volatilidad baja", price, atr_value)

    upper = row.get("bb_up")
    lower = row.get("bb_low")
    rsi_value = row.get("rsi")
    if pd.isna(upper) or pd.isna(lower) or pd.isna(rsi_value):
        return _flat("bandas sin calentar", price, atr_value)

    long_ok = price <= float(lower) and float(rsi_value) <= float(params.get("mr_rsi_low", 30.0))
    short_ok = price >= float(upper) and float(rsi_value) >= float(params.get("mr_rsi_high", 70.0))

    if not (long_ok or short_ok):
        return _flat("precio dentro de las bandas", price, atr_value)

    side = "buy" if long_ok else "sell"
    rejection = _ml_rejects(side, params, ml_prob_up)
    if rejection:
        return _flat(rejection, price, atr_value)

    sl, tp = _levels(side, price, atr_value, params)
    conf = min(1.0, 0.55 + abs(float(rsi_value) - 50.0) / 100.0)
    return Signal(side, f"reversión · RSI {float(rsi_value):.1f}", conf, price, sl, tp, atr_value)


STRATEGIES = {
    "ema_rsi_atr": _ema_rsi_atr,
    "donchian": _donchian,
    "mean_reversion": _mean_reversion,
}

STRATEGY_META = [
    {
        "name": "ema_rsi_atr",
        "label": "EMA + RSI + ATR",
        "description": "Sigue la tendencia con cruce de EMAs y filtro RSI.",
        "fields": ["ema_fast", "ema_slow", "rsi_long_max", "rsi_short_min"],
    },
    {
        "name": "donchian",
        "label": "Donchian (ruptura)",
        "description": "Entra cuando el precio rompe el máximo/mínimo de N velas.",
        "fields": ["donchian_period", "trend_ema"],
    },
    {
        "name": "mean_reversion",
        "label": "Reversión a la media",
        "description": "Compra en la banda inferior y vende en la superior con RSI extremo.",
        "fields": ["bb_period", "bb_std", "mr_rsi_low", "mr_rsi_high"],
    },
]


def signal_at(df: pd.DataFrame, index: int, params: dict, ml_prob_up: float | None = None) -> Signal:
    """Evalúa la barra `index` con la estrategia indicada en `params["name"]`."""
    name = str(params.get("name") or "ema_rsi_atr").lower()
    strategy = STRATEGIES.get(name, _ema_rsi_atr)
    return strategy(df, index, params, ml_prob_up)


def evaluate(df: pd.DataFrame, params: dict, ml_prob_up: float | None = None) -> Signal:
    """Señal sobre la última barra (usada por el motor en vivo)."""
    enriched = prepare(df, params)
    return signal_at(enriched, len(enriched) - 1, params, ml_prob_up)
