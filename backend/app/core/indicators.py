"""Indicadores técnicos sin dependencias externas (numpy/pandas)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(50.0)


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def enrich(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Agrega las columnas que consume la estrategia."""
    out = df.copy()
    out["ema_fast"] = ema(out["close"], int(params["ema_fast"]))
    out["ema_slow"] = ema(out["close"], int(params["ema_slow"]))
    out["rsi"] = rsi(out["close"], int(params["rsi_period"]))
    out["atr"] = atr(out, int(params["atr_period"]))
    out["atr_pct"] = out["atr"] / out["close"] * 100.0
    trend_period = int(params.get("trend_ema") or 0)
    if trend_period > 0:
        out["ema_trend"] = ema(out["close"], trend_period)

    # Canales Donchian (sin incluir la vela actual: shift(1)).
    donchian = int(params.get("donchian_period") or 0)
    if donchian > 0:
        out["donchian_high"] = out["high"].rolling(donchian).max().shift(1)
        out["donchian_low"] = out["low"].rolling(donchian).min().shift(1)

    # Bandas de Bollinger.
    bb_period = int(params.get("bb_period") or 0)
    if bb_period > 0:
        mid = out["close"].rolling(bb_period).mean()
        std = out["close"].rolling(bb_period).std(ddof=0)
        width = float(params.get("bb_std") or 2.0) * std
        out["bb_mid"] = mid
        out["bb_up"] = mid + width
        out["bb_low"] = mid - width

    return out
