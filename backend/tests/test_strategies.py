import pandas as pd

from app.config import load_config
from app.core.strategy import STRATEGIES, prepare, signal_at
from app.mt5.feed import SimFeed


def _params(name: str, **overrides) -> dict:
    params = dict(load_config()["strategy"])
    params.update({"name": name, "min_atr_pct": 0.0})
    params.update(overrides)
    return params


def _series(n: int = 60, price: float = 100.0) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "time": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=5 * i),
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price,
                "volume": 100.0,
            }
        )
    return pd.DataFrame(rows)


def test_registro_tiene_las_tres_estrategias():
    assert set(STRATEGIES) == {"ema_rsi_atr", "donchian", "mean_reversion"}


def test_donchian_detecta_ruptura():
    df = _series(60, 100.0)
    df.loc[len(df)] = {
        "time": df["time"].iloc[-1] + pd.Timedelta(minutes=5),
        "open": 100.0,
        "high": 106.0,
        "low": 100.0,
        "close": 105.5,
        "volume": 200.0,
    }
    params = _params("donchian", donchian_period=20)
    enriched = prepare(df, params)
    signal = signal_at(enriched, len(enriched) - 1, params)
    assert signal.action == "buy"
    assert signal.sl and signal.sl < signal.price < signal.tp


def test_donchian_sin_ruptura_no_opera():
    df = _series(60, 100.0)
    params = _params("donchian", donchian_period=20)
    enriched = prepare(df, params)
    signal = signal_at(enriched, len(enriched) - 1, params)
    assert signal.action == "flat"


def test_mean_reversion_compra_en_banda_inferior():
    df = SimFeed(seed=11).candles("M5", 3000)
    params = _params("mean_reversion", bb_period=20, bb_std=2.0, mr_rsi_low=35.0, mr_rsi_high=65.0)
    enriched = prepare(df, params)

    found_buy = False
    for i in range(100, len(enriched)):
        signal = signal_at(enriched, i, params)
        if signal.action == "buy":
            row = enriched.iloc[i]
            assert row["close"] <= row["bb_low"]
            found_buy = True
            break
    assert found_buy, "no se encontró ninguna señal de reversión en la serie"


def test_nombre_desconocido_usa_la_estrategia_base():
    df = SimFeed(seed=3).candles("M5", 600)
    params = _params("inexistente")
    enriched = prepare(df, params)
    signal = signal_at(enriched, len(enriched) - 1, params)
    assert signal.action in ("buy", "sell", "flat")


def test_cada_estrategia_produce_senales_distintas():
    df = SimFeed(seed=5).candles("M5", 2000)
    results = {}
    for name in STRATEGIES:
        params = _params(name, trend_ema=200)
        enriched = prepare(df, params)
        results[name] = [signal_at(enriched, i, params).action for i in range(300, len(enriched))]
    assert results["donchian"] != results["ema_rsi_atr"]
    assert results["mean_reversion"] != results["ema_rsi_atr"]
