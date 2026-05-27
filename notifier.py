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

    def entry(self, index: str, instruments: dict, net_credit: float,
              max_loss: float, lots: int):
        lot_size = config.NIFTY_LOT_SIZE if index == "NIFTY" else config.BANKNIFTY_LOT_SIZE
        max_profit = round(net_credit * lot_size * lots, 0)
        self.send(
            f"IRON FLY ENTRY\n"
            f"Index: {index} | Lots: {lots} | {'PAPER' if config.PAPER_TRADE else 'LIVE'}\n"
            f"SELL CE {instruments['sell_ce_strike']}: Rs{instruments['sell_ce_ltp']:.1f}\n"
            f"SELL PE {instruments['sell_pe_strike']}: Rs{instruments['sell_pe_ltp']:.1f}\n"
            f"BUY  CE {instruments['buy_ce_strike']}:  Rs{instruments['buy_ce_ltp']:.1f}\n"
            f"BUY  PE {instruments['buy_pe_strike']}:  Rs{instruments['buy_pe_ltp']:.1f}\n"
            f"Net Credit: Rs{net_credit:.1f} | "
            f"Max Profit: Rs{max_profit:.0f} | Max Loss: Rs{max_loss:.0f}"
        )

    def exit(self, index: str, position: dict, pnl: float, reason: str):
        self.send(
            f"IRON FLY EXIT — {reason}\n"
            f"Index: {index}\n"
            f"Sell {position['sell_ce_strike']}/{position['sell_pe_strike']} | "
            f"Buy {position['buy_ce_strike']}/{position['buy_pe_strike']}\n"
            f"Net Credit collected: Rs{position['net_credit']:.1f}\n"
            f"P&L: Rs{pnl:+.0f}"
        )
