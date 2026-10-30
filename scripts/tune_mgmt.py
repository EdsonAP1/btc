"""Busca un set de gestión de salida que no empeore M15 ni H4."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import load_config
from app.core.backtester import BacktestConfig, run_backtest
from app.core.metrics import compute_metrics
from app.mt5.client import MT5Client

client = MT5Client()
if not client.connect() or not client.symbol:
    raise SystemExit("MT5 no disponible")
info = client.symbol_info() or {}
cfg = load_config()
params = cfg["strategy"]

data = {tf: client.candles(tf, 5000) for tf in ("M15", "H4")}

rows = []
for be_trigger, trail_start, at_r in itertools.product((1.0, 1.5, 2.0), (1.5, 2.0, 2.5), (1.0, 1.5, 2.0)):
    mgmt = {
        "break_even": {"enabled": True, "trigger_atr": be_trigger, "offset_atr": 0.05},
        "trailing": {"enabled": True, "start_atr": trail_start, "distance_atr": 2.0, "step_atr": 0.15},
        "partials": {"enabled": True, "steps": [{"at_r": at_r, "pct": 50.0}]},
    }
    res = {}
    for tf, df in data.items():
        bt = BacktestConfig(
            initial_balance=10000,
            risk_pct=1.0,
            spread_points=None,
            point=float(info.get("point") or 0.01),
            contract_size=float(info.get("contract_size") or 1.0),
            management=mgmt,
        )
        m = compute_metrics(run_backtest(df, params, bt).trades, 10000)
        res[tf] = m
    rows.append((be_trigger, trail_start, at_r, res["M15"], res["H4"]))

rows.sort(key=lambda r: (r[3]["profit_factor"] + r[4]["profit_factor"]), reverse=True)
print(f"{'BE':>4} {'trail':>5} {'atR':>4} | {'M15 pf':>7} {'M15 pnl':>8} {'M15 dd':>7} | {'H4 pf':>6} {'H4 pnl':>8} {'H4 dd':>7}")
for be, tr, atr, m15, h4 in rows[:12]:
    print(
        f"{be:>4} {tr:>5} {atr:>4} | {m15['profit_factor']:>7.2f} {m15['net_pnl']:>8.0f} {m15['max_drawdown_pct']:>7.1f} "
        f"| {h4['profit_factor']:>6.2f} {h4['net_pnl']:>8.0f} {h4['max_drawdown_pct']:>7.1f}"
    )

client.disconnect()
