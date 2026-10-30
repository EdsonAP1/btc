"""Configuración central del bot.

Todo se guarda en `backend/config.json` y se puede sobrescribir por variables
de entorno. Nada de valores hardcodeados en el resto del código.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
CONFIG_PATH = Path(os.environ.get("BTC_BOT_CONFIG", BACKEND_DIR / "config.json"))

DEFAULTS: dict[str, Any] = {
    "symbol": {
        # "auto" detecta el símbolo BTC disponible en el terminal MT5.
        "mode": "auto",
        "name": None,
        # Se usan si la detección automática falla.
        "fallbacks": ["BTCUSD", "BTCUSD.m", "BTCUSDm", "XBTUSD", "BTCUSDT", "BTCUSD.raw"],
    },
    "timeframe": "M15",
    "mode": "live",  # live = cuenta conectada en MT5 (demo o real) | paper | sim
    "strategy": {
        "name": "ema_rsi_atr",
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
        "exit_on_opposite": True,
        "trend_ema": 0,
        "donchian_period": 20,
        "bb_period": 20,
        "bb_std": 2.0,
        "mr_rsi_low": 30.0,
        "mr_rsi_high": 70.0,
        "use_ml": False,
        "ml_threshold": 0.55,
    },
    "risk": {
        "risk_pct": 1.0,
        "max_positions": 1,
        "max_daily_loss_pct": 3.0,
        "max_trades_per_day": 6,
        "max_drawdown_pct": 15.0,
        "halt_on_drawdown": True,
        "min_free_margin_pct": 30.0,
        # None = límite automático (3x el spread típico del símbolo).
        "max_spread_points": None,
        "lot_min": 0.01,
        "lot_max": 1.0,
        "contract_size": 1.0,
    },
    "management": {
        # Con SL de 2 ATR, 1R = 2 ATR. BE y trailing se miden en ATR; los
        # parciales en R (riesgo asumido).
        "break_even": {
            "enabled": True,
            "trigger_atr": 2.0,
            "offset_atr": 0.05,
        },
        "trailing": {
            "enabled": True,
            "start_atr": 2.0,
            "distance_atr": 2.0,
            "step_atr": 0.15,
        },
        "partials": {
            "enabled": True,
            "steps": [{"at_r": 0.5, "pct": 50.0}],
        },
    },
    "execution": {
        "magic": 770123,
        "deviation": 30,
        "comment": "btc-bot",
    },
    "backtest": {
        "initial_balance": 10000.0,
        # None = usa la mediana de spread de las propias velas.
        "spread_points": None,
        "commission_per_lot": 0.0,
        "bars": 5000,
        "risk_pct": 1.0,
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8000,
    },
    "ui": {
        "refresh_ms": 2000,
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    """Merge recursivo sin mutar los originales."""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    path = Path(path or CONFIG_PATH)
    cfg = copy.deepcopy(DEFAULTS)
    if path.exists():
        try:
            cfg = deep_merge(cfg, json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:  # config rota: no rompemos el arranque
            print(f"[config] JSON inválido en {path}: {exc}. Se usan defaults.")
    cfg = deep_merge(cfg, _env_overrides())
    return cfg


def _env_overrides() -> dict[str, Any]:
    out: dict[str, Any] = {}
    if os.environ.get("BTC_BOT_MODE"):
        out["mode"] = os.environ["BTC_BOT_MODE"]
    if os.environ.get("BTC_BOT_SYMBOL"):
        out["symbol"] = {"mode": "manual", "name": os.environ["BTC_BOT_SYMBOL"]}
    if os.environ.get("BTC_BOT_TIMEFRAME"):
        out["timeframe"] = os.environ["BTC_BOT_TIMEFRAME"]
    if os.environ.get("BTC_BOT_PORT"):
        out["server"] = {"port": int(os.environ["BTC_BOT_PORT"])}
    return out


def save_config(cfg: dict[str, Any], path: Path | str | None = None) -> dict[str, Any]:
    path = Path(path or CONFIG_PATH)
    merged = deep_merge(DEFAULTS, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return merged


def patch_config(patch: dict[str, Any]) -> dict[str, Any]:
    current = load_config()
    return save_config(deep_merge(current, patch))


def ensure_config_file() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return save_config(DEFAULTS)
    return load_config()
