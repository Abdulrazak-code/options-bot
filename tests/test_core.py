import os
import sys


def _reload_config(overrides: dict):
    for k, v in overrides.items():
        os.environ[k] = v
    if "config" in sys.modules:
        del sys.modules["config"]
    import config
    return config


def test_placeholder():
    assert True


def test_defaults():
    cfg = _reload_config({
        "MAX_LOSS_INR": "5000",
        "WING_WIDTH_STEPS": "2",
        "TARGET_PROFIT_PCT": "50.0",
        "PRODUCT_TYPE": "NRML",
        "MAX_HOLD_DAYS": "5",
    })
    assert cfg.MAX_LOSS_INR == 5000.0
    assert cfg.WING_WIDTH_STEPS == 2
    assert cfg.TARGET_PROFIT_PCT == 50.0
    assert cfg.PRODUCT_TYPE == "NRML"
    assert cfg.MAX_HOLD_DAYS == 5


def test_override_via_env():
    cfg = _reload_config({"MAX_LOSS_INR": "7500"})
    assert cfg.MAX_LOSS_INR == 7500.0


# ---------------------------------------------------------------------------
# data_fetcher tests
# ---------------------------------------------------------------------------

from data_fetcher import find_iron_fly_instruments, get_atm_strike


def _make_chain_row(strike, ce_key, ce_ltp, ce_iv, pe_key, pe_ltp, pe_iv):
    return {
        "strike_price": strike,
        "call_options": {
            "instrument_key": ce_key,
            "market_data": {"ltp": ce_ltp, "iv": ce_iv, "oi": 1000},
        },
        "put_options": {
            "instrument_key": pe_key,
            "market_data": {"ltp": pe_ltp, "iv": pe_iv, "oi": 1000},
        },
    }


def test_find_iron_fly_instruments_nifty():
    chain = [
        _make_chain_row(23900, "CE23900", 30.0, 14.0, "PE23900", 85.0, 16.0),
        _make_chain_row(24000, "CE24000", 120.0, 15.0, "PE24000", 115.0, 15.0),
        _make_chain_row(24100, "CE24100", 45.0, 13.5, "PE24100", 20.0, 13.0),
    ]
    result = find_iron_fly_instruments(chain, atm_strike=24000, step=50, wing_steps=2)
    assert result["sell_ce_key"] == "CE24000"
    assert result["sell_pe_key"] == "PE24000"
    assert result["buy_ce_key"] == "CE24100"
    assert result["buy_pe_key"] == "PE23900"
    assert result["sell_ce_ltp"] == 120.0
    assert result["sell_pe_ltp"] == 115.0
    assert result["buy_ce_ltp"] == 45.0
    assert result["buy_pe_ltp"] == 85.0  # PE at 23900 has ltp=85.0
    assert result["sell_ce_strike"] == 24000
    assert result["sell_pe_strike"] == 24000
    assert result["buy_ce_strike"] == 24100
    assert result["buy_pe_strike"] == 23900


def test_find_iron_fly_missing_strike_returns_partial():
    chain = [
        _make_chain_row(24000, "CE24000", 120.0, 15.0, "PE24000", 115.0, 15.0),
    ]
    result = find_iron_fly_instruments(chain, atm_strike=24000, step=50, wing_steps=2)
    assert result.get("sell_ce_key") == "CE24000"
    assert result.get("buy_ce_key") is None


def test_get_atm_strike():
    assert get_atm_strike(24023.5, 50) == 24000
    assert get_atm_strike(24076.0, 50) == 24100
    assert get_atm_strike(48350.0, 100) == 48400
