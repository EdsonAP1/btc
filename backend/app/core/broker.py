"""Brokers: ejecución real (MT5) y ejecución en papel (paper)."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from ..mt5.client import MT5Client
from ..mt5.feed import SimFeed


class Broker(Protocol):
    name: str
    is_live: bool

    def candles(self, timeframe: str, count: int): ...
    def tick(self) -> dict: ...
    def account(self) -> dict: ...
    def positions(self) -> list[dict]: ...
    def open(self, side: str, volume: float, sl: float | None, tp: float | None, comment: str = ""): ...
    def close(self, ticket: int) -> dict: ...
    def modify(self, ticket: int, sl: float, tp: float) -> bool: ...


class MT5Broker:
    name = "mt5"
    is_live = True

    def __init__(self, client: MT5Client) -> None:
        self.client = client

    def candles(self, timeframe: str, count: int):
        return self.client.candles(timeframe, count)

    def tick(self) -> dict:
        return self.client.tick()

    def account(self) -> dict:
        return self.client.account() or {}

    def positions(self) -> list[dict]:
        return self.client.positions()

    def symbol_info(self) -> dict:
        return self.client.symbol_info() or {}

    def open(self, side: str, volume: float, sl: float | None, tp: float | None, comment: str = "") -> dict:
        return self.client.open_market(side, volume, sl, tp, comment)

    def close(self, ticket: int, volume: float | None = None) -> dict:
        result = self.client.close_position(ticket, volume)
        if volume is None:
            deals = self.client.position_deals(ticket)
            pnl = sum(d["profit"] for d in deals)
            commission = sum(d["commission"] for d in deals)
            swap = sum(d["swap"] for d in deals)
            return {
                "ticket": ticket,
                "price": result["price"],
                "pnl": pnl,
                "commission": commission,
                "swap": swap,
                "volume": result.get("volume", volume),
                "remaining": 0.0,
            }
        # Cierre parcial: P&L incremental del volumen cerrado.
        position = self.client.position(ticket)
        contract = float((self.client.symbol_info() or {}).get("contract_size") or 1.0)
        direction = 1 if (position or {}).get("side") == "buy" else -1
        entry = float((position or {}).get("open_price") or result["price"])
        pnl = (float(result["price"]) - entry) * direction * float(volume) * contract
        remaining = max(0.0, float((position or {}).get("volume") or 0) - float(volume))
        return {
            "ticket": ticket,
            "price": result["price"],
            "pnl": round(pnl, 2),
            "commission": 0.0,
            "swap": 0.0,
            "volume": float(volume),
            "remaining": round(remaining, 8),
        }

    def modify(self, ticket: int, sl: float, tp: float) -> bool:
        return self.client.modify_position(ticket, sl, tp)

    def margin_for(self, side: str, volume: float, price: float | None = None) -> float:
        return self.client.margin_for(side, volume, price)


class PaperBroker:
    """Simula fills al bid/ask actual, sin tocar el mercado."""

    name = "paper"
    is_live = False

    def __init__(
        self,
        feed: SimFeed | MT5Client,
        initial_balance: float = 10000.0,
        contract_size: float = 1.0,
    ) -> None:
        self.feed = feed
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.contract_size = contract_size
        self._positions: dict[int, dict] = {}
        self._lock = threading.RLock()

    # ---------------------------------------------------------------- mercado
    def candles(self, timeframe: str, count: int):
        return self.feed.candles(timeframe, count)

    def tick(self) -> dict:
        return self.feed.tick()

    def symbol_info(self) -> dict:
        return self.feed.symbol_info()

    def account(self) -> dict:
        equity = self.balance + sum(p["profit"] for p in self.positions())
        return {
            "login": 0,
            "server": "PAPER",
            "name": "Cuenta paper",
            "balance": round(self.balance, 2),
            "equity": round(equity, 2),
            "margin": 0.0,
            "free_margin": round(equity, 2),
            "currency": "USD",
            "leverage": 100,
            "profit": round(equity - self.balance, 2),
            "type": "paper",
            "is_demo": True,
            "trade_allowed": True,
        }

    # ---------------------------------------------------------------- órdenes
    def open(self, side: str, volume: float, sl: float | None, tp: float | None, comment: str = "") -> dict:
        tick = self.tick()
        price = tick["ask"] if side == "buy" else tick["bid"]
        with self._lock:
            ticket = int(uuid.uuid4().int % 1_000_000_000)
            self._positions[ticket] = {
                "ticket": ticket,
                "symbol": getattr(self.feed, "name", "PAPER"),
                "side": side,
                "volume": float(volume),
                "open_price": float(price),
                "sl": float(sl) if sl else 0.0,
                "tp": float(tp) if tp else 0.0,
                "open_time": datetime.now(timezone.utc).isoformat(),
                "comment": comment,
            }
        return {"ticket": ticket, "price": price, "volume": float(volume)}

    def positions(self) -> list[dict]:
        tick = self.tick()
        out = []
        with self._lock:
            for p in self._positions.values():
                current = tick["bid"] if p["side"] == "buy" else tick["ask"]
                direction = 1 if p["side"] == "buy" else -1
                profit = (current - p["open_price"]) * direction * p["volume"] * self.contract_size
                out.append({**p, "current_price": current, "profit": round(profit, 2), "swap": 0.0, "magic": 0})
        return out

    def close(self, ticket: int, volume: float | None = None) -> dict:
        with self._lock:
            pos = self._positions.get(ticket)
            if pos is None:
                raise KeyError(f"posición {ticket} no existe")
            volume = float(volume or pos["volume"])
            volume = min(volume, float(pos["volume"]))
            tick = self.tick()
            price = tick["bid"] if pos["side"] == "buy" else tick["ask"]
            direction = 1 if pos["side"] == "buy" else -1
            pnl = (price - pos["open_price"]) * direction * volume * self.contract_size
            self.balance += pnl
            remaining = round(float(pos["volume"]) - volume, 8)
            if remaining <= 1e-9:
                self._positions.pop(ticket, None)
                remaining = 0.0
            else:
                pos["volume"] = remaining
        return {
            "ticket": ticket,
            "price": price,
            "pnl": round(pnl, 2),
            "commission": 0.0,
            "swap": 0.0,
            "volume": volume,
            "remaining": remaining,
        }

    def modify(self, ticket: int, sl: float, tp: float) -> bool:
        with self._lock:
            if ticket in self._positions:
                self._positions[ticket]["sl"] = float(sl)
                self._positions[ticket]["tp"] = float(tp)
                return True
        return False

    def margin_for(self, side: str, volume: float, price: float | None = None) -> float:
        if price is None:
            tick = self.tick()
            price = tick["ask"] if side == "buy" else tick["bid"]
        return float(price) * float(volume) * self.contract_size / 100.0
