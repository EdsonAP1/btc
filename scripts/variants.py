"""Compara variantes de la estrategia (con/sin filtro de tendencia)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.backtester import BacktestConfig, run_backtest
from app.core.metrics import compute_metrics
from app.mt5.client import MT5Client

client = MT5Client()
if not client.connect() or not client.symbol:
    raise SystemExit("MT5 no disponible")
info = client.symbol_info() or {}
point = float(info.get("point") or 0.01)
contract = float(info.get("contract_size") or 1.0)

base = {
    "ema_fast": 9,
    "ema_slow": 100,
    "rsi_period": 14,
    "rsi_long_max": 72.0,
    "rsi_short_min": 28.0,
    "atr_period": 14,
    "sl_atr": 2.0,
    "tp_atr": 2.0,
    "min_atr_pct": 0.02,
    "cooldown_bars": 2,
}

print(f"{'tf':4} {'trend':>6} {'n':>4} {'wr%':>6} {'pnl':>9} {'pf':>6} {'dd%':>6} {'sharpe':>7}")
for tf in ("M15", "H1", "H4"):
    df = client.candles(tf, 5000)
    for trend_ema in (0, 100, 200, 500):
        params = {**base, "trend_ema": trend_ema}
        cfg = BacktestConfig(initial_balance=10000, risk_pct=1.0, spread_points=None, point=point, contract_size=contract)
        result = run_backtest(df, params, cfg)
        m = compute_metrics(result.trades, 10000)
        print(f"{tf:4} {trend_ema:>6} {m['trades']:>4} {m['winrate']:>6.1f} {m['net_pnl']:>9.0f} {m['profit_factor']:>6.2f} {m['max_drawdown_pct']:>6.1f} {m['sharpe']:>7.2f}")

client.disconnect()
