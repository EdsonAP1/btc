"""Acceso a datos de mercado con fallback automático a simulación."""
from __future__ import annotations

import threading
from typing import Any

from .mt5.client import MT5Client, MT5Unavailable
from .mt5.feed import SimFeed


class Market:
    def __init__(self, config: dict) -> None:
        sym = config["symbol"]
        exec_cfg = config.get("execution", {})
        self.client = MT5Client(
            symbol_mode=sym.get("mode", "auto"),
            symbol_name=sym.get("name"),
            fallbacks=sym.get("fallbacks", []),
            magic=int(exec_cfg.get("magic", 770123)),
            deviation=int(exec_cfg.get("deviation", 30)),
            comment=str(exec_cfg.get("comment", "btc-bot")),
        )
        self.sim = SimFeed()
        self._lock = threading.RLock()
        self._mt5_state: bool | None = None

    # ------------------------------------------------------------------ estado
    def mt5_available(self) -> bool:
        with self._lock:
            if self._mt5_state is None:
                self._mt5_state = self.client.connect()
            return bool(self._mt5_state)

    def refresh_mt5(self) -> bool:
        with self._lock:
            self._mt5_state = self.client.connect()
            return bool(self._mt5_state)

    @property
    def using_mt5(self) -> bool:
        return self.mt5_available()

    @property
    def symbol(self) -> str:
        if self.mt5_available() and self.client.symbol:
            return self.client.symbol
        return self.sim.name

    def source(self, force_sim: bool = False):
        if not force_sim and self.mt5_available():
            return self.client
        return self.sim

    # ------------------------------------------------------------------- datos
    def candles(self, timeframe: str = "M5", count: int = 500, force_sim: bool = False):
        try:
            return self.source(force_sim).candles(timeframe, count)
        except Exception:
            return self.sim.candles(timeframe, count)

    def tick(self) -> dict[str, Any]:
        try:
            return self.source().tick()
        except Exception:
            return self.sim.tick()

    def symbol_info(self) -> dict[str, Any]:
        try:
            return self.source().symbol_info() or {}
        except Exception:
            return self.sim.symbol_info()

    def account(self) -> dict[str, Any]:
        try:
            return self.source().account() or {}
        except Exception:
            return self.sim.account()

    def status(self) -> dict[str, Any]:
        connected = self.mt5_available()
        error = None
        if not connected:
            error = self.client.last_error or "terminal MT5 no disponible"
        return {
            "connected": connected,
            "terminal": self.client._terminal_info,
            "error": error,
            "account": self.account() if connected else None,
        }

    def symbol_status(self) -> dict[str, Any]:
        sym_cfg = {"mode": self.client.symbol_mode}
        return {
            "name": self.symbol,
            "auto_detected": self.client.symbol_mode == "auto",
            "mode": self.client.symbol_mode,
            "candidates": self.client.candidates[:10],
            "info": self.symbol_info(),
        }


__all__ = ["Market", "MT5Unavailable"]
