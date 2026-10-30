"""Features para el modelo ML (sin dependencias más allá de numpy/pandas)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.strategy import prepare

FEATURE_NAMES = [
    "ret_1",
    "ret_3",
    "ret_5",
    "ema_spread",
    "rsi_norm",
    "atr_pct",
    "close_vs_ema",
    "body_atr",
    "range_atr",
    "vol_ratio",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]


def build_features(df_raw: pd.DataFrame, params: dict) -> pd.DataFrame:
    df = prepare(df_raw.reset_index(drop=True), params)
    close = df["close"]

    out = pd.DataFrame(index=df.index)
    out["ret_1"] = close.pct_change(1)
    out["ret_3"] = close.pct_change(3)
    out["ret_5"] = close.pct_change(5)
    out["ema_spread"] = (df["ema_fast"] - df["ema_slow"]) / df["atr"].replace(0, np.nan)
    out["rsi_norm"] = df["rsi"] / 100.0 - 0.5
    out["atr_pct"] = df["atr_pct"] / 100.0
    out["close_vs_ema"] = (close - df["ema_fast"]) / df["atr"].replace(0, np.nan)
    out["body_atr"] = (close - df["open"]) / df["atr"].replace(0, np.nan)
    out["range_atr"] = (df["high"] - df["low"]) / df["atr"].replace(0, np.nan)
    out["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean().replace(0, np.nan)

    hours = df["time"].dt.hour + df["time"].dt.minute / 60.0
    out["hour_sin"] = np.sin(2 * np.pi * hours / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hours / 24.0)
    dow = df["time"].dt.dayofweek
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)

    out = out[FEATURE_NAMES]
    return out.replace([np.inf, -np.inf], np.nan)


def build_dataset(
    df_raw: pd.DataFrame, params: dict, horizon: int = 3
) -> tuple[np.ndarray, np.ndarray, pd.Series]:
    features = build_features(df_raw, params)
    close = df_raw.reset_index(drop=True)["close"]
    future = close.shift(-horizon) / close - 1.0
    label = (future > 0).astype(int)

    mask = features.notna().all(axis=1) & future.notna()
    X = features[mask].to_numpy(dtype=float)
    y = label[mask].to_numpy(dtype=int)
    times = df_raw.reset_index(drop=True).loc[mask, "time"]
    return X, y, times


def latest_features(df_raw: pd.DataFrame, params: dict) -> np.ndarray | None:
    features = build_features(df_raw, params)
    if features.empty:
        return None
    row = features.iloc[[-1]].to_numpy(dtype=float)
    if np.isnan(row).any():
        return None
    return row[0]
