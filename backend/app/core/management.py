"""Gestión de salida: break-even, trailing stop y cierres parciales.

Este módulo es puro (no toca brokers ni base de datos) y lo usan **el motor en
vivo y el backtester**, así las dos rutas aplican exactamente las mismas reglas.

El llamador pasa el precio actual (o el extremo favorable de la vela) y recibe
una lista de acciones a ejecutar:
    {"type": "partial", "volume": 0.05, "step": 0, "trigger_price": 77100.0}
    {"type": "modify", "sl": 76950.0}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ManagedPosition:
    side: str  # "buy" | "sell"
    entry: float
    sl: float
    tp: float
    initial_sl: float
    volume: float
    initial_volume: float
    risk_amount: float = 0.0
    realized_pnl: float = 0.0
    extreme: float = 0.0  # mejor precio alcanzado a favor
    be_done: bool = False
    partials_done: int = 0
    open_time: Any = None
    entry_bar: int = 0

    @property
    def direction(self) -> int:
        return 1 if self.side == "buy" else -1

    @property
    def risk_distance(self) -> float:
        return abs(float(self.entry) - float(self.initial_sl))


def _improves(new_sl: float, current_sl: float, direction: int) -> bool:
    if direction > 0:
        return new_sl > current_sl + 1e-9
    return new_sl < current_sl - 1e-9


def _round_lot(volume: float, step: float) -> float:
    if step <= 0:
        step = 0.01
    return round(round(volume / step) * step, 8)


def apply_management(
    state: ManagedPosition,
    *,
    price: float,
    atr: float,
    config: dict,
    digits: int = 2,
    lot_step: float = 0.01,
) -> list[dict]:
    """Aplica las reglas sobre `state` y devuelve las acciones a ejecutar."""
    actions: list[dict] = []
    price = float(price)
    direction = state.direction
    risk_distance = state.risk_distance
    if risk_distance <= 0 or atr <= 0 or state.volume <= 0:
        return actions

    # Extremo favorable (para trailing).
    if state.extreme == 0.0:
        state.extreme = state.entry
    state.extreme = max(state.extreme, price) if direction > 0 else min(state.extreme, price)

    # ------------------------------------------------------------ parciales
    partials_cfg = config.get("partials") or {}
    if partials_cfg.get("enabled"):
        steps = partials_cfg.get("steps") or []
        for index, step in enumerate(steps):
            if index < state.partials_done:
                continue
            at_r = float(step.get("at_r", 1.0))
            pct = float(step.get("pct", 50.0))
            target = state.entry + direction * at_r * risk_distance
            reached = price >= target if direction > 0 else price <= target
            if not reached:
                break
            volume = _round_lot(state.initial_volume * pct / 100.0, lot_step)
            volume = min(volume, state.volume)
            if volume <= 0:
                state.partials_done = index + 1
                continue
            actions.append(
                {"type": "partial", "volume": volume, "step": index, "trigger_price": target}
            )
            state.volume = round(state.volume - volume, 8)
            state.partials_done = index + 1
            if state.volume <= 1e-9:
                state.volume = 0.0
                return actions

    # ------------------------------------------------------------ break-even
    be_cfg = config.get("break_even") or {}
    if be_cfg.get("enabled") and not state.be_done:
        trigger = float(be_cfg.get("trigger_atr", 1.0)) * atr
        if (price - state.entry) * direction >= trigger:
            offset = float(be_cfg.get("offset_atr", 0.0)) * atr
            new_sl = round(state.entry + direction * offset, digits)
            state.be_done = True
            if _improves(new_sl, state.sl, direction) and (new_sl - price) * direction < 0:
                state.sl = new_sl
                actions.append({"type": "modify", "sl": new_sl})

    # -------------------------------------------------------------- trailing
    trail_cfg = config.get("trailing") or {}
    if trail_cfg.get("enabled"):
        start = float(trail_cfg.get("start_atr", 1.5)) * atr
        if (state.extreme - state.entry) * direction >= start:
            distance = float(trail_cfg.get("distance_atr", 2.0)) * atr
            step_atr = float(trail_cfg.get("step_atr", 0.0)) * atr
            new_sl = round(state.extreme - direction * distance, digits)
            far_enough = abs(new_sl - state.sl) >= step_atr if step_atr > 0 else True
            if _improves(new_sl, state.sl, direction) and far_enough and (new_sl - price) * direction < 0:
                state.sl = new_sl
                actions.append({"type": "modify", "sl": new_sl})

    return actions
