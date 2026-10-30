"""Gestión de riesgo: tamaño de posición y límites duros."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    volume: float = 0.0
    risk_amount: float = 0.0
    warning: str | None = None
    halt: bool = False


class RiskManager:
    def __init__(self, risk_cfg: dict) -> None:
        self.cfg = risk_cfg

    # ------------------------------------------------------------------ utils
    def value_per_price_unit(self, symbol_info: dict) -> float:
        """USD ganados/pérdidos por 1.0 de movimiento de precio, por lote."""
        tick_value = float(symbol_info.get("tick_value") or 0.0)
        tick_size = float(symbol_info.get("tick_size") or 0.0)
        if tick_value > 0 and tick_size > 0:
            return tick_value / tick_size
        return float(symbol_info.get("contract_size") or 1.0)

    def _round_lot(self, volume: float, info: dict) -> float:
        step = float(info.get("volume_step") or 0.01) or 0.01
        min_lot = float(info.get("volume_min") or self.cfg.get("lot_min", 0.01))
        max_lot = float(info.get("volume_max") or self.cfg.get("lot_max", 1.0))
        max_lot = min(max_lot, float(self.cfg.get("lot_max", max_lot)))
        lots = round(volume / step) * step
        lots = max(min_lot, min(max_lot, lots))
        return round(lots, 4)

    def drawdown_pct(self, equity: float, peak_equity: float | None) -> float:
        if not peak_equity or peak_equity <= 0:
            return 0.0
        return max(0.0, (float(peak_equity) - float(equity)) / float(peak_equity) * 100.0)

    # --------------------------------------------------------------- evaluate
    def evaluate(
        self,
        *,
        account: dict,
        open_positions: int,
        entry_price: float,
        sl_price: float,
        symbol_info: dict,
        daily_pnl: float,
        spread_points: float = 0.0,
        trades_today: int = 0,
        peak_equity: float | None = None,
        free_margin: float | None = None,
        margin_required: float | None = None,
    ) -> RiskDecision:
        equity = float(account.get("equity") or account.get("balance") or 0.0)
        if equity <= 0:
            return RiskDecision(False, "equity inválida")

        # 1) Drawdown de cuenta desde el pico.
        max_dd = float(self.cfg.get("max_drawdown_pct") or 0.0)
        if max_dd > 0:
            dd = self.drawdown_pct(equity, peak_equity)
            if dd >= max_dd:
                return RiskDecision(
                    False,
                    f"drawdown de cuenta {dd:.2f}% ≥ {max_dd:.2f}%",
                    halt=bool(self.cfg.get("halt_on_drawdown", True)),
                )

        # 2) Pérdida diaria.
        max_daily_loss_pct = float(self.cfg.get("max_daily_loss_pct", 3.0))
        if max_daily_loss_pct > 0 and daily_pnl < 0:
            loss_pct = abs(daily_pnl) / equity * 100.0
            if loss_pct >= max_daily_loss_pct:
                return RiskDecision(False, f"límite de pérdida diaria alcanzado ({loss_pct:.2f}%)")

        # 3) Cantidad de operaciones del día.
        max_trades = int(self.cfg.get("max_trades_per_day") or 0)
        if max_trades > 0 and trades_today >= max_trades:
            return RiskDecision(False, f"máximo de operaciones diarias alcanzado ({max_trades})")

        # 4) Posiciones simultáneas.
        max_positions = int(self.cfg.get("max_positions", 1))
        if open_positions >= max_positions:
            return RiskDecision(False, f"máximo de posiciones alcanzado ({max_positions})")

        # 5) Spread.
        max_spread = self.cfg.get("max_spread_points")
        if max_spread is None:
            max_spread = float(symbol_info.get("spread") or 0) * 3.0
        max_spread = float(max_spread or 0)
        if max_spread > 0 and spread_points > max_spread:
            return RiskDecision(False, f"spread alto ({spread_points:.0f} pts)")

        # 6) Margen libre después de abrir.
        min_free_pct = float(self.cfg.get("min_free_margin_pct") or 0.0)
        if min_free_pct > 0 and free_margin is not None and margin_required is not None:
            remaining = float(free_margin) - float(margin_required)
            required = float(free_margin) * min_free_pct / 100.0
            if remaining < required:
                return RiskDecision(
                    False,
                    f"margen libre insuficiente (quedarían {remaining:.2f} de {free_margin:.2f})",
                )

        # 7) Tamaño por riesgo.
        sl_distance = abs(float(entry_price) - float(sl_price))
        if sl_distance <= 0:
            return RiskDecision(False, "distancia de SL inválida")

        risk_pct = float(self.cfg.get("risk_pct", 1.0))
        risk_amount = equity * risk_pct / 100.0
        per_unit = self.value_per_price_unit(symbol_info)
        volume = risk_amount / (sl_distance * per_unit)
        volume = self._round_lot(volume, symbol_info)

        if volume <= 0:
            return RiskDecision(False, "volumen calculado 0")

        # Si el lote mínimo obliga a arriesgar más de lo pedido, avisamos.
        real_risk = volume * sl_distance * per_unit
        warning = None
        if real_risk > risk_amount * 1.25:
            warning = (
                f"lote mínimo {volume} implica riesgo {real_risk:.2f} "
                f"({real_risk / equity * 100:.2f}% del equity) vs. {risk_amount:.2f} objetivo"
            )

        return RiskDecision(True, "ok", volume=volume, risk_amount=risk_amount, warning=warning)
