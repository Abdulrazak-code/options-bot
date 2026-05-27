import time
from datetime import date, datetime, timezone, timedelta

import schedule

import config
from data_fetcher import (
    get_spot_price, get_option_chain, get_expiry_dates, get_ltp,
    get_atm_strike, find_iron_fly_instruments,
    NIFTY_KEY, BANKNIFTY_KEY,
)
from order_executor import (
    load_state, save_state, enter_iron_fly, exit_iron_fly, calculate_pnl,
)
from claude_engine import ClaudeEngine
from notifier import Notifier
from logger import log_trade

_IST = timezone(timedelta(hours=5, minutes=30))


def ist_now() -> datetime:
    return datetime.now(_IST)


def is_market_open() -> bool:
    t = ist_now()
    if t.weekday() >= 5:
        return False
    return (t.replace(hour=9, minute=15, second=0, microsecond=0)
            <= t <
            t.replace(hour=15, minute=30, second=0, microsecond=0))


def is_entry_time() -> bool:
    t = ist_now()
    start = t.replace(hour=9, minute=30, second=0, microsecond=0)
    end   = t.replace(hour=10, minute=0,  second=0, microsecond=0)
    return start <= t <= end


def is_expiry_force_exit(index: str) -> bool:
    """Force exit on expiry day at 3 PM — Thursday for NIFTY, Wednesday for BANKNIFTY."""
    t = ist_now()
    expiry_weekday = 3 if index == "NIFTY" else 2
    return t.weekday() == expiry_weekday and t.hour >= 15


def _nearest_expiry(dates: list) -> str:
    today = str(ist_now().date())
    future = [d for d in dates if d >= today]
    return future[0] if future else dates[-1]


def _days_held(position: dict) -> int:
    try:
        entry = date.fromisoformat(position["entry_date"])
        return (ist_now().date() - entry).days
    except Exception:
        return 0


def _chain_summary(chain: list, spot: float, step: int, name: str) -> str:
    atm = get_atm_strike(spot, step)
    buy_ce_strike = atm + config.WING_WIDTH_STEPS * step
    buy_pe_strike = atm - config.WING_WIDTH_STEPS * step
    strikes_shown = {buy_pe_strike, atm, buy_ce_strike}
    lines = [f"{name} ATM={atm} spot={spot:.1f}"]
    for row in chain:
        strike = int(row.get("strike_price", 0))
        if strike not in strikes_shown:
            continue
        ce = row.get("call_options", {}).get("market_data", {})
        pe = row.get("put_options", {}).get("market_data", {})
        lines.append(
            f"  {strike}: CE={ce.get('ltp', 0):.1f}(IV={ce.get('iv', 0):.1f}%) "
            f"PE={pe.get('ltp', 0):.1f}(IV={pe.get('iv', 0):.1f}%)"
        )
    return "\n".join(lines)


class OptionsScheduler:
    def __init__(self, state_path: str = "state.json"):
        self._state_path = state_path
        self._engine = ClaudeEngine()
        self._notifier = Notifier()

    def _get_current_ltps(self, position: dict) -> dict:
        keys = [position["sell_ce_key"], position["sell_pe_key"],
                position["buy_ce_key"],  position["buy_pe_key"]]
        return get_ltp(keys)

    def _do_exit(self, state: dict, current_ltps: dict, reason: str) -> dict:
        pos = state["position"]
        sell_ce_now = current_ltps.get(pos["sell_ce_key"], pos["sell_ce_entry"])
        sell_pe_now = current_ltps.get(pos["sell_pe_key"], pos["sell_pe_entry"])
        buy_ce_now  = current_ltps.get(pos["buy_ce_key"],  pos["buy_ce_entry"])
        buy_pe_now  = current_ltps.get(pos["buy_pe_key"],  pos["buy_pe_entry"])

        pnl, new_state = exit_iron_fly(current_ltps, state, reason)
        save_state(new_state, self._state_path)
        log_trade("EXIT", pos["index"], "IRON_FLY",
                  pos["sell_ce_strike"], pos["sell_pe_strike"],
                  pos["buy_ce_strike"],  pos["buy_pe_strike"],
                  pos["sell_ce_entry"],  pos["sell_pe_entry"],
                  pos["buy_ce_entry"],   pos["buy_pe_entry"],
                  sell_ce_now, sell_pe_now, buy_ce_now, buy_pe_now,
                  pos["net_credit"], pos["lots"], pnl, reason)
        self._notifier.exit(pos["index"], pos, pnl, reason)
        return new_state

    def _monitor_position(self, state: dict) -> dict:
        pos = state["position"]
        current_ltps = self._get_current_ltps(pos)
        unrealized_pnl = calculate_pnl(pos, current_ltps)
        days = _days_held(pos)
        t_str = ist_now().strftime("%H:%M")

        sell_ce_now = current_ltps.get(pos["sell_ce_key"], pos["sell_ce_entry"])
        sell_pe_now = current_ltps.get(pos["sell_pe_key"], pos["sell_pe_entry"])

        print(f"[{t_str}] {pos['index']} IRON_FLY day={days} | "
              f"unrealized=Rs{unrealized_pnl:+.0f} | "
              f"sell={sell_ce_now:.1f}/{sell_pe_now:.1f}")

        if unrealized_pnl <= -config.MAX_LOSS_INR:
            return self._do_exit(state, current_ltps,
                                 f"stop-loss Rs{unrealized_pnl:.0f}")

        if unrealized_pnl >= (config.TARGET_PROFIT_PCT / 100) * pos["max_profit_inr"]:
            return self._do_exit(state, current_ltps,
                                 f"target-profit Rs{unrealized_pnl:.0f}")

        if is_expiry_force_exit(pos["index"]):
            return self._do_exit(state, current_ltps, "expiry force exit")

        if days >= config.MAX_HOLD_DAYS:
            return self._do_exit(state, current_ltps,
                                 f"max hold days ({days})")

        decision = self._engine.assess_exit(pos, current_ltps, t_str, days, state)
        save_state(state, self._state_path)

        if decision.get("action") == "EXIT":
            return self._do_exit(state, current_ltps,
                                 f"Claude: {decision.get('reasoning', '')}")

        save_state(state, self._state_path)
        return state

    def _try_entry(self, state: dict) -> dict:
        if not is_entry_time():
            return state

        nifty_spot = get_spot_price(NIFTY_KEY)
        bnf_spot   = get_spot_price(BANKNIFTY_KEY)

        nifty_expiry = _nearest_expiry(get_expiry_dates(NIFTY_KEY))
        bnf_expiry   = _nearest_expiry(get_expiry_dates(BANKNIFTY_KEY))

        nifty_chain  = get_option_chain(NIFTY_KEY, nifty_expiry)
        bnf_chain    = get_option_chain(BANKNIFTY_KEY, bnf_expiry)

        nifty_summary = _chain_summary(nifty_chain, nifty_spot, 50,  "NIFTY")
        bnf_summary   = _chain_summary(bnf_chain,   bnf_spot,   100, "BANKNIFTY")

        t_str = ist_now().strftime("%H:%M")
        decision = self._engine.assess_entry(nifty_spot, bnf_spot,
                                             nifty_summary, bnf_summary,
                                             t_str, state)
        save_state(state, self._state_path)

        action    = decision.get("action", "SKIP")
        index     = decision.get("index")
        reasoning = decision.get("reasoning", "")
        print(f"[{t_str}] Claude → {action} | {index} | {reasoning}")

        if action != "ENTER" or not index:
            return state

        chain, spot, step = (nifty_chain, nifty_spot, 50) if index == "NIFTY" \
                             else (bnf_chain, bnf_spot, 100)
        expiry = nifty_expiry if index == "NIFTY" else bnf_expiry

        atm = get_atm_strike(spot, step)
        instruments = find_iron_fly_instruments(chain, atm, step, config.WING_WIDTH_STEPS)

        required = ["sell_ce_key", "sell_pe_key", "buy_ce_key", "buy_pe_key"]
        if not all(instruments.get(k) for k in required):
            msg = f"Entry aborted — incomplete Iron Fly chain for {index}"
            print(f"[{t_str}] {msg}")
            self._notifier.send(msg)
            return state

        net_credit = round(
            (instruments["sell_ce_ltp"] + instruments["sell_pe_ltp"]) -
            (instruments["buy_ce_ltp"]  + instruments["buy_pe_ltp"]), 2
        )
        if net_credit <= 0:
            print(f"[{t_str}] Entry aborted — net credit is zero or negative ({net_credit})")
            return state

        lot_size = config.NIFTY_LOT_SIZE if index == "NIFTY" else config.BANKNIFTY_LOT_SIZE
        wing_width_pts = config.WING_WIDTH_STEPS * step
        max_loss_inr = round((wing_width_pts - net_credit) * lot_size, 2)

        if max_loss_inr > config.MAX_LOSS_INR:
            msg = (f"Entry skipped — max loss Rs{max_loss_inr:.0f} "
                   f"> limit Rs{config.MAX_LOSS_INR:.0f} for {index}")
            print(f"[{t_str}] {msg}")
            self._notifier.send(msg)
            return state

        print(f"[{t_str}] ENTER {index} IRON_FLY ATM={atm} | "
              f"credit=Rs{net_credit:.1f} | max_loss=Rs{max_loss_inr:.0f} | expiry={expiry}")

        new_state = enter_iron_fly(index, instruments, 1, state)
        save_state(new_state, self._state_path)
        log_trade("ENTER", index, "IRON_FLY",
                  instruments["sell_ce_strike"], instruments["sell_pe_strike"],
                  instruments["buy_ce_strike"],  instruments["buy_pe_strike"],
                  instruments["sell_ce_ltp"],    instruments["sell_pe_ltp"],
                  instruments["buy_ce_ltp"],     instruments["buy_pe_ltp"],
                  0, 0, 0, 0,
                  net_credit, 1, 0, reasoning)
        self._notifier.entry(index, instruments, net_credit, max_loss_inr, 1)
        return new_state

    def run_cycle(self):
        try:
            if not is_market_open():
                return
            state = load_state(self._state_path)

            today = str(ist_now().date())
            if state.get("last_trade_date") != today:
                state["daily_pnl"] = 0.0
                state["last_trade_date"] = today
                state["claude_spend_usd"] = 0.0
                save_state(state, self._state_path)

            if state.get("position"):
                state = self._monitor_position(state)
            else:
                state = self._try_entry(state)

        except Exception as e:
            print(f"Cycle error: {e}")
            self._notifier.send(f"Options bot error: {e}")

    def start(self):
        print("Options bot started (Iron Fly selling strategy).")
        self.run_cycle()
        schedule.every(30).minutes.do(self.run_cycle)
        while True:
            schedule.run_pending()
            time.sleep(30)


if __name__ == "__main__":
    OptionsScheduler().start()
