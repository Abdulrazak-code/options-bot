import csv
import os
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_LOG_FILE = "trades.csv"
_FIELDS = [
    "timestamp", "action", "index", "strategy",
    "sell_ce_strike", "sell_pe_strike", "buy_ce_strike", "buy_pe_strike",
    "sell_ce_entry", "sell_pe_entry", "buy_ce_entry", "buy_pe_entry",
    "sell_ce_exit",  "sell_pe_exit",  "buy_ce_exit",  "buy_pe_exit",
    "net_credit", "lots", "pnl", "reason",
]


def _ensure_header():
    if not os.path.exists(_LOG_FILE) or os.path.getsize(_LOG_FILE) == 0:
        with open(_LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_FIELDS).writeheader()


def log_trade(action: str, index: str, strategy: str,
              sell_ce_strike: float, sell_pe_strike: float,
              buy_ce_strike: float,  buy_pe_strike: float,
              sell_ce_entry: float,  sell_pe_entry: float,
              buy_ce_entry: float,   buy_pe_entry: float,
              sell_ce_exit: float,   sell_pe_exit: float,
              buy_ce_exit: float,    buy_pe_exit: float,
              net_credit: float, lots: int, pnl: float, reason: str):
    row = {
        "timestamp":      datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S"),
        "action":         action,
        "index":          index,
        "strategy":       strategy,
        "sell_ce_strike": sell_ce_strike,
        "sell_pe_strike": sell_pe_strike,
        "buy_ce_strike":  buy_ce_strike,
        "buy_pe_strike":  buy_pe_strike,
        "sell_ce_entry":  round(sell_ce_entry, 2),
        "sell_pe_entry":  round(sell_pe_entry, 2),
        "buy_ce_entry":   round(buy_ce_entry,  2),
        "buy_pe_entry":   round(buy_pe_entry,  2),
        "sell_ce_exit":   round(sell_ce_exit,  2),
        "sell_pe_exit":   round(sell_pe_exit,  2),
        "buy_ce_exit":    round(buy_ce_exit,   2),
        "buy_pe_exit":    round(buy_pe_exit,   2),
        "net_credit":     round(net_credit, 2),
        "lots":           lots,
        "pnl":            round(pnl, 2),
        "reason":         reason,
    }
    _ensure_header()
    with open(_LOG_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=_FIELDS).writerow(row)
    print(f"[{row['timestamp']}] {action} | {index} {strategy} | "
          f"sell={sell_ce_strike}/{sell_pe_strike} buy={buy_ce_strike}/{buy_pe_strike} | "
          f"credit=Rs{net_credit:.1f} | P&L=Rs{pnl:+.0f} | {reason}")
