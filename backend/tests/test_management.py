from app.core.management import ManagedPosition, apply_management

MGMT = {
    "break_even": {"enabled": True, "trigger_atr": 1.0, "offset_atr": 0.05},
    "trailing": {"enabled": True, "start_atr": 1.5, "distance_atr": 2.0, "step_atr": 0.15},
    "partials": {"enabled": True, "steps": [{"at_r": 1.0, "pct": 50.0}]},
}


def _long(volume=1.0, entry=100.0, sl=90.0):
    return ManagedPosition(
        side="buy",
        entry=entry,
        sl=sl,
        tp=120.0,
        initial_sl=sl,
        volume=volume,
        initial_volume=volume,
        extreme=entry,
    )


def _short(volume=1.0, entry=100.0, sl=110.0):
    return ManagedPosition(
        side="sell",
        entry=entry,
        sl=sl,
        tp=80.0,
        initial_sl=sl,
        volume=volume,
        initial_volume=volume,
        extreme=entry,
    )


def test_break_even_mueve_el_sl():
    state = _long()
    actions = apply_management(state, price=106.0, atr=5.0, config=MGMT, digits=2)
    mods = [a for a in actions if a["type"] == "modify"]
    assert mods and mods[0]["sl"] == 100.25
    assert state.be_done


def test_sin_break_even_si_no_llega_al_trigger():
    state = _long()
    actions = apply_management(state, price=104.0, atr=5.0, config=MGMT, digits=2)
    assert not [a for a in actions if a["type"] == "modify"]
    assert not state.be_done


def test_parcial_cierra_mitad_a_1r():
    state = _long(volume=1.0)
    actions = apply_management(state, price=111.0, atr=5.0, config=MGMT, digits=2)
    partials = [a for a in actions if a["type"] == "partial"]
    assert len(partials) == 1
    assert partials[0]["volume"] == 0.5
    assert state.volume == 0.5
    assert state.partials_done == 1

    # No se repite el mismo parcial.
    actions2 = apply_management(state, price=112.0, atr=5.0, config=MGMT, digits=2)
    assert not [a for a in actions2 if a["type"] == "partial"]


def test_trailing_sube_el_sl():
    state = _long()
    apply_management(state, price=106.0, atr=5.0, config=MGMT, digits=2)  # BE
    actions = apply_management(state, price=120.0, atr=5.0, config=MGMT, digits=2)
    mods = [a for a in actions if a["type"] == "modify"]
    assert mods and mods[-1]["sl"] == 110.0
    assert state.sl == 110.0


def test_trailing_no_baja_el_sl():
    state = _long()
    apply_management(state, price=130.0, atr=5.0, config=MGMT, digits=2)
    sl_before = state.sl
    actions = apply_management(state, price=100.0, atr=5.0, config=MGMT, digits=2)
    assert not [a for a in actions if a["type"] == "modify"]
    assert state.sl == sl_before


def test_short_break_even_y_parcial():
    state = _short(volume=2.0)
    actions = apply_management(state, price=89.0, atr=5.0, config=MGMT, digits=2)
    mods = [a for a in actions if a["type"] == "modify"]
    partials = [a for a in actions if a["type"] == "partial"]
    assert mods and mods[0]["sl"] == 99.75
    assert partials and partials[0]["volume"] == 1.0


def test_todo_desactivado_no_hace_nada():
    state = _long()
    off = {
        "break_even": {"enabled": False},
        "trailing": {"enabled": False},
        "partials": {"enabled": False},
    }
    actions = apply_management(state, price=200.0, atr=5.0, config=off, digits=2)
    assert actions == []
