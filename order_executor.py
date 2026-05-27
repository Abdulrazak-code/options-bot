import json
import os
from datetime import datetime, timezone, timedelta

import requests
import config

_BASE = "https://api.upstox.com/v2"
_HEADERS = {
    "Authorization": f"Bearer {config.UPSTOX_ACCESS_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}
_IST = timezone(timedelta(hours=5, minutes=30))


def load_state(path: str = "state.json") -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {
        "position": None,
        "daily_pnl": 0.0,
        "total_pnl": 0.0,
        "claude_spend_usd": 0.0,
        "last_trade_date": None,
    }


def save_state(state: dict, path: str = "state.json"):
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def _place_order(instrument_key: str, qty: int, side: str) -> str:
    if config.PAPER_TRADE:
        return f"PAPER-{side}-{instrument_key[-6:]}"
    payload = {
        "quantity": qty,
        "product": config.PRODUCT_TYPE,
        "validity": "DAY",
        "price": 0,
        "tag": "options-bot",
        "instrument_token": instrument_key,
        "order_type": "MARKET",
        "transaction_type": side,
        "disclosed_quantity": 0,
        "trigger_price": 0,
        "is_amo": False,
    }
    resp = requests.post(f"{_BASE}/order/place", headers=_HEADERS, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json().get("data", {}).get("order_id", "unknown")


def calculate_pnl(position: dict, current_ltps: dict) -> float:
    """Unrealized P&L for an open Iron Fly. Positive = profit (premium decayed in our favour)."""
    sell_ce = current_ltps.get(position["sell_ce_key"], position["sell_ce_entry"])
    sell_pe = current_ltps.get(position["sell_pe_key"], position["sell_pe_entry"])
    buy_ce  = current_ltps.get(position["buy_ce_key"],  position["buy_ce_entry"])
    buy_pe  = current_ltps.get(position["buy_pe_key"],  position["buy_pe_entry"])
    current_net = (sell_ce + sell_pe) - (buy_ce + buy_pe)
    return round((position["net_credit"] - current_net) * position["lot_size"] * position["lots"], 2)


def enter_iron_fly(index: str, instruments: dict, lots: int, state: dict) -> dict:
    """Place 4-leg Iron Fly. instruments dict from find_iron_fly_instruments()."""
    lot_size = config.NIFTY_LOT_SIZE if index == "NIFTY" else config.BANKNIFTY_LOT_SIZE
    qty = lot_size * lots

    sell_ce_order = _place_order(instruments["sell_ce_key"], qty, "SELL")
    sell_pe_order = _place_order(instruments["sell_pe_key"], qty, "SELL")
    buy_ce_order  = _place_order(instruments["buy_ce_key"],  qty, "BUY")
    buy_pe_order  = _place_order(instruments["buy_pe_key"],  qty, "BUY")

    net_credit = round(
        (instruments["sell_ce_ltp"] + instruments["sell_pe_ltp"]) -
        (instruments["buy_ce_ltp"]  + instruments["buy_pe_ltp"]), 2
    )

    state["position"] = {
        "index": index,
        "strategy": "IRON_FLY",
        "lots": lots,
        "lot_size": lot_size,
        "qty": qty,
        "sell_ce_key":    instruments["sell_ce_key"],
        "sell_ce_strike": instruments["sell_ce_strike"],
        "sell_ce_entry":  instruments["sell_ce_ltp"],
        "sell_pe_key":    instruments["sell_pe_key"],
        "sell_pe_strike": instruments["sell_pe_strike"],
        "sell_pe_entry":  instruments["sell_pe_ltp"],
        "buy_ce_key":     instruments["buy_ce_key"],
        "buy_ce_strike":  instruments["buy_ce_strike"],
        "buy_ce_entry":   instruments["buy_ce_ltp"],
        "buy_pe_key":     instruments["buy_pe_key"],
        "buy_pe_strike":  instruments["buy_pe_strike"],
        "buy_pe_entry":   instruments["buy_pe_ltp"],
        "net_credit":     net_credit,
        "max_profit_inr": round(net_credit * lot_size * lots, 2),
        "entry_date":     datetime.now(_IST).strftime("%Y-%m-%d"),
        "sell_ce_order_id": sell_ce_order,
        "sell_pe_order_id": sell_pe_order,
        "buy_ce_order_id":  buy_ce_order,
        "buy_pe_order_id":  buy_pe_order,
    }
    return state


def exit_iron_fly(current_ltps: dict, state: dict, reason: str) -> tuple:
    """Close all 4 legs. Returns (pnl, new_state)."""
    pos = state["position"]
    qty = pos["qty"]

    if not config.PAPER_TRADE:
        _place_order(pos["sell_ce_key"], qty, "BUY")
        _place_order(pos["sell_pe_key"], qty, "BUY")
        _place_order(pos["buy_ce_key"],  qty, "SELL")
        _place_order(pos["buy_pe_key"],  qty, "SELL")

    pnl = calculate_pnl(pos, current_ltps)
    state["daily_pnl"] = round(state.get("daily_pnl", 0) + pnl, 2)
    state["total_pnl"] = round(state.get("total_pnl", 0) + pnl, 2)
    state["position"] = None
    return pnl, state
