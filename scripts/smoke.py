"""Smoke test manual: backtest sobre datos simulados y reales de MT5."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import ensure_config_file
from app.core.backtester import BacktestConfig, run_backtest
from app.core.metrics import compute_metrics
from app.mt5.client import MT5Client
from app.mt5.feed import SimFeed

KEYS = ["trades", "winrate", "net_pnl", "profit_factor", "max_drawdown_pct", "sharpe", "return_pct"]


def run(name: str, df, params, cfg: BacktestConfig) -> None:
    t0 = time.perf_counter()
    result = run_backtest(df, params, cfg)
    elapsed = time.perf_counter() - t0
    metrics = compute_metrics(result.trades, cfg.initial_balance)
    print(f"\n=== {name} ===  {len(df)} velas · {elapsed:.2f}s")
    print({k: metrics[k] for k in KEYS})
    if result.trades:
        first = result.trades[0]
        print("primer trade:", {k: first[k] for k in ("side", "volume", "open_price", "close_price", "pnl", "r_multiple")})


def main() -> None:
    config = ensure_config_file()
    params = config["strategy"]
    cfg = BacktestConfig(
        initial_balance=10000,
        risk_pct=1.0,
        spread_points=None,
        point=0.01,
        contract_size=1.0,
    )

    sim = SimFeed()
    run("SIM M5", sim.candles("M5", 5000), params, cfg)

    client = MT5Client()
    if client.connect() and client.symbol:
        print(f"\nMT5 OK · símbolo detectado: {client.symbol}")
        print("candidatos:", [(c["name"], c["score"]) for c in client.candidates[:5]])
        info = client.symbol_info() or {}
        print("info:", {k: info.get(k) for k in ("digits", "point", "contract_size", "spread", "volume_min")})
        df = client.candles("M5", 5000)
        print("velas MT5:", len(df), df["time"].iloc[0], "->", df["time"].iloc[-1])
        cfg.point = float(info.get("point") or 0.01)
        cfg.contract_size = float(info.get("contract_size") or 1.0)
        run("MT5 M5", df, params, cfg)
        print("tick:", client.tick())
        client.disconnect()
    else:
        print("\nMT5 no disponible:", client.last_error)


if __name__ == "__main__":
    main()
