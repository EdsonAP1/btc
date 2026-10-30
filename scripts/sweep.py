"""Barrido rápido de parámetros para elegir defaults sensatos."""
from __future__ import annotations

import itertools
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
print("símbolo", client.symbol, "point", point, "spread", info.get("spread"))

rows = []
for tf in ("M5", "M15", "M30", "H1", "H4"):
    df = client.candles(tf, 5000)
    for fast, slow, sl_mult, tp_mult in itertools.product((9, 21, 34), (55, 100), (1.2, 2.0), (2.0, 3.5)):
        params = {
            "ema_fast": fast,
            "ema_slow": slow,
            "rsi_period": 14,
            "rsi_long_max": 72.0,
            "rsi_short_min": 28.0,
            "atr_period": 14,
            "sl_atr": sl_mult,
            "tp_atr": tp_mult,
            "min_atr_pct": 0.02,
            "cooldown_bars": 2,
        }
        cfg = BacktestConfig(initial_balance=10000, risk_pct=1.0, spread_points=None, point=point, contract_size=contract)
        result = run_backtest(df, params, cfg)
        m = compute_metrics(result.trades, 10000)
        rows.append((tf, fast, slow, sl_mult, tp_mult, m["trades"], m["winrate"], m["net_pnl"], m["profit_factor"], m["max_drawdown_pct"]))

rows.sort(key=lambda r: r[8], reverse=True)
print(f"\n{'tf':4} {'fast':>4} {'slow':>4} {'sl':>4} {'tp':>4} {'n':>4} {'wr%':>6} {'pnl':>9} {'pf':>6} {'dd%':>6}")
for r in rows[:20]:
    print(f"{r[0]:4} {r[1]:>4} {r[2]:>4} {r[3]:>4} {r[4]:>4} {r[5]:>4} {r[6]:>6.1f} {r[7]:>9.0f} {r[8]:>6.2f} {r[9]:>6.1f}")

print("\n--- por timeframe (mejor de cada uno) ---")
seen = set()
for r in rows:
    if r[0] in seen:
        continue
    seen.add(r[0])
    print(f"{r[0]:4} pf={r[8]:.2f} pnl={r[7]:.0f} n={r[5]} wr={r[6]:.1f}% dd={r[9]:.1f}%")

client.disconnect()
