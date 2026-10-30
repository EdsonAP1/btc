from app.core.risk import RiskManager

INFO = {
    "tick_value": 0.01,
    "tick_size": 0.01,
    "contract_size": 1.0,
    "volume_min": 0.01,
    "volume_max": 100.0,
    "volume_step": 0.01,
    "spread": 2000,
}


def _manager(**overrides):
    cfg = {
        "risk_pct": 1.0,
        "max_positions": 1,
        "max_daily_loss_pct": 3.0,
        "max_trades_per_day": 6,
        "max_drawdown_pct": 15.0,
        "halt_on_drawdown": True,
        "min_free_margin_pct": 30.0,
        "max_spread_points": None,
        "lot_min": 0.01,
        "lot_max": 10.0,
    }
    cfg.update(overrides)
    return RiskManager(cfg)


def _eval(manager, **overrides):
    kwargs = {
        "account": {"equity": 10000},
        "open_positions": 0,
        "entry_price": 100.0,
        "sl_price": 90.0,
        "symbol_info": INFO,
        "daily_pnl": 0.0,
        "spread_points": 2000,
    }
    kwargs.update(overrides)
    return manager.evaluate(**kwargs)


def test_tamano_de_posicion_por_riesgo():
    decision = _eval(_manager())
    assert decision.allowed
    assert decision.volume == 10.0
    assert decision.risk_amount == 100.0


def test_bloquea_por_maximo_de_posiciones():
    assert not _eval(_manager(), open_positions=1).allowed


def test_bloquea_por_perdida_diaria():
    decision = _eval(_manager(), daily_pnl=-400.0)
    assert not decision.allowed
    assert "pérdida diaria" in decision.reason


def test_bloquea_por_trades_del_dia():
    decision = _eval(_manager(), trades_today=6)
    assert not decision.allowed
    assert "operaciones diarias" in decision.reason


def test_bloquea_por_drawdown_y_pide_halt():
    decision = _eval(_manager(), account={"equity": 8000}, peak_equity=10000)
    assert not decision.allowed
    assert decision.halt is True
    assert "drawdown" in decision.reason


def test_drawdown_no_bloquea_si_esta_debajo():
    decision = _eval(_manager(), account={"equity": 9500}, peak_equity=10000)
    assert decision.allowed


def test_bloquea_por_margen_libre():
    decision = _eval(_manager(), free_margin=1000.0, margin_required=800.0)
    assert not decision.allowed
    assert "margen" in decision.reason


def test_margen_suficiente_permite():
    decision = _eval(_manager(), free_margin=1000.0, margin_required=200.0)
    assert decision.allowed


def test_bloquea_por_spread():
    decision = _eval(_manager(max_spread_points=100), spread_points=500)
    assert not decision.allowed
    assert "spread" in decision.reason


def test_respeta_lote_maximo():
    decision = _eval(_manager(lot_max=0.5), account={"equity": 100000}, sl_price=99.0)
    assert decision.volume == 0.5
