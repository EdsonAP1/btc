"""Compara la estrategia con y sin gestión de salida (BE, trailing, parciales)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import load_config
from app.core.backtester import BacktestConfig, run_backtest
from app.core.metrics import compute_metrics
from app.mt5.client import MT5Client

OFF = {
    "break_even": {"enabled": False},
    "trailing": {"enabled": False},
    "partials": {"enabled": False},
}

client = MT5Client()
if not client.connect() or not client.symbol:
    raise SystemExit("MT5 no disponible")
info = client.symbol_info() or {}
cfg = load_config()
params = cfg["strategy"]

print(f"{'tf':4} {'gestión':10} {'n':>4} {'wr%':>6} {'pnl':>9} {'pf':>6} {'dd%':>6} {'sharpe':>7}")
for tf in ("M15", "H1", "H4"):
    df = client.candles(tf, 5000)
    for label, mgmt in (("sin", OFF), ("con", cfg["management"])):
        bt = BacktestConfig(
            initial_balance=10000,
            risk_pct=1.0,
            spread_points=None,
            point=float(info.get("point") or 0.01),
            contract_size=float(info.get("contract_size") or 1.0),
            management=mgmt,
        )
        result = run_backtest(df, params, bt)
        m = compute_metrics(result.trades, 10000)
        print(
            f"{tf:4} {label:10} {m['trades']:>4} {m['winrate']:>6.1f} {m['net_pnl']:>9.0f} "
            f"{m['profit_factor']:>6.2f} {m['max_drawdown_pct']:>6.1f} {m['sharpe']:>7.2f}"
        )

client.disconnect()
