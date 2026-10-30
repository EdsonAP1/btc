from app.mt5.symbols import is_btc_candidate, pick_best, score_symbol


def test_detecta_variantes_de_btc():
    for name in ["BTCUSD", "BTCUSD.m", "BTCUSDm", "XBTUSD", "BTCUSDT", "BITCOIN"]:
        assert is_btc_candidate(name), name


def test_ignora_pares_que_no_son_btc():
    for name in ["ETHUSD", "EURUSD", "SOLUSD"]:
        assert not is_btc_candidate(name)


def test_par_cruzado_puntua_menos_que_btcusd():
    assert score_symbol("ETHBTC") < score_symbol("BTCUSD")


def test_prefiere_btcusd_exacto():
    candidates = [
        {"name": "ETHBTC", "visible": True, "trade_allowed": True},
        {"name": "BTCUSD.m", "visible": True, "trade_allowed": True},
        {"name": "BTCUSD", "visible": False, "trade_allowed": True},
    ]
    best = pick_best(candidates)
    assert best is not None
    assert best["name"] == "BTCUSD"


def test_penaliza_simbolos_no_operables():
    operables = score_symbol("BTCUSD", visible=True, trade_allowed=True)
    bloqueado = score_symbol("BTCUSD", visible=True, trade_allowed=False)
    assert operables > bloqueado


def test_sin_candidatos_devuelve_none():
    assert pick_best([{"name": "EURUSD", "visible": True, "trade_allowed": True}]) is None
