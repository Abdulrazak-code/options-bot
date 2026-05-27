import requests
import json
from datetime import datetime, timezone, timedelta

import config

_IST = timezone(timedelta(hours=5, minutes=30))
_BASE = "https://api.upstox.com/v2"
_HEADERS = {
    "Authorization": f"Bearer {config.UPSTOX_ACCESS_TOKEN}",
    "Accept": "application/json",
}

# Upstox instrument keys for index spot price
NIFTY_KEY     = "NSE_INDEX|Nifty 50"
BANKNIFTY_KEY = "NSE_INDEX|Nifty Bank"


def get_spot_price(instrument_key: str) -> float:
    """Fetch live spot price for NIFTY or BANKNIFTY index."""
    resp = requests.get(
        f"{_BASE}/market-quote/ltp",
        headers=_HEADERS,
        params={"instrument_key": instrument_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    for key, val in data.items():
        return float(val.get("last_price", 0))
    return 0.0


def get_option_chain(instrument_key: str, expiry_date: str) -> list:
    """
    Fetch option chain for given index and expiry.
    expiry_date format: YYYY-MM-DD
    Returns list of dicts with strike, CE/PE instrument_key and LTP.
    """
    resp = requests.get(
        f"{_BASE}/option/chain",
        headers=_HEADERS,
        params={"instrument_key": instrument_key, "expiry_date": expiry_date},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_expiry_dates(instrument_key: str) -> list:
    """Get available expiry dates for the index options."""
    resp = requests.get(
        f"{_BASE}/option/contract",
        headers=_HEADERS,
        params={"instrument_key": instrument_key},
        timeout=10,
    )
    resp.raise_for_status()
    dates = resp.json().get("data", [])
    return sorted(dates)


def get_ltp(instrument_keys: list) -> dict:
    """Fetch LTP for a list of option instrument keys."""
    joined = ",".join(instrument_keys)
    resp = requests.get(
        f"{_BASE}/market-quote/ltp",
        headers=_HEADERS,
        params={"instrument_key": joined},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    return {k: float(v.get("last_price", 0)) for k, v in data.items()}


def get_atm_strike(spot: float, step: int) -> int:
    """Round spot to nearest strike step (50 for NIFTY, 100 for BANKNIFTY)."""
    return round(spot / step) * step


def find_straddle_instruments(chain: list, atm_strike: int) -> dict:
    """
    From option chain, find CE and PE instrument keys for the ATM strike.
    Returns {"ce_key": ..., "pe_key": ..., "ce_ltp": ..., "pe_ltp": ...}
    """
    result = {}
    for row in chain:
        strike = row.get("strike_price", 0)
        if int(strike) != atm_strike:
            continue
        ce = row.get("call_options", {})
        pe = row.get("put_options", {})
        if ce:
            result["ce_key"] = ce.get("instrument_key", "")
            result["ce_ltp"] = float(ce.get("market_data", {}).get("ltp", 0))
            result["ce_strike"] = atm_strike
        if pe:
            result["pe_key"] = pe.get("instrument_key", "")
            result["pe_ltp"] = float(pe.get("market_data", {}).get("ltp", 0))
            result["pe_strike"] = atm_strike
        break
    return result


def find_iron_fly_instruments(chain: list, atm_strike: int, step: int, wing_steps: int = 2) -> dict:
    """
    Find all 4 legs of an Iron Fly:
      Sell ATM CE + Sell ATM PE
      Buy  OTM CE (atm + wing_steps*step) + Buy OTM PE (atm - wing_steps*step)
    """
    buy_ce_strike = atm_strike + wing_steps * step
    buy_pe_strike = atm_strike - wing_steps * step
    result = {}
    for row in chain:
        strike = int(row.get("strike_price", 0))
        ce = row.get("call_options", {})
        pe = row.get("put_options", {})
        if strike == atm_strike:
            if ce:
                result["sell_ce_key"]    = ce.get("instrument_key", "")
                result["sell_ce_ltp"]    = float(ce.get("market_data", {}).get("ltp", 0))
                result["sell_ce_strike"] = atm_strike
            if pe:
                result["sell_pe_key"]    = pe.get("instrument_key", "")
                result["sell_pe_ltp"]    = float(pe.get("market_data", {}).get("ltp", 0))
                result["sell_pe_strike"] = atm_strike
        if strike == buy_ce_strike and ce:
            result["buy_ce_key"]    = ce.get("instrument_key", "")
            result["buy_ce_ltp"]    = float(ce.get("market_data", {}).get("ltp", 0))
            result["buy_ce_strike"] = buy_ce_strike
        if strike == buy_pe_strike and pe:
            result["buy_pe_key"]    = pe.get("instrument_key", "")
            result["buy_pe_ltp"]    = float(pe.get("market_data", {}).get("ltp", 0))
            result["buy_pe_strike"] = buy_pe_strike
    return result


def find_strangle_instruments(chain: list, atm_strike: int, step: int) -> dict:
    """
    Find OTM CE (ATM + 1 step) and OTM PE (ATM - 1 step) for a strangle.
    Returns same shape as find_straddle_instruments.
    """
    ce_strike = atm_strike + step
    pe_strike = atm_strike - step
    result = {}
    for row in chain:
        strike = int(row.get("strike_price", 0))
        ce = row.get("call_options", {})
        pe = row.get("put_options", {})
        if strike == ce_strike and ce:
            result["ce_key"] = ce.get("instrument_key", "")
            result["ce_ltp"] = float(ce.get("market_data", {}).get("ltp", 0))
            result["ce_strike"] = ce_strike
        if strike == pe_strike and pe:
            result["pe_key"] = pe.get("instrument_key", "")
            result["pe_ltp"] = float(pe.get("market_data", {}).get("ltp", 0))
            result["pe_strike"] = pe_strike
    return result
