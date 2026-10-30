import asyncio

from app.config import load_config
from app.core.management import ManagedPosition
from app.db import Store
from app.engine import Engine
from app.market import Market

MGMT = {
    "break_even": {"enabled": True, "trigger_atr": 1.0, "offset_atr": 0.05},
    "trailing": {"enabled": True, "start_atr": 1.5, "distance_atr": 2.0, "step_atr": 0.15},
    "partials": {"enabled": True, "steps": [{"at_r": 1.0, "pct": 50.0}]},
}

INFO = {
    "digits": 2,
    "point": 0.01,
    "volume_min": 0.01,
    "volume_max": 100.0,
    "volume_step": 0.01,
    "tick_value": 0.01,
    "tick_size": 0.01,
    "contract_size": 1.0,
    "spread": 10,
}


class FakeBroker:
    is_live = False
    name = "fake"

    def __init__(self, price=100.0, entry=100.0, sl=90.0, tp=120.0, volume=1.0):
        self.price = price
        self.entry = entry
        self.volume = volume
        self.pos = {
            "ticket": 1,
            "side": "buy",
            "volume": volume,
            "open_price": entry,
            "current_price": price,
            "sl": sl,
            "tp": tp,
            "profit": 0.0,
            "magic": 0,
        }
        self.modified = []
        self.closed = []

    def positions(self):
        return [self.pos] if self.pos else []

    def symbol_info(self):
        return INFO

    def modify(self, ticket, sl, tp):
        self.modified.append(sl)
        self.pos["sl"] = sl
        return True

    def close(self, ticket, volume=None):
        self.closed.append(volume)
        pnl = (self.price - self.entry) * float(volume)
        return {"price": self.price, "pnl": pnl, "volume": volume, "remaining": 0.0}

    def account(self):
        return {"equity": 10000.0, "balance": 10000.0, "free_margin": 10000.0}

    def tick(self):
        return {"bid": self.price - 0.5, "ask": self.price + 0.5}

    def margin_for(self, side, volume, price=None):
        return 100.0


def _engine(tmp_path, cfg):
    store = Store(tmp_path / "mgmt.db")
    market = Market(cfg)
    engine = Engine(store, market, cfg)
    return engine, store


def test_engine_aplica_break_even_y_parcial(tmp_path):
    cfg = load_config()
    cfg["management"] = MGMT
    engine, store = _engine(tmp_path, cfg)

    broker = FakeBroker(price=111.0)  # 1R alcanzado (entry 100, SL 90)
    engine.broker = broker
    engine._atr = 5.0
    engine.symbol = "SIM-BTC"
    engine.mode = "sim"

    trade_id = store.add_trade(
        {
            "ticket": 1,
            "symbol": "SIM-BTC",
            "side": "buy",
            "volume": 1.0,
            "open_time": "2026-01-01T00:00:00+00:00",
            "open_price": 100.0,
            "sl": 90.0,
            "tp": 120.0,
            "mode": "sim",
            "status": "open",
        }
    )
    engine._meta[1] = {
        "trade_id": trade_id,
        "risk_amount": 100.0,
        "side": "buy",
        "volume": 1.0,
        "open_price": 100.0,
        "state": ManagedPosition(
            side="buy",
            entry=100.0,
            sl=90.0,
            tp=120.0,
            initial_sl=90.0,
            volume=1.0,
            initial_volume=1.0,
            risk_amount=100.0,
            extreme=100.0,
        ),
    }

    asyncio.run(engine._manage_positions())

    assert broker.modified, "debería haber movido el SL a break-even"
    assert broker.modified[0] == 100.25
    assert broker.closed == [0.5], "debería cerrar el 50% del volumen"
    assert engine._meta[1]["state"].volume == 0.5
    assert store.get_trade(trade_id)["status"] == "open"
    store.close()


def test_engine_cierra_trade_cuando_el_parcial_agota_el_volumen(tmp_path):
    cfg = load_config()
    cfg["management"] = {
        "break_even": {"enabled": False},
        "trailing": {"enabled": False},
        "partials": {"enabled": True, "steps": [{"at_r": 1.0, "pct": 100.0}]},
    }
    engine, store = _engine(tmp_path, cfg)

    broker = FakeBroker(price=111.0)
    engine.broker = broker
    engine._atr = 5.0
    engine.symbol = "SIM-BTC"
    engine.mode = "sim"

    trade_id = store.add_trade(
        {
            "ticket": 1,
            "symbol": "SIM-BTC",
            "side": "buy",
            "volume": 1.0,
            "open_time": "2026-01-01T00:00:00+00:00",
            "open_price": 100.0,
            "sl": 90.0,
            "tp": 120.0,
            "mode": "sim",
            "status": "open",
        }
    )
    engine._meta[1] = {
        "trade_id": trade_id,
        "risk_amount": 100.0,
        "side": "buy",
        "volume": 1.0,
        "open_price": 100.0,
        "state": ManagedPosition(
            side="buy",
            entry=100.0,
            sl=90.0,
            tp=120.0,
            initial_sl=90.0,
            volume=1.0,
            initial_volume=1.0,
            risk_amount=100.0,
            extreme=100.0,
        ),
    }

    asyncio.run(engine._manage_positions())

    trade = store.get_trade(trade_id)
    assert trade["status"] == "closed"
    assert trade["pnl"] == 11.0
    assert 1 not in engine._meta
    store.close()
