"""Detección automática del símbolo de BTC en el terminal MT5.

Cada broker nombra el par distinto: BTCUSD, BTCUSD.m, BTCUSDm, XBTUSD,
BTCUSD.raw, BTCUSDT, BITCOIN... Acá puntuamos todos los candidatos y nos
quedamos con el más probable.
"""
from __future__ import annotations

import re

# Nombres "ideales": coincidencia exacta.
_EXACT_BONUS = {
    "BTCUSD": 60,
    "BTCUSDT": 55,
    "XBTUSD": 50,
    "BTCUSD.raw": 45,
    "BTCUSDm": 40,
    "BTCUSD.m": 40,
}

_SUFFIX_RE = re.compile(r"[._\-][A-Za-z0-9]{1,6}$")


def is_btc_candidate(name: str) -> bool:
    upper = name.upper()
    if "BTC" in upper or "XBT" in upper:
        return True
    return "BITCOIN" in upper


def base_name(name: str) -> str:
    """Quita el sufijo del broker: BTCUSD.m -> BTCUSD."""
    upper = name.upper()
    stripped = _SUFFIX_RE.sub("", upper)
    return stripped if stripped else upper


def score_symbol(name: str, *, visible: bool = True, trade_allowed: bool = True) -> int:
    """Puntaje 0-100. Más alto = mejor candidato para operar BTC."""
    if not is_btc_candidate(name):
        return 0

    upper = name.upper()
    base = base_name(name)
    score = 30

    if upper in _EXACT_BONUS:
        score += _EXACT_BONUS[upper]
    elif base in ("BTCUSD", "BTCUSDT", "XBTUSD"):
        score += 25
    elif base.startswith("BTC") or base.startswith("XBT"):
        score += 10

    if "USD" in base:
        score += 12
    if "USDT" in base:
        score += 6
    if "BITCOIN" in base:
        score += 4

    # Penalizamos variantes raras (índices, futuros, pares cruzados).
    if any(tag in upper for tag in ("INDEX", "IDX", "FUT", "PERP", "ZAR", "EUR", "JPY", "GBP")):
        score -= 25

    if visible:
        score += 5
    else:
        score -= 10
    if not trade_allowed:
        score -= 40

    return max(0, min(100, score))


def pick_best(candidates: list[dict]) -> dict | None:
    """candidates: [{"name":..., "visible":..., "trade_allowed":...}]"""
    scored = []
    for item in candidates:
        s = score_symbol(
            item["name"],
            visible=bool(item.get("visible", True)),
            trade_allowed=bool(item.get("trade_allowed", True)),
        )
        if s > 0:
            scored.append({**item, "score": s})
    scored.sort(key=lambda x: (-x["score"], len(x["name"])))
    return scored[0] if scored else None
