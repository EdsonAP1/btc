"""Cliente MT5: conexión, autodetección de símbolo, datos y órdenes."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

import pandas as pd

try:  # El paquete solo existe en Windows con el terminal instalado.
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None  # type: ignore[assignment]

from .symbols import is_btc_candidate, pick_best, score_symbol

TF_MAP = (
    {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    if mt5 is not None
    else {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 16385, "H4": 16388, "D1": 16408}
)

TF_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}


class MT5Unavailable(RuntimeError):
    pass


class MT5Client:
    """Envoltorio thread-safe sobre la API de MetaTrader 5."""

    def __init__(
        self,
        symbol_mode: str = "auto",
        symbol_name: str | None = None,
        fallbacks: list[str] | None = None,
        magic: int = 770123,
        deviation: int = 30,
        comment: str = "btc-bot",
    ) -> None:
        self.symbol_mode = symbol_mode
        self.requested_symbol = symbol_name
        self.fallbacks = fallbacks or []
        self.magic = magic
        self.deviation = deviation
        self.comment = comment

        self.symbol: str | None = None
        self.candidates: list[dict] = []
        self.last_error: str | None = None
        self._connected = False
        self._lock = threading.RLock()
        self._terminal_info: dict | None = None

    # ------------------------------------------------------------------ conexión
    @property
    def available(self) -> bool:
        return mt5 is not None

    @property
    def connected(self) -> bool:
        return self._connected and mt5 is not None

    def connect(self) -> bool:
        with self._lock:
            if self._connected:
                return True
            if mt5 is None:
                self.last_error = "paquete MetaTrader5 no instalado"
                return False
            if not mt5.initialize():
                self.last_error = f"initialize falló: {mt5.last_error()}"
                self._connected = False
                return False
            self._connected = True
            self.last_error = None
            info = mt5.terminal_info()
            self._terminal_info = {
                "path": getattr(info, "path", None),
                "connected": getattr(info, "connected", None),
                "company": getattr(info, "company", None),
                "build": getattr(info, "build", None),
            }
            self._resolve_symbol()
            return True

    def disconnect(self) -> None:
        with self._lock:
            if mt5 is not None:
                mt5.shutdown()
            self._connected = False

    def ensure(self) -> None:
        if not self.connect():
            raise MT5Unavailable(self.last_error or "MT5 no disponible")
        if self.symbol is None:
            self._resolve_symbol()
        if self.symbol is None:
            raise MT5Unavailable("no se encontró ningún símbolo BTC en el terminal")

    # ------------------------------------------------------------------ símbolo
    def _resolve_symbol(self) -> str | None:
        assert mt5 is not None
        candidates: list[dict] = []
        for info in mt5.symbols_get() or []:
            if not is_btc_candidate(info.name):
                continue
            candidates.append(
                {
                    "name": info.name,
                    "visible": bool(info.visible),
                    "trade_allowed": int(info.trade_mode) != 0,
                    "score": score_symbol(
                        info.name,
                        visible=bool(info.visible),
                        trade_allowed=int(info.trade_mode) != 0,
                    ),
                }
            )
        candidates.sort(key=lambda c: (-c["score"], len(c["name"])))
        self.candidates = candidates

        chosen: str | None = None
        if self.symbol_mode == "manual" and self.requested_symbol:
            chosen = self._try_symbol(self.requested_symbol)
        if chosen is None:
            best = pick_best(candidates)
            if best:
                chosen = self._try_symbol(best["name"])
        if chosen is None:
            for name in self.fallbacks:
                chosen = self._try_symbol(name)
                if chosen:
                    break
        self.symbol = chosen
        return chosen

    def _try_symbol(self, name: str) -> str | None:
        assert mt5 is not None
        info = mt5.symbol_info(name)
        if info is None:
            return None
        if not info.visible:
            mt5.symbol_select(name, True)
            info = mt5.symbol_info(name)
        if info is None:
            return None
        return name

    def symbol_info(self) -> dict[str, Any] | None:
        self.ensure()
        assert mt5 is not None and self.symbol
        info = mt5.symbol_info(self.symbol)
        if info is None:
            return None
        return {
            "name": info.name,
            "description": info.description,
            "digits": int(info.digits),
            "point": float(info.point),
            "spread": int(info.spread),
            "contract_size": float(info.trade_contract_size),
            "volume_min": float(info.volume_min),
            "volume_max": float(info.volume_max),
            "volume_step": float(info.volume_step),
            "tick_value": float(getattr(info, "trade_tick_value", 0.0) or 0.0),
            "tick_size": float(getattr(info, "trade_tick_size", 0.0) or 0.0),
            "trade_mode": int(info.trade_mode),
            "currency_profit": info.currency_profit,
        }

    # ------------------------------------------------------------------ datos
    def candles(self, timeframe: str = "M5", count: int = 500) -> pd.DataFrame:
        self.ensure()
        assert mt5 is not None and self.symbol
        tf = TF_MAP.get(timeframe, 5)
        rates = mt5.copy_rates_from_pos(self.symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            raise MT5Unavailable(f"sin velas para {self.symbol} {timeframe}: {mt5.last_error()}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"tick_volume": "volume"})
        return df[["time", "open", "high", "low", "close", "volume", "spread"]].reset_index(drop=True)

    def tick(self) -> dict[str, Any]:
        self.ensure()
        assert mt5 is not None and self.symbol
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            raise MT5Unavailable("sin tick disponible")
        return {
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "time": datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
        }

    def account(self) -> dict[str, Any] | None:
        self.ensure()
        assert mt5 is not None
        acc = mt5.account_info()
        if acc is None:
            return None
        account_type = {0: "demo", 1: "contest", 2: "real"}.get(int(getattr(acc, "trade_mode", 2)), "unknown")
        return {
            "login": acc.login,
            "server": acc.server,
            "name": acc.name,
            "balance": float(acc.balance),
            "equity": float(acc.equity),
            "margin": float(acc.margin),
            "free_margin": float(acc.margin_free),
            "currency": acc.currency,
            "leverage": acc.leverage,
            "profit": float(acc.profit),
            "type": account_type,
            "is_demo": account_type == "demo",
            "trade_allowed": bool(getattr(acc, "trade_allowed", False)),
        }

    def positions(self) -> list[dict[str, Any]]:
        self.ensure()
        assert mt5 is not None and self.symbol
        raw = mt5.positions_get(symbol=self.symbol) or []
        out = []
        for p in raw:
            out.append(
                {
                    "ticket": int(p.ticket),
                    "symbol": p.symbol,
                    "side": "buy" if int(p.type) == 0 else "sell",
                    "volume": float(p.volume),
                    "open_price": float(p.price_open),
                    "current_price": float(p.price_current),
                    "sl": float(p.sl),
                    "tp": float(p.tp),
                    "profit": float(p.profit),
                    "swap": float(p.swap),
                    "magic": int(p.magic),
                    "comment": p.comment,
                    "open_time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
                }
            )
        return out

    def position(self, ticket: int) -> dict[str, Any] | None:
        for pos in self.positions():
            if int(pos["ticket"]) == int(ticket):
                return pos
        return None

    def margin_for(self, side: str, volume: float, price: float | None = None) -> float:
        """Margen requerido aproximado para abrir `volume` lotes."""
        self.ensure()
        assert mt5 is not None and self.symbol
        if price is None:
            price = self.tick()["ask" if side == "buy" else "bid"]
        order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
        try:
            margin = mt5.order_calc_margin(order_type, self.symbol, float(volume), float(price))
        except Exception:  # noqa: BLE001
            margin = None
        if margin is not None:
            return float(margin)
        info = self.symbol_info() or {}
        leverage = 1.0
        acc = mt5.account_info()
        if acc is not None and acc.leverage:
            leverage = float(acc.leverage)
        return float(price) * float(volume) * float(info.get("contract_size") or 1.0) / leverage

    def position_deals(self, ticket: int) -> list[dict[str, Any]]:
        assert mt5 is not None
        deals = mt5.history_deals_get(position=ticket) or []
        return [
            {
                "ticket": int(d.ticket),
                "price": float(d.price),
                "profit": float(d.profit),
                "commission": float(d.commission),
                "swap": float(d.swap),
                "time": datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
                "entry": int(d.entry),
            }
            for d in deals
        ]

    # ------------------------------------------------------------------ órdenes
    def _filling_mode(self) -> int:
        assert mt5 is not None and self.symbol
        info = mt5.symbol_info(self.symbol)
        flags = int(getattr(info, "filling_mode", 0) or 0)
        if flags & 1:
            return mt5.ORDER_FILLING_FOK
        if flags & 2:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def open_market(
        self,
        side: str,
        volume: float,
        sl: float | None = None,
        tp: float | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        assert mt5 is not None and self.symbol
        tick = self.tick()
        price = tick["ask"] if side == "buy" else tick["bid"]
        info = self.symbol_info() or {}
        digits = int(info.get("digits", 2))
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": comment or self.comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(),
        }
        if sl:
            request["sl"] = round(float(sl), digits)
        if tp:
            request["tp"] = round(float(tp), digits)

        result = mt5.order_send(request)
        if result is None:
            raise MT5Unavailable(f"order_send sin respuesta: {mt5.last_error()}")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise MT5Unavailable(f"orden rechazada ({result.retcode}): {result.comment}")
        return {
            "ticket": int(result.order),
            "deal": int(result.deal),
            "price": float(result.price),
            "volume": float(result.volume),
        }

    def close_position(self, ticket: int, volume: float | None = None) -> dict[str, Any]:
        self.ensure()
        assert mt5 is not None and self.symbol
        positions = [p for p in (mt5.positions_get(ticket=ticket) or [])]
        if not positions:
            raise MT5Unavailable(f"posición {ticket} no encontrada")
        pos = positions[0]
        side = "sell" if int(pos.type) == 0 else "buy"
        tick = self.tick()
        price = tick["bid"] if side == "sell" else tick["ask"]
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "position": ticket,
            "volume": float(volume or pos.volume),
            "type": mt5.ORDER_TYPE_SELL if side == "sell" else mt5.ORDER_TYPE_BUY,
            "price": price,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(),
        }
        result = mt5.order_send(request)
        if result is None:
            raise MT5Unavailable(f"cierre sin respuesta: {mt5.last_error()}")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise MT5Unavailable(f"cierre rechazado ({result.retcode}): {result.comment}")
        return {"ticket": ticket, "price": float(result.price), "volume": float(result.volume)}

    def modify_position(self, ticket: int, sl: float, tp: float) -> bool:
        self.ensure()
        assert mt5 is not None
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": float(sl),
            "tp": float(tp),
        }
        result = mt5.order_send(request)
        return bool(result and result.retcode == mt5.TRADE_RETCODE_DONE)
