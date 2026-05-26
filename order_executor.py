import json
import os
import requests
import config

_BASE = "https://api.upstox.com/v2"
_HEADERS = {
    "Authorization": f"Bearer {config.UPSTOX_ACCESS_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def load_state(path: str = "state.json") -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {
        "position": None,
        "daily_pnl": 0.0,
        "claude_spend_usd": 0.0,
        "last_trade_date": None,
    }


def save_state(state: dict, path: str = "state.json"):
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def _place_order(instrument_key: str, qty: int, side: str) -> str:
    """Place a market order. Returns order_id or 'PAPER-xxx'."""
    if config.PAPER_TRADE:
        return f"PAPER-{side}-{instrument_key[-6:]}"
    payload = {
        "quantity": qty,
        "product": "I",          # Intraday
        "validity": "DAY",
        "price": 0,
        "tag": "options-bot",
        "instrument_token": instrument_key,
        "order_type": "MARKET",
        "transaction_type": side,  # BUY or SELL
        "disclosed_quantity": 0,
        "trigger_price": 0,
        "is_amo": False,
    }
    resp = requests.post(f"{_BASE}/order/place", headers=_HEADERS, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json().get("data", {}).get("order_id", "unknown")


def enter_straddle(index: str, strategy: str, ce_key: str, pe_key: str,
                   ce_ltp: float, pe_ltp: float, ce_strike: int, pe_strike: int,
                   lots: int, state: dict) -> dict:
    lot_size = config.NIFTY_LOT_SIZE if index == "NIFTY" else config.BANKNIFTY_LOT_SIZE
    qty = lot_size * lots

    ce_order = _place_order(ce_key, qty, "BUY")
    pe_order = _place_order(pe_key, qty, "BUY")

    state["position"] = {
        "index": index,
        "strategy": strategy,
        "lots": lots,
        "lot_size": lot_size,
        "qty": qty,
        "ce_key": ce_key,
        "pe_key": pe_key,
        "ce_strike": ce_strike,
        "pe_strike": pe_strike,
        "ce_entry": ce_ltp,
        "pe_entry": pe_ltp,
        "combined_entry": round(ce_ltp + pe_ltp, 2),
        "ce_order_id": ce_order,
        "pe_order_id": pe_order,
    }
    return state


def exit_straddle(ce_ltp: float, pe_ltp: float, state: dict, reason: str) -> tuple:
    """Sell both legs. Returns (pnl, new_state)."""
    pos = state["position"]
    lot_size = pos["lot_size"]
    lots = pos["lots"]
    qty = pos["qty"]

    if not config.PAPER_TRADE:
        _place_order(pos["ce_key"], qty, "SELL")
        _place_order(pos["pe_key"], qty, "SELL")

    combined_exit = ce_ltp + pe_ltp
    combined_entry = pos["combined_entry"]
    pnl = (combined_exit - combined_entry) * lot_size * lots

    state["daily_pnl"] = round(state.get("daily_pnl", 0) + pnl, 2)
    state["position"] = None
    return round(pnl, 2), state
