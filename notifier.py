import requests
import config


class Notifier:
    def __init__(self):
        self._token = config.TELEGRAM_BOT_TOKEN
        self._chat_id = config.TELEGRAM_CHAT_ID

    def send(self, message: str):
        if not self._token or not self._chat_id:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": message},
                timeout=5,
            )
        except Exception:
            pass

    def entry(self, index: str, strategy: str, ce_strike, pe_strike, ce_ltp, pe_ltp, lots: int):
        combined = ce_ltp + pe_ltp
        lot_size = config.NIFTY_LOT_SIZE if index == "NIFTY" else config.BANKNIFTY_LOT_SIZE
        cost = combined * lot_size * lots
        self.send(
            f"OPTIONS ENTRY\n"
            f"Index: {index} {strategy}\n"
            f"CE {ce_strike}: Rs{ce_ltp:.1f}\n"
            f"PE {pe_strike}: Rs{pe_ltp:.1f}\n"
            f"Combined: Rs{combined:.1f} | Cost: Rs{cost:.0f}\n"
            f"Lots: {lots} | {'PAPER' if config.PAPER_TRADE else 'LIVE'}"
        )

    def exit(self, index: str, strategy: str, ce_strike, pe_strike,
             entry_combined, exit_combined, pnl: float, reason: str):
        pct = (exit_combined - entry_combined) / entry_combined * 100 if entry_combined else 0
        self.send(
            f"OPTIONS EXIT — {reason}\n"
            f"Index: {index} {strategy}\n"
            f"CE {ce_strike} | PE {pe_strike}\n"
            f"Combined: Rs{entry_combined:.1f} → Rs{exit_combined:.1f} ({pct:+.1f}%)\n"
            f"P&L: Rs{pnl:+.0f}"
        )
