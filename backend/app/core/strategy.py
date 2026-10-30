"""Estrategia de ejemplo: cruce EMA + filtro RSI + SL/TP por ATR.

`signal_at()` es la ÚNICA fuente de verdad: la usa el motor en vivo y el
backtester, así lo que se prueba es exactamente lo que se opera.
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


def signal_at(
    df: pd.DataFrame,
    index: int,
    params: dict,
    ml_prob_up: float | None = None,
) -> Signal:
    """Evalúa la barra `index` de un DataFrame ya enriquecido."""
    row = df.iloc[index]
    price = float(row["close"])

    if pd.isna(row.get("atr")) or pd.isna(row.get("ema_slow")) or pd.isna(row.get("rsi")):
        return Signal("flat", "indicadores sin calentar", 0.0, price)

    atr_value = float(row["atr"])
    atr_pct = float(row.get("atr_pct") or 0.0)
    if atr_pct < float(params["min_atr_pct"]):
        return Signal("flat", f"volatilidad baja ({atr_pct:.3f}%)", 0.0, price, atr=atr_value)

    ema_fast = float(row["ema_fast"])
    ema_slow = float(row["ema_slow"])
    rsi_value = float(row["rsi"])

    trend_up = ema_fast > ema_slow and price > ema_fast
    trend_down = ema_fast < ema_slow and price < ema_fast

    long_ok = trend_up and rsi_value < float(params["rsi_long_max"])
    short_ok = trend_down and rsi_value > float(params["rsi_short_min"])

    # Filtro de tendencia de más largo plazo (opcional).
    trend_period = int(params.get("trend_ema") or 0)
    if trend_period > 0:
        ema_trend = row.get("ema_trend")
        if pd.isna(ema_trend):
            return Signal("flat", "EMA de tendencia sin calentar", 0.0, price, atr=atr_value)
        long_ok = long_ok and price > float(ema_trend)
        short_ok = short_ok and price < float(ema_trend)

    if not (long_ok or short_ok):
        return Signal("flat", "sin alineación de tendencia", 0.0, price, atr=atr_value)

    # Confirmación opcional del modelo ML.
    if params.get("use_ml") and ml_prob_up is not None:
        threshold = float(params.get("ml_threshold", 0.55))
        if long_ok and ml_prob_up < threshold:
            return Signal("flat", f"ML no confirma long ({ml_prob_up:.2f})", 0.0, price, atr=atr_value)
        if short_ok and ml_prob_up > 1 - threshold:
            return Signal("flat", f"ML no confirma short ({ml_prob_up:.2f})", 0.0, price, atr=atr_value)

    sl_mult = float(params["sl_atr"])
    tp_mult = float(params["tp_atr"])

    if long_ok:
        sl = price - atr_value * sl_mult
        tp = price + atr_value * tp_mult
        # Confianza: qué tan alineadas están las señales (0-1).
        conf = min(1.0, 0.5 + abs(ema_fast - ema_slow) / max(atr_value, 1e-9) * 0.2)
        if ml_prob_up is not None:
            conf = (conf + ml_prob_up) / 2
        return Signal("buy", f"EMA{params['ema_fast']}>{params['ema_slow']} · RSI {rsi_value:.1f}", conf, price, sl, tp, atr_value)

    sl = price + atr_value * sl_mult
    tp = price - atr_value * tp_mult
    conf = min(1.0, 0.5 + abs(ema_fast - ema_slow) / max(atr_value, 1e-9) * 0.2)
    if ml_prob_up is not None:
        conf = (conf + (1 - ml_prob_up)) / 2
    return Signal("sell", f"EMA{params['ema_fast']}<{params['ema_slow']} · RSI {rsi_value:.1f}", conf, price, sl, tp, atr_value)


def evaluate(df: pd.DataFrame, params: dict, ml_prob_up: float | None = None) -> Signal:
    """Señal sobre la última barra (usada por el motor en vivo)."""
    enriched = prepare(df, params)
    return signal_at(enriched, len(enriched) - 1, params, ml_prob_up)
