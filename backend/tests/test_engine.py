import asyncio

from app.config import load_config
from app.core.broker import PaperBroker
from app.core.strategy import prepare, signal_at
from app.db import Store
from app.engine import Engine
from app.market import Market


class StubBroker(PaperBroker):
    """PaperBroker que devuelve un histórico fijo (para forzar señales)."""

    def __init__(self, feed, df, **kwargs):
        super().__init__(feed, **kwargs)
        self._df = df

    def candles(self, timeframe, count):
        return self._df


def _config():
    cfg = load_config()
    cfg["timeframe"] = "M5"
    cfg["strategy"].update(
        {
            "ema_fast": 9,
            "ema_slow": 100,
            "rsi_long_max": 80.0,
            "rsi_short_min": 20.0,
            "sl_atr": 2.0,
            "tp_atr": 2.0,
            "min_atr_pct": 0.0,
            "cooldown_bars": 0,
        }
    )
    return cfg


def test_engine_abre_y_cierra_una_operacion(tmp_path):
    cfg = _config()
    store = Store(tmp_path / "bot.db")
    market = Market(cfg)
    params = cfg["strategy"]

    df = market.sim.candles("M5", 900)
    enriched = prepare(df, params)

    index = None
    for i in range(120, len(df) - 2):
        if signal_at(enriched, i, params).action != "flat":
            index = i
            break
    assert index is not None, "no se encontró ninguna señal en la serie de prueba"

    # Dejamos la vela con señal como última vela cerrada (la última fila es la
    # vela en formación, que el motor descarta).
    stub_df = df.iloc[: index + 2].reset_index(drop=True)
    broker = StubBroker(market.sim, stub_df, initial_balance=10000)

    engine = Engine(store, market, cfg)
    engine.broker = broker
    engine.symbol = "SIM-BTC"
    engine.mode = "sim"
    engine.state = "running"

    asyncio.run(engine._on_bar())

    total, trades = store.list_trades()
    assert total == 1
    trade = trades[0]
    assert trade["status"] == "open"
    assert trade["side"] in ("buy", "sell")
    assert trade["sl"] and trade["tp"]
    assert trade["volume"] > 0

    asyncio.run(engine._close_ticket(trade["ticket"]))

    total, trades = store.list_trades()
    assert trades[0]["status"] == "closed"
    assert trades[0]["close_price"] is not None
    assert trades[0]["r_multiple"] is not None
    store.close()


def test_engine_status_no_rompe_sin_broker(tmp_path):
    cfg = _config()
    store = Store(tmp_path / "bot2.db")
    market = Market(cfg)
    engine = Engine(store, market, cfg)
    status = engine.status()
    assert status["bot"]["state"] == "stopped"
    assert "risk" in status
    assert status["symbol"]["name"]
    store.close()
