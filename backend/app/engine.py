"""Motor del bot: bucle de velas, señales, riesgo y ejecución."""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from .config import load_config
from .core.broker import MT5Broker, PaperBroker
from .core.management import ManagedPosition, apply_management
from .core.risk import RiskManager
from .core.strategy import evaluate
from .db import Store
from .market import Market
from .mt5.client import TF_SECONDS

log = logging.getLogger("btc-bot.engine")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _floor_time(now: datetime, seconds: int) -> datetime:
    ts = int(now.timestamp())
    return datetime.fromtimestamp(ts - ts % seconds, tz=timezone.utc)


class Engine:
    def __init__(self, store: Store, market: Market, config: dict | None = None) -> None:
        self.store = store
        self.market = market
        self.config = config or load_config()
        self.state = "stopped"  # stopped | starting | running | stopping | error
        self.mode: str | None = None
        self.broker: MT5Broker | PaperBroker | None = None
        self.risk = RiskManager(self.config["risk"])
        self.symbol: str | None = None

        self.started_at: datetime | None = None
        self.last_error: str | None = None
        self.last_signal: dict | None = None
        self.last_bar_time: datetime | None = None
        self.tick: dict | None = None

        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._meta: dict[int, dict] = {}  # ticket -> datos de la operación abierta
        self._last_close_at: datetime | None = None
        self._atr: float = 0.0
        self._peak_equity: float | None = None
        self._halted: bool = False
        self._logs: deque[dict] = deque(maxlen=120)
        self._subscribers: set[Callable[[dict], Any]] = set()
        self._status_lock = asyncio.Lock()

    # ------------------------------------------------------------------ utils
    def _log(self, level: str, message: str) -> None:
        entry = {"time": _utcnow().isoformat(), "level": level, "message": message}
        self._logs.append(entry)
        getattr(log, level if level in ("debug", "info", "warning", "error") else "info")(message)
        self._publish({"type": "log", "data": entry})

    def _publish(self, message: dict) -> None:
        for callback in list(self._subscribers):
            try:
                callback(message)
            except Exception:  # un suscriptor roto no debe tumbar el motor
                pass

    def subscribe(self, callback: Callable[[dict], Any]) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: Callable[[dict], Any]) -> None:
        self._subscribers.discard(callback)

    # ------------------------------------------------------------------ estado
    async def start(self, mode: str | None = None, confirm_real: bool = False) -> dict:
        if self.state in ("running", "starting"):
            return self.status()
        self.state = "starting"
        self.last_error = None
        self._halted = False
        self._atr = 0.0
        self.config = load_config()
        self.risk = RiskManager(self.config["risk"])
        chosen = (mode or self.config.get("mode") or "live").lower()
        if chosen == "mt5":
            chosen = "live"
        if chosen not in ("live", "paper", "sim"):
            raise ValueError(f"modo inválido: {chosen}")

        # En modo live se opera sobre la cuenta que esté logueada en MT5.
        if chosen == "live":
            if not await asyncio.to_thread(self.market.refresh_mt5):
                raise RuntimeError("MT5 no conectado: abrí el terminal y logueate")
            account = await asyncio.to_thread(self.market.client.account) or {}
            if account.get("type") == "real" and not confirm_real:
                raise RuntimeError(
                    "La cuenta conectada es REAL. Confirmá explícitamente para operar en real."
                )

        try:
            self.broker, self.symbol = await asyncio.to_thread(self._build_broker, chosen)
        except Exception as exc:
            self.state = "error"
            self.last_error = str(exc)
            self._log("error", f"no se pudo iniciar: {exc}")
            raise

        self.mode = chosen
        self.started_at = _utcnow()
        self.last_bar_time = None
        self._stop_event = asyncio.Event()
        self._peak_equity = self.store.kv_get("peak_equity") or None
        self.state = "running"
        if chosen == "live":
            try:
                await asyncio.to_thread(self._adopt_positions)
            except Exception as exc:  # noqa: BLE001
                self._log("warning", f"no se pudieron recuperar posiciones abiertas: {exc}")
        self._log("info", f"bot iniciado en modo {chosen} · {self.symbol}")
        self._task = asyncio.create_task(self._loop())
        return self.status()

    def _build_broker(self, mode: str):
        if mode == "live":
            if not self.market.refresh_mt5():
                raise RuntimeError("MT5 no conectado: abrí el terminal y logueate")
            broker = MT5Broker(self.market.client)
            return broker, self.market.client.symbol
        if mode == "sim":
            return PaperBroker(self.market.sim, initial_balance=self.config["backtest"]["initial_balance"]), self.market.sim.name
        # paper: precios reales si hay MT5, si no simulación
        feed = self.market.client if self.market.refresh_mt5() else self.market.sim
        symbol = getattr(feed, "symbol", None) or getattr(feed, "name", "SIM-BTC")
        return PaperBroker(feed, initial_balance=self.config["backtest"]["initial_balance"]), symbol

    async def stop(self, close_positions: bool = False) -> dict:
        if self.state not in ("running", "starting"):
            return self.status()
        self.state = "stopping"
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        if close_positions and self.broker:
            await asyncio.to_thread(self._close_all)
        elif self.broker is not None and not self.broker.is_live:
            # En paper/sim las posiciones viven en memoria: se cierran al detener.
            await asyncio.to_thread(self._close_all)
        self.state = "stopped"
        self._log("info", "bot detenido")
        return self.status()

    def _close_all(self) -> None:
        if not self.broker:
            return
        for pos in self.broker.positions():
            try:
                result = self.broker.close(pos["ticket"])
                self._record_close_by_ticket(pos["ticket"], float(result.get("price") or 0), result)
            except Exception as exc:  # noqa: BLE001
                self._log("error", f"no se pudo cerrar {pos['ticket']}: {exc}")

    # -------------------------------------------------------------------- loop
    async def _loop(self) -> None:
        tf = self.config.get("timeframe", "M5")
        seconds = TF_SECONDS.get(tf, 300)
        try:
            while not self._stop_event.is_set() and not self._halted:
                try:
                    await self._step(seconds)
                except Exception as exc:  # noqa: BLE001
                    self._log("error", f"error en ciclo: {exc}")
                    self.last_error = str(exc)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
        finally:
            self._task = None
            if self._halted and self.state == "running":
                self.state = "stopped"
                self._log("error", "bot detenido automáticamente por límite de riesgo")

    async def _step(self, seconds: int) -> None:
        assert self.broker is not None
        self.tick = await asyncio.to_thread(self.broker.tick)
        await self._sync_positions()
        await self._manage_positions()
        await self._update_peak_equity()

        now = _utcnow()
        bar_time = _floor_time(now, seconds)
        new_bar = self.last_bar_time is None or bar_time > self.last_bar_time
        if new_bar:
            self.last_bar_time = bar_time
            await self._on_bar()

        self._publish({"type": "status", "data": await asyncio.to_thread(self.status)})

    async def _on_bar(self) -> None:
        assert self.broker is not None
        tf = self.config.get("timeframe", "M5")
        try:
            df = await asyncio.to_thread(self.broker.candles, tf, 600)
        except Exception as exc:  # noqa: BLE001
            self._log("error", f"sin velas: {exc}")
            return
        if df is None or len(df) < 80:
            return

        # La última vela está en formación: operamos sobre la última cerrada.
        closed = df.iloc[:-1].reset_index(drop=True)
        params = self.config["strategy"]
        ml_prob = self._ml_probability(closed, params)
        signal = await asyncio.to_thread(evaluate, closed, params, ml_prob)

        self.last_signal = {**signal.as_dict(), "time": _utcnow().isoformat()}
        self._publish({"type": "signal", "data": self.last_signal})
        self._atr = float(signal.atr or 0.0)

        positions = await asyncio.to_thread(self.broker.positions)
        mine = [p for p in positions if self._is_mine(p)]

        # Salida por señal contraria.
        if mine and self.config["strategy"].get("exit_on_opposite", True):
            for pos in mine:
                if signal.action != "flat" and signal.action != pos["side"]:
                    self._log("info", f"señal contraria: cierro {pos['side']} {pos['ticket']}")
                    await self._close_ticket(int(pos["ticket"]))
            mine = [p for p in positions if self._is_mine(p)]

        if signal.action == "flat" or mine:
            return
        if not signal.sl or not signal.tp:
            return

        # Enfriamiento tras cerrar: misma regla que el backtester.
        cooldown_bars = int(params.get("cooldown_bars", 0) or 0)
        if cooldown_bars > 0 and self._last_close_at is not None:
            window = cooldown_bars * TF_SECONDS.get(tf, 300)
            elapsed = (_utcnow() - self._last_close_at).total_seconds()
            if elapsed < window:
                self._log("info", f"cooldown activo: {int(elapsed)}s de {window}s")
                return

        account = await asyncio.to_thread(self.broker.account)
        info = await asyncio.to_thread(self.broker.symbol_info)
        spread_points = 0.0
        if self.tick:
            point = float(info.get("point") or 0.01)
            spread_points = (float(self.tick["ask"]) - float(self.tick["bid"])) / point

        # Margen estimado para el volumen que se abriría.
        margin_required = 0.0
        try:
            per_unit = self.risk.value_per_price_unit(info)
            sl_dist = abs(float(signal.price) - float(signal.sl))
            equity_now = float(account.get("equity") or 0.0)
            prov_volume = max(
                float(info.get("volume_min") or 0.01),
                equity_now * float(self.config["risk"].get("risk_pct", 1.0)) / 100.0 / (sl_dist * per_unit),
            ) if sl_dist > 0 and per_unit > 0 else 0.0
            if prov_volume > 0:
                margin_required = float(self.broker.margin_for(signal.action, prov_volume, signal.price))
        except Exception:  # noqa: BLE001
            margin_required = 0.0

        free_margin = account.get("free_margin")
        decision = self.risk.evaluate(
            account=account,
            open_positions=len(mine),
            entry_price=signal.price,
            sl_price=signal.sl,
            symbol_info=info,
            daily_pnl=self._today_pnl(),
            spread_points=spread_points,
            trades_today=self._trades_today(),
            peak_equity=self._peak_equity,
            free_margin=float(free_margin) if free_margin is not None else None,
            margin_required=margin_required,
        )
        if not decision.allowed:
            if decision.halt:
                self._halted = True
                self.last_error = decision.reason
                self._log("error", f"bot detenido por riesgo: {decision.reason}")
                return
            self._log("info", f"entrada bloqueada: {decision.reason}")
            return
        if decision.warning:
            self._log("warning", f"riesgo real mayor al configurado: {decision.warning}")

        await self._open(signal, decision.volume, decision.risk_amount)

    # ---------------------------------------------------------------- entradas
    async def _open(self, signal, volume: float, risk_amount: float) -> None:
        assert self.broker is not None
        info = await asyncio.to_thread(self.broker.symbol_info)
        digits = int(info.get("digits", 2))
        sl = round(float(signal.sl), digits)
        tp = round(float(signal.tp), digits)
        result = await asyncio.to_thread(
            self.broker.open, signal.action, volume, sl, tp, f"btc-bot {signal.reason[:40]}"
        )
        now = _utcnow().isoformat()
        trade_id = self.store.add_trade(
            {
                "ticket": result["ticket"],
                "symbol": self.symbol,
                "side": signal.action,
                "volume": result.get("volume", volume),
                "open_time": now,
                "open_price": result["price"],
                "sl": sl,
                "tp": tp,
                "strategy": self.config["strategy"].get("name", "ema_rsi_atr"),
                "mode": self.mode,
                "status": "open",
                "comment": signal.reason[:120],
            }
        )
        self._meta[int(result["ticket"])] = {
            "trade_id": trade_id,
            "risk_amount": risk_amount,
            "side": signal.action,
            "volume": float(result.get("volume", volume)),
            "open_price": float(result["price"]),
            "open_time": now,
            "state": ManagedPosition(
                side=signal.action,
                entry=float(result["price"]),
                sl=sl,
                tp=tp,
                initial_sl=sl,
                volume=float(result.get("volume", volume)),
                initial_volume=float(result.get("volume", volume)),
                risk_amount=risk_amount,
                extreme=float(result["price"]),
                open_time=now,
            ),
        }
        self._log(
            "info",
            f"{signal.action.upper()} {volume} {self.symbol} @ {result['price']} · SL {sl} · TP {tp}",
        )
        self._publish(
            {
                "type": "trade_open",
                "data": {
                    "ticket": result["ticket"],
                    "side": signal.action,
                    "volume": volume,
                    "price": result["price"],
                    "sl": sl,
                    "tp": tp,
                    "time": now,
                },
            }
        )

    async def _close_ticket(self, ticket: int) -> None:
        assert self.broker is not None
        try:
            result = await asyncio.to_thread(self.broker.close, ticket)
        except Exception as exc:  # noqa: BLE001
            self._log("error", f"cierre falló {ticket}: {exc}")
            return
        self._record_close_by_ticket(ticket, float(result.get("price") or 0), result)

    def _record_close_by_ticket(self, ticket: int, price: float, result: dict | None = None) -> None:
        meta = self._meta.get(ticket)
        if not meta:
            return
        pnl = float((result or {}).get("pnl") or 0.0)
        if self.broker is not None and not self.broker.is_live:
            # En paper el P&L del cierre es solo del volumen restante.
            pnl += float((meta.get("state").realized_pnl if meta.get("state") else 0.0))
        self._finalize_meta(
            ticket,
            price,
            pnl,
            float((result or {}).get("commission") or 0.0),
            float((result or {}).get("swap") or 0.0),
        )

    def _finalize_meta(self, ticket: int, price: float, pnl: float, commission: float = 0.0, swap: float = 0.0) -> None:
        meta = self._meta.pop(ticket, None)
        if not meta:
            return
        self._finalize_trade(
            int(meta["trade_id"]),
            float(meta.get("risk_amount") or 0.0),
            price,
            pnl,
            commission,
            swap,
        )

    def _finalize_trade(
        self,
        trade_id: int,
        risk_amount: float,
        price: float,
        pnl: float,
        commission: float = 0.0,
        swap: float = 0.0,
    ) -> None:
        r_multiple = round(pnl / risk_amount, 2) if risk_amount else 0.0
        self.store.update_trade(
            trade_id,
            status="closed",
            close_time=_utcnow().isoformat(),
            close_price=price,
            pnl=round(pnl, 2),
            commission=commission,
            swap=swap,
            r_multiple=r_multiple,
        )
        self._last_close_at = _utcnow()
        self._log("info", f"operación cerrada · PnL {pnl:.2f} · R {r_multiple}")
        self._publish(
            {
                "type": "trade_close",
                "data": {"trade_id": trade_id, "price": price, "pnl": round(pnl, 2), "r_multiple": r_multiple},
            }
        )

    def _adopt_positions(self) -> None:
        """Al arrancar en real, recupera posiciones abiertas de corridas previas."""
        if not self.broker:
            return
        info = self.broker.symbol_info()
        per_unit = self.risk.value_per_price_unit(info)
        positions = {int(p["ticket"]): p for p in self.broker.positions() if self._is_mine(p)}
        _, open_trades = self.store.list_trades(limit=200, status="open", mode="live")
        by_ticket = {int(t["ticket"]): t for t in open_trades if t.get("ticket")}

        for ticket, pos in positions.items():
            trade = by_ticket.get(ticket)
            sl = float(pos.get("sl") or 0.0)
            risk_amount = (
                abs(float(pos["open_price"]) - sl) * float(pos["volume"]) * per_unit if sl else 0.0
            )
            if trade:
                trade_id = int(trade["id"])
            else:
                trade_id = self.store.add_trade(
                    {
                        "ticket": ticket,
                        "symbol": self.symbol,
                        "side": pos["side"],
                        "volume": pos["volume"],
                        "open_time": pos.get("open_time"),
                        "open_price": pos["open_price"],
                        "sl": sl,
                        "tp": float(pos.get("tp") or 0.0),
                        "strategy": "adoptada",
                        "mode": "live",
                        "status": "open",
                        "comment": "posición existente al iniciar",
                    }
                )
            self._meta[ticket] = {
                "trade_id": trade_id,
                "risk_amount": risk_amount,
                "side": pos["side"],
                "volume": pos["volume"],
                "open_price": pos["open_price"],
                "open_time": pos.get("open_time"),
                "state": ManagedPosition(
                    side=pos["side"],
                    entry=float(pos["open_price"]),
                    sl=sl,
                    tp=float(pos.get("tp") or 0.0),
                    initial_sl=sl,
                    volume=float(pos["volume"]),
                    initial_volume=float(pos["volume"]),
                    risk_amount=risk_amount,
                    extreme=float(pos["open_price"]),
                    open_time=pos.get("open_time"),
                ),
            }

        for ticket, trade in by_ticket.items():
            if ticket in positions:
                continue
            try:
                deals = self.broker.client.position_deals(ticket)
            except Exception:  # noqa: BLE001
                deals = []
            pnl = sum(d["profit"] for d in deals)
            commission = sum(d["commission"] for d in deals)
            swap = sum(d["swap"] for d in deals)
            price = float(deals[-1]["price"]) if deals else 0.0
            self._finalize_trade(int(trade["id"]), 0.0, price, pnl, commission, swap)

    # -------------------------------------------------------- gestión de salida
    async def _manage_positions(self) -> None:
        """Break-even, trailing y cierres parciales sobre las posiciones abiertas."""
        if not self.broker or not self._meta or self._atr <= 0:
            return
        management = self.config.get("management") or {}
        positions = {int(p["ticket"]): p for p in await asyncio.to_thread(self.broker.positions)}
        info = await asyncio.to_thread(self.broker.symbol_info)
        digits = int(info.get("digits", 2))
        lot_step = float(info.get("volume_step") or 0.01)

        for ticket, meta in list(self._meta.items()):
            state = meta.get("state")
            pos = positions.get(ticket)
            if state is None or pos is None:
                continue
            actions = apply_management(
                state,
                price=float(pos["current_price"]),
                atr=self._atr,
                config=management,
                digits=digits,
                lot_step=lot_step,
            )
            for action in actions:
                if action["type"] == "modify":
                    try:
                        ok = await asyncio.to_thread(self.broker.modify, ticket, action["sl"], state.tp)
                    except Exception as exc:  # noqa: BLE001
                        self._log("error", f"no se pudo mover el SL de {ticket}: {exc}")
                        continue
                    if ok:
                        self.store.update_trade(meta["trade_id"], sl=action["sl"])
                        self._log("info", f"SL movido a {action['sl']} (#{ticket})")
                elif action["type"] == "partial":
                    try:
                        result = await asyncio.to_thread(self.broker.close, ticket, action["volume"])
                    except Exception as exc:  # noqa: BLE001
                        self._log("error", f"cierre parcial falló {ticket}: {exc}")
                        continue
                    state.realized_pnl += float(result.get("pnl") or 0.0)
                    self._log(
                        "info",
                        f"parcial {action['volume']} de #{ticket} @ {result.get('price')} · PnL {result.get('pnl')}",
                    )
                    if state.volume <= 0:
                        self._finalize_meta(ticket, float(result.get("price") or 0.0), state.realized_pnl)
                        break

    async def _update_peak_equity(self) -> None:
        if not self.broker:
            return
        try:
            account = await asyncio.to_thread(self.broker.account)
        except Exception:  # noqa: BLE001
            return
        equity = float(account.get("equity") or account.get("balance") or 0.0)
        if equity <= 0:
            return
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity
            self.store.kv_set("peak_equity", equity)

    def _trades_today(self) -> int:
        today = _utcnow().date().isoformat()
        return self.store.count_trades_since(f"{today}T00:00:00", self.mode or "live")

    # ------------------------------------------------------------- posiciones
    def _is_mine(self, pos: dict) -> bool:
        magic = int(self.config["execution"].get("magic", 770123))
        return int(pos.get("magic") or 0) in (0, magic)

    async def _sync_positions(self) -> None:
        """Detecta cierres (SL/TP del broker) y salidas simuladas."""
        if not self.broker or not self._meta:
            return
        positions = {int(p["ticket"]): p for p in await asyncio.to_thread(self.broker.positions)}

        if not self.broker.is_live:
            tick = self.tick or await asyncio.to_thread(self.broker.tick)
            for ticket, meta in list(self._meta.items()):
                pos = positions.get(ticket)
                if pos is None:
                    continue
                price = float(pos["current_price"])
                sl = float(pos["sl"])
                tp = float(pos["tp"])
                hit = (
                    (meta["side"] == "buy" and price <= sl)
                    or (meta["side"] == "buy" and price >= tp)
                    or (meta["side"] == "sell" and price >= sl)
                    or (meta["side"] == "sell" and price <= tp)
                )
                if hit:
                    try:
                        result = await asyncio.to_thread(self.broker.close, ticket)
                        self._record_close_by_ticket(ticket, float(result["price"]), result)
                    except Exception as exc:  # noqa: BLE001
                        self._log("error", f"cierre paper falló: {exc}")
            return

        for ticket in list(self._meta):
            if ticket in positions:
                continue
            meta = self._meta.get(ticket) or {}
            try:
                deals = await asyncio.to_thread(self.broker.client.position_deals, ticket)
            except Exception:  # noqa: BLE001
                deals = []
            if not deals:
                continue
            pnl = sum(d["profit"] for d in deals)
            commission = sum(d["commission"] for d in deals)
            swap = sum(d["swap"] for d in deals)
            last = deals[-1]
            self._record_close_by_ticket(
                ticket,
                float(last["price"]),
                {"pnl": pnl, "commission": commission, "swap": swap},
            )

    # ------------------------------------------------------------------ stats
    def _today_pnl(self) -> float:
        today = _utcnow().date().isoformat()
        total = 0.0
        for trade in self.store.all_closed_trades(self.mode or "live"):
            if str(trade.get("close_time") or "").startswith(today):
                total += float(trade.get("pnl") or 0.0)
        return total

    def _today_stats(self) -> dict:
        today = _utcnow().date().isoformat()
        trades = [t for t in self.store.all_closed_trades(self.mode or "live") if str(t.get("close_time") or "").startswith(today)]
        pnls = [float(t.get("pnl") or 0) for t in trades]
        wins = len([p for p in pnls if p > 0])
        return {
            "trades": len(trades),
            "pnl": round(sum(pnls), 2),
            "winrate": round(wins / len(trades) * 100, 2) if trades else 0.0,
        }

    def _ml_probability(self, df, params: dict) -> float | None:
        if not params.get("use_ml"):
            return None
        try:
            from .ml.model import load_model, predict_proba
            from .ml.features import latest_features

            model = load_model()
            if model is None:
                return None
            features = latest_features(df, params)
            if features is None:
                return None
            return predict_proba(model, features)
        except Exception:  # noqa: BLE001
            return None

    # ----------------------------------------------------------------- status
    def status(self) -> dict:
        mt5 = self.market.status()
        symbol = self.market.symbol_status()
        running = self.state in ("running", "starting")
        positions = []
        if self.broker is not None and running:
            try:
                positions = self.broker.positions()
            except Exception:  # noqa: BLE001
                positions = []
        elif mt5.get("connected"):
            # Bot detenido: igual mostramos lo que hay abierto en la cuenta.
            try:
                positions = self.market.client.positions()
            except Exception:  # noqa: BLE001
                positions = []

        # En paper/sim mostramos la cuenta simulada, no la real de MT5.
        if self.broker is not None and running:
            try:
                account = self.broker.account()
            except Exception:  # noqa: BLE001
                account = mt5.get("account") or {}
        else:
            account = mt5.get("account") or {}

        tick = self.tick
        if tick is None:
            try:
                tick = self.market.tick()
            except Exception:  # noqa: BLE001
                tick = None

        risk_cfg = self.config["risk"]
        equity = float(account.get("equity") or account.get("balance") or 0)
        today = self._today_stats()
        return {
            "bot": {
                "state": self.state,
                "mode": self.mode,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "uptime_sec": int((_utcnow() - self.started_at).total_seconds()) if self.started_at else 0,
                "timeframe": self.config.get("timeframe", "M5"),
                "symbol": self.symbol or symbol["name"],
                "last_signal": self.last_signal,
                "last_bar": self.last_bar_time.isoformat() if self.last_bar_time else None,
                "error": self.last_error,
            },
            "mt5": mt5,
            "symbol": symbol,
            "market": {
                "bid": (tick or {}).get("bid"),
                "ask": (tick or {}).get("ask"),
                "time": (tick or {}).get("time"),
                "spread_points": round(
                    ((float(tick["ask"]) - float(tick["bid"])) / float(symbol["info"].get("point") or 0.01)), 1
                )
                if tick
                else None,
            },
            "account": account,
            "positions": positions,
            "today": today,
            "risk": {
                "equity": round(equity, 2),
                "daily_pnl": today["pnl"],
                "risk_pct": risk_cfg.get("risk_pct"),
                "max_daily_loss_pct": risk_cfg.get("max_daily_loss_pct"),
                "open_positions": len(positions),
                "max_positions": risk_cfg.get("max_positions"),
                "peak_equity": round(self._peak_equity or equity, 2),
                "drawdown_pct": round(self.risk.drawdown_pct(equity, self._peak_equity or equity), 2),
                "max_drawdown_pct": risk_cfg.get("max_drawdown_pct"),
                "trades_today": self._trades_today(),
                "max_trades_per_day": risk_cfg.get("max_trades_per_day"),
                "halted": self._halted,
            },
            "logs": list(self._logs)[-30:],
        }
