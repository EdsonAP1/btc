from app.core.metrics import compute_metrics


def _trade(pnl, close_time="2026-01-02T10:00:00+00:00", side="buy", r=None):
    return {
        "pnl": pnl,
        "status": "closed",
        "side": side,
        "close_time": close_time,
        "r_multiple": r,
    }


def test_metricas_basicas():
    trades = [_trade(100), _trade(-50), _trade(100)]
    m = compute_metrics(trades, initial_balance=1000)
    assert m["trades"] == 3
    assert m["wins"] == 2
    assert m["losses"] == 1
    assert round(m["winrate"], 2) == 66.67
    assert m["net_pnl"] == 150
    assert m["profit_factor"] == 4.0
    assert m["final_equity"] == 1150


def test_drawdown():
    trades = [_trade(100), _trade(-300), _trade(50)]
    m = compute_metrics(trades, initial_balance=1000)
    # equity: 1000 -> 1100 -> 800 -> 850 ; pico 1100, valle 800
    assert m["max_drawdown"] == 300
    assert round(m["max_drawdown_pct"], 2) == 27.27


def test_rachas():
    trades = [_trade(10), _trade(10), _trade(-5), _trade(-5), _trade(-5), _trade(10)]
    m = compute_metrics(trades, initial_balance=1000)
    assert m["max_win_streak"] == 2
    assert m["max_loss_streak"] == 3


def test_sin_trades_no_rompe():
    m = compute_metrics([], initial_balance=1000)
    assert m["trades"] == 0
    assert m["winrate"] == 0
    assert m["profit_factor"] == 0
    assert m["final_equity"] == 1000
