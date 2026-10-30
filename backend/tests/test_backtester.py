from app.core.backtester import BacktestConfig, run_backtest
from app.core.metrics import compute_metrics
from app.mt5.feed import SimFeed


def _params():
    return {
        "ema_fast": 9,
        "ema_slow": 21,
        "rsi_period": 14,
        "rsi_long_max": 80.0,
        "rsi_short_min": 20.0,
        "atr_period": 14,
        "sl_atr": 1.5,
        "tp_atr": 2.5,
        "min_atr_pct": 0.0,
        "cooldown_bars": 1,
    }


def test_backtest_genera_trades_y_contabilidad_consistente():
    df = SimFeed(seed=3).candles("M5", 1500)
    cfg = BacktestConfig(initial_balance=10000, risk_pct=1.0, spread_points=None)
    result = run_backtest(df, _params(), cfg)

    assert len(result.trades) > 0
    total = sum(t["pnl"] for t in result.trades)
    assert round(result.stats["final_equity"], 2) == round(10000 + total, 2)

    for trade in result.trades:
        assert trade["volume"] > 0
        assert trade["sl"] > 0 and trade["tp"] > 0
        assert trade["status"] == "closed"


def test_metricas_del_backtest():
    df = SimFeed(seed=5).candles("M15", 1200)
    result = run_backtest(df, _params(), BacktestConfig())
    metrics = compute_metrics(result.trades, 10000)
    assert metrics["trades"] == len(result.trades)
    assert 0 <= metrics["winrate"] <= 100
    assert metrics["final_equity"] == result.stats["final_equity"]


def test_spread_se_resuelve_desde_las_velas():
    df = SimFeed(seed=9).candles("M5", 300)
    auto = run_backtest(df, _params(), BacktestConfig(spread_points=None))
    manual = run_backtest(df, _params(), BacktestConfig(spread_points=123))
    assert auto.stats["spread_points"] == round(float(df["spread"].median()), 1)
    assert manual.stats["spread_points"] == 123.0
