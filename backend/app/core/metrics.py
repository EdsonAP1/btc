"""Métricas de rendimiento a partir de una lista de trades cerrados."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

import math


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


def _streaks(pnls: list[float]) -> tuple[int, int]:
    best = worst = cur_win = cur_loss = 0
    for pnl in pnls:
        if pnl > 0:
            cur_win += 1
            cur_loss = 0
        elif pnl < 0:
            cur_loss += 1
            cur_win = 0
        else:
            cur_win = cur_loss = 0
        best = max(best, cur_win)
        worst = max(worst, cur_loss)
    return best, worst


def max_drawdown(equity: list[float]) -> tuple[float, float]:
    """Devuelve (drawdown absoluto, drawdown porcentual)."""
    peak = -math.inf
    worst_abs = 0.0
    worst_pct = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak <= 0:
            continue
        dd = peak - value
        if dd > worst_abs:
            worst_abs = dd
            worst_pct = dd / peak * 100.0
    return worst_abs, worst_pct


def sharpe_ratio(trades: list[dict], initial_balance: float) -> float:
    """Sharpe anualizado sobre retornos diarios (cripto opera 365 días)."""
    daily: dict[str, float] = defaultdict(float)
    for t in trades:
        dt = _parse_dt(t.get("close_time")) or _parse_dt(t.get("open_time"))
        if dt is None:
            continue
        daily[dt.date().isoformat()] += float(t.get("pnl") or 0.0)
    if len(daily) < 3:
        return 0.0
    equity = initial_balance
    returns: list[float] = []
    for day in sorted(daily):
        pnl = daily[day]
        if equity > 0:
            returns.append(pnl / equity)
        equity += pnl
    if len(returns) < 3:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return mean / std * math.sqrt(365)


def compute_metrics(
    trades: Iterable[dict],
    initial_balance: float = 10000.0,
) -> dict[str, Any]:
    closed = [t for t in trades if str(t.get("status", "closed")) == "closed"]
    closed.sort(key=lambda t: str(t.get("close_time") or t.get("open_time") or ""))

    pnls = [float(t.get("pnl") or 0.0) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    equity = initial_balance
    curve = [{"time": None, "equity": round(equity, 2)}]
    for t, pnl in zip(closed, pnls):
        equity += pnl
        curve.append(
            {
                "time": t.get("close_time") or t.get("open_time"),
                "equity": round(equity, 2),
            }
        )

    dd_abs, dd_pct = max_drawdown([p["equity"] for p in curve])
    best_streak, worst_streak = _streaks(pnls)

    by_hour: dict[int, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
    by_weekday: dict[int, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
    by_side: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})

    for t, pnl in zip(closed, pnls):
        dt = _parse_dt(t.get("close_time")) or _parse_dt(t.get("open_time"))
        buckets = [by_side[str(t.get("side", "?")).lower()]]
        if dt is not None:
            buckets += [by_hour[dt.hour], by_weekday[dt.weekday()]]
        for bucket in buckets:
            bucket["trades"] += 1
            bucket["pnl"] += pnl
            if pnl > 0:
                bucket["wins"] += 1

    def _rows(source: dict, key_name: str) -> list[dict]:
        rows = []
        for key, value in sorted(source.items(), key=lambda kv: kv[0]):
            rows.append(
                {
                    key_name: key,
                    "trades": value["trades"],
                    "winrate": round(_safe_div(value["wins"], value["trades"]) * 100, 2),
                    "pnl": round(value["pnl"], 2),
                }
            )
        return rows

    r_multiples = [float(t["r_multiple"]) for t in closed if t.get("r_multiple") is not None]

    return {
        "trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(closed) - len(wins) - len(losses),
        "winrate": round(_safe_div(len(wins), len(closed)) * 100, 2),
        "net_pnl": round(sum(pnls), 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(_safe_div(gross_profit, gross_loss), 2),
        "expectancy": round(_safe_div(sum(pnls), len(closed)), 2),
        "avg_win": round(_safe_div(sum(wins), len(wins)), 2),
        "avg_loss": round(_safe_div(sum(losses), len(losses)), 2),
        "avg_r": round(_safe_div(sum(r_multiples), len(r_multiples)), 2),
        "best_trade": round(max(pnls), 2) if pnls else 0.0,
        "worst_trade": round(min(pnls), 2) if pnls else 0.0,
        "max_win_streak": best_streak,
        "max_loss_streak": worst_streak,
        "max_drawdown": round(dd_abs, 2),
        "max_drawdown_pct": round(dd_pct, 2),
        "sharpe": round(sharpe_ratio(closed, initial_balance), 2),
        "final_equity": round(equity, 2),
        "return_pct": round(_safe_div(equity - initial_balance, initial_balance) * 100, 2),
        "equity_curve": curve,
        "by_hour": _rows(by_hour, "hour"),
        "by_weekday": _rows(by_weekday, "weekday"),
        "by_side": _rows(by_side, "side"),
    }
