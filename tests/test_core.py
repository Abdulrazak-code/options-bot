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


# ---------------------------------------------------------------------------
# order_executor tests
# ---------------------------------------------------------------------------

os.environ.setdefault("PAPER_TRADE", "true")
os.environ.setdefault("NIFTY_LOT_SIZE", "75")
os.environ.setdefault("BANKNIFTY_LOT_SIZE", "35")
os.environ.setdefault("PRODUCT_TYPE", "NRML")

from order_executor import calculate_pnl, enter_iron_fly, exit_iron_fly


def _make_position():
    return {
        "index": "NIFTY",
        "strategy": "IRON_FLY",
        "lots": 1,
        "lot_size": 75,
        "qty": 75,
        "sell_ce_key": "CE24000", "sell_ce_strike": 24000, "sell_ce_entry": 120.0,
        "sell_pe_key": "PE24000", "sell_pe_strike": 24000, "sell_pe_entry": 115.0,
        "buy_ce_key":  "CE24100", "buy_ce_strike": 24100,  "buy_ce_entry": 45.0,
        "buy_pe_key":  "PE23900", "buy_pe_strike": 23900,  "buy_pe_entry": 30.0,
        "net_credit": 160.0,
        "max_profit_inr": 12000.0,
        "entry_date": "2026-05-26",
    }


def test_calculate_pnl_profit():
    pos = _make_position()
    ltps = {"CE24000": 80.0, "PE24000": 70.0, "CE24100": 25.0, "PE23900": 15.0}
    # current_net = (80+70)-(25+15) = 110; pnl = (160-110)*75 = 3750
    pnl = calculate_pnl(pos, ltps)
    assert pnl == 3750.0


def test_calculate_pnl_loss():
    pos = _make_position()
    ltps = {"CE24000": 400.0, "PE24000": 2.0, "CE24100": 200.0, "PE23900": 1.0}
    # current_net = (400+2)-(200+1) = 201; pnl = (160-201)*75 = -3075
    pnl = calculate_pnl(pos, ltps)
    assert pnl == -3075.0


def _make_state():
    return {"position": None, "daily_pnl": 0.0, "total_pnl": 0.0,
            "claude_spend_usd": 0.0, "last_trade_date": None}


def _make_instruments():
    return {
        "sell_ce_key": "CE24000", "sell_ce_strike": 24000, "sell_ce_ltp": 120.0,
        "sell_pe_key": "PE24000", "sell_pe_strike": 24000, "sell_pe_ltp": 115.0,
        "buy_ce_key":  "CE24100", "buy_ce_strike": 24100,  "buy_ce_ltp": 45.0,
        "buy_pe_key":  "PE23900", "buy_pe_strike": 23900,  "buy_pe_ltp": 30.0,
    }


def test_enter_iron_fly_paper_trade():
    state = enter_iron_fly("NIFTY", _make_instruments(), 1, _make_state())
    pos = state["position"]
    assert pos is not None
    assert pos["strategy"] == "IRON_FLY"
    assert pos["net_credit"] == 160.0
    assert pos["sell_ce_strike"] == 24000
    assert pos["buy_ce_strike"] == 24100


def test_exit_iron_fly_paper_trade():
    state = enter_iron_fly("NIFTY", _make_instruments(), 1, _make_state())
    ltps = {"CE24000": 80.0, "PE24000": 70.0, "CE24100": 25.0, "PE23900": 15.0}
    pnl, new_state = exit_iron_fly(ltps, state, "test exit")
    assert pnl == 3750.0
    assert new_state["position"] is None
    assert new_state["total_pnl"] == 3750.0


# ---------------------------------------------------------------------------
# logger tests
# ---------------------------------------------------------------------------

import tempfile
from logger import log_trade


# ---------------------------------------------------------------------------
# scheduler time-logic tests
# ---------------------------------------------------------------------------

from unittest.mock import patch
from datetime import datetime, timezone, timedelta as tdelta

_IST = timezone(tdelta(hours=5, minutes=30))


def _mock_ist(hour, minute, weekday=0):
    # weekday 0=Mon ... 6=Sun; use date 2026-05-25 (Mon) + offset
    base = datetime(2026, 5, 25, hour, minute, 0, tzinfo=_IST)
    return base.replace(day=25 + weekday)


import scheduler as sched


def test_is_market_open_weekday():
    with patch("scheduler.ist_now", return_value=_mock_ist(10, 0, weekday=0)):
        assert sched.is_market_open() is True


def test_is_market_open_weekend():
    with patch("scheduler.ist_now", return_value=_mock_ist(10, 0, weekday=5)):
        assert sched.is_market_open() is False


def test_is_entry_time_in_window():
    with patch("scheduler.ist_now", return_value=_mock_ist(9, 45)):
        assert sched.is_entry_time() is True


def test_is_entry_time_outside_window():
    with patch("scheduler.ist_now", return_value=_mock_ist(10, 30)):
        assert sched.is_entry_time() is False


def test_is_expiry_force_exit_nifty_thursday():
    with patch("scheduler.ist_now", return_value=_mock_ist(15, 5, weekday=3)):
        assert sched.is_expiry_force_exit("NIFTY") is True


def test_is_expiry_force_exit_nifty_not_thursday():
    with patch("scheduler.ist_now", return_value=_mock_ist(15, 5, weekday=0)):
        assert sched.is_expiry_force_exit("NIFTY") is False


def test_days_held():
    with patch("scheduler.ist_now", return_value=_mock_ist(10, 0, weekday=2)):
        pos = {"entry_date": "2026-05-25"}
        assert sched._days_held(pos) == 2


# ---------------------------------------------------------------------------
# logger tests
# ---------------------------------------------------------------------------


def test_log_trade_creates_csv():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        tmp = f.name
    import logger as lg
    original = lg._LOG_FILE
    lg._LOG_FILE = tmp
    try:
        log_trade("ENTER", "NIFTY", "IRON_FLY",
                  24000, 24000, 24100, 23900,
                  120.0, 115.0, 45.0, 30.0,
                  0, 0, 0, 0,
                  160.0, 1, 0, "test entry")
        log_trade("EXIT", "NIFTY", "IRON_FLY",
                  24000, 24000, 24100, 23900,
                  120.0, 115.0, 45.0, 30.0,
                  80.0, 70.0, 25.0, 15.0,
                  160.0, 1, 3750.0, "target-profit")
        import csv
        with open(tmp) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert rows[0]["action"] == "ENTER"
        assert rows[1]["action"] == "EXIT"
        assert float(rows[1]["pnl"]) == 3750.0
    finally:
        lg._LOG_FILE = original
        os.unlink(tmp)
