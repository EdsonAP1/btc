"""Fuentes de precio: MT5 real o simulada (para desarrollo sin terminal)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .client import TF_SECONDS

BASE_PRICE = 64000.0


class SimFeed:
    """Serie sintética de BTC con forma realista, avanza con el reloj.

    Se genera una sola vez una caminata aleatoria de 1 minuto y se corta en
    "ahora", así las velas son continuas entre llamadas.
    """

    def __init__(self, bars_1m: int = 200_000, seed: int = 7, base_price: float = BASE_PRICE) -> None:
        self.seed = seed
        self.base_price = base_price
        self._bars = bars_1m
        self._start = datetime.now(timezone.utc) - timedelta(minutes=bars_1m)
        rng = np.random.default_rng(seed)
        # Volatilidad por minuto ~0.05% con clusters (GARCH-ish simple).
        shocks = rng.standard_normal(bars_1m)
        vol = 0.0006 * (1 + 0.5 * np.abs(np.sin(np.arange(bars_1m) / 900.0)))
        ret = shocks * vol
        # Deriva suave para que no se vaya a cero ni a infinito.
        drift = 0.0000025 * np.sin(np.arange(bars_1m) / 4000.0)
        close = base_price * np.exp(np.cumsum(ret + drift))
        open_ = np.concatenate([[base_price], close[:-1]])
        wick = np.abs(rng.standard_normal(bars_1m)) * vol * close
        high = np.maximum(open_, close) + wick * 0.6
        low = np.minimum(open_, close) - wick * 0.6
        volume = rng.integers(50, 500, bars_1m).astype(float)

        self._df = pd.DataFrame(
            {
                "time": pd.date_range(self._start, periods=bars_1m, freq="1min", tz="UTC"),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )

    @property
    def name(self) -> str:
        return "SIM-BTC"

    def candles(self, timeframe: str = "M5", count: int = 500) -> pd.DataFrame:
        minutes = TF_SECONDS.get(timeframe, 300) // 60
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        cutoff = now - timedelta(minutes=now.minute % minutes)
        df = self._df[self._df["time"] < cutoff]
        need = count * minutes
        df = df.tail(need)
        df = df.set_index("time")
        agg = df.resample(f"{minutes}min", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        )
        agg = agg.dropna().reset_index()
        agg["spread"] = 30
        return agg.tail(count).reset_index(drop=True)

    def tick(self) -> dict:
        df = self._df[self._df["time"] <= datetime.now(timezone.utc)]
        last = float(df["close"].iloc[-1])
        spread = 30 * 0.01  # 30 puntos, igual que las velas simuladas
        return {
            "bid": round(last - spread / 2, 2),
            "ask": round(last + spread / 2, 2),
            "time": datetime.now(timezone.utc).isoformat(),
        }

    def account(self) -> dict:
        return {
            "login": 0,
            "server": "SIMULADO",
            "name": "Cuenta simulada",
            "balance": 10000.0,
            "equity": 10000.0,
            "margin": 0.0,
            "free_margin": 10000.0,
            "currency": "USD",
            "leverage": 100,
            "profit": 0.0,
            "type": "sim",
            "is_demo": True,
            "trade_allowed": True,
        }

    def positions(self) -> list[dict]:
        return []

    def position_deals(self, ticket: int) -> list[dict]:
        return []

    def symbol_info(self) -> dict:
        return {
            "name": "SIM-BTC",
            "description": "Bitcoin simulado",
            "digits": 2,
            "point": 0.01,
            "spread": 30,
            "contract_size": 1.0,
            "volume_min": 0.01,
            "volume_max": 10.0,
            "volume_step": 0.01,
            "tick_value": 0.01,
            "tick_size": 0.01,
            "trade_mode": 4,
            "currency_profit": "USD",
        }
