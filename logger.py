import csv
import os
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_LOG_FILE = "trades.csv"
_FIELDS = ["timestamp", "action", "index", "strategy", "ce_strike", "pe_strike",
           "ce_entry", "pe_entry", "ce_exit", "pe_exit", "lots",
           "combined_entry", "combined_exit", "pnl", "reason"]


def _ensure_header():
    if not os.path.exists(_LOG_FILE) or os.path.getsize(_LOG_FILE) == 0:
        with open(_LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_FIELDS).writeheader()


def log_trade(action: str, index: str, strategy: str, ce_strike: float, pe_strike: float,
              ce_entry: float, pe_entry: float, ce_exit: float, pe_exit: float,
              lots: int, pnl: float, reason: str):
    combined_entry = ce_entry + pe_entry
    combined_exit = ce_exit + pe_exit
    row = {
        "timestamp": datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "index": index,
        "strategy": strategy,
        "ce_strike": ce_strike,
        "pe_strike": pe_strike,
        "ce_entry": round(ce_entry, 2),
        "pe_entry": round(pe_entry, 2),
        "ce_exit": round(ce_exit, 2),
        "pe_exit": round(pe_exit, 2),
        "lots": lots,
        "combined_entry": round(combined_entry, 2),
        "combined_exit": round(combined_exit, 2),
        "pnl": round(pnl, 2),
        "reason": reason,
    }
    _ensure_header()
    with open(_LOG_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=_FIELDS).writerow(row)
    print(f"[{row['timestamp']}] {action} | {index} {strategy} | "
          f"CE={ce_strike} PE={pe_strike} | combined={combined_entry:.1f}→{combined_exit:.1f} | "
          f"P&L=Rs{pnl:+.0f} | {reason}")
