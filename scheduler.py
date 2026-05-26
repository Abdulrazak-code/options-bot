import time
from datetime import datetime, timezone, timedelta

import schedule

import config
from data_fetcher import (
    get_spot_price, get_option_chain, get_expiry_dates, get_ltp,
    get_atm_strike, find_straddle_instruments, find_strangle_instruments,
    NIFTY_KEY, BANKNIFTY_KEY,
)
from order_executor import load_state, save_state, enter_straddle, exit_straddle
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
    return t.replace(hour=9, minute=15, second=0, microsecond=0) <= t < t.replace(hour=15, minute=30, second=0, microsecond=0)


def is_entry_window() -> bool:
    t = ist_now()
    start = t.replace(hour=config.ENTRY_START_HOUR, minute=config.ENTRY_START_MINUTE, second=0, microsecond=0)
    end   = t.replace(hour=config.ENTRY_END_HOUR,   minute=config.ENTRY_END_MINUTE,   second=0, microsecond=0)
    return start <= t <= end


def is_force_exit_time() -> bool:
    t = ist_now()
    return t.hour > config.FORCE_EXIT_HOUR or (t.hour == config.FORCE_EXIT_HOUR and t.minute >= config.FORCE_EXIT_MINUTE)


def _nearest_expiry(dates: list) -> str:
    today = ist_now().date()
    future = [d for d in dates if d >= str(today)]
    return future[0] if future else dates[-1]


def _chain_summary(chain: list, spot: float, step: int, name: str) -> str:
    atm = get_atm_strike(spot, step)
    lines = [f"{name} ATM={atm} spot={spot:.1f}"]
    strikes_shown = [atm - step, atm, atm + step]
    for row in chain:
        strike = int(row.get("strike_price", 0))
        if strike not in strikes_shown:
            continue
        ce = row.get("call_options", {}).get("market_data", {})
        pe = row.get("put_options", {}).get("market_data", {})
        ce_iv = ce.get("iv", 0)
        pe_iv = pe.get("iv", 0)
        ce_ltp = ce.get("ltp", 0)
        pe_ltp = pe.get("ltp", 0)
        ce_oi = ce.get("oi", 0)
        pe_oi = pe.get("oi", 0)
        lines.append(f"  {strike}: CE={ce_ltp:.1f}(IV={ce_iv:.1f}% OI={ce_oi:,}) PE={pe_ltp:.1f}(IV={pe_iv:.1f}% OI={pe_oi:,})")
    return "\n".join(lines)


class OptionsScheduler:
    def __init__(self, state_path: str = "state.json"):
        self._state_path = state_path
        self._engine = ClaudeEngine()
        self._notifier = Notifier()

    def _get_fresh_pnl(self, state: dict) -> tuple:
        """Fetch current CE and PE LTP for open position. Returns (ce_ltp, pe_ltp)."""
        pos = state["position"]
        prices = get_ltp([pos["ce_key"], pos["pe_key"]])
        ce_ltp = prices.get(pos["ce_key"], pos["ce_entry"])
        pe_ltp = prices.get(pos["pe_key"], pos["pe_entry"])
        return ce_ltp, pe_ltp

    def _monitor_position(self, state: dict) -> dict:
        pos = state["position"]
        ce_ltp, pe_ltp = self._get_fresh_pnl(state)
        combined_entry = pos["combined_entry"]
        combined_now = ce_ltp + pe_ltp
        pct_change = (combined_now - combined_entry) / combined_entry * 100 if combined_entry else 0
        lot_size = pos["lot_size"]
        lots = pos["lots"]
        t_str = ist_now().strftime("%H:%M")

        print(f"[{t_str}] {pos['index']} {pos['strategy']} | "
              f"CE={ce_ltp:.1f} PE={pe_ltp:.1f} combined={combined_now:.1f} ({pct_change:+.1f}%)")

        reason = None

        # Hard take-profit
        if pct_change >= config.TAKE_PROFIT_PCT:
            reason = f"take-profit {pct_change:+.1f}%"

        # Hard stop-loss
        elif pct_change <= -config.STOP_LOSS_PCT:
            reason = f"stop-loss {pct_change:+.1f}%"

        # Force exit time
        elif is_force_exit_time():
            reason = f"force exit at {t_str}"

        # Force exit at EOD
        elif ist_now().hour >= 15 and ist_now().minute >= 15:
            reason = f"EOD force exit"

        if reason:
            pnl, new_state = exit_straddle(ce_ltp, pe_ltp, state, reason)
            save_state(new_state, self._state_path)
            log_trade("EXIT", pos["index"], pos["strategy"],
                      pos.get("ce_strike", 0), pos.get("pe_strike", 0),
                      pos["ce_entry"], pos["pe_entry"], ce_ltp, pe_ltp,
                      lots, pnl, reason)
            self._notifier.exit(pos["index"], pos["strategy"],
                                pos.get("ce_strike", 0), pos.get("pe_strike", 0),
                                combined_entry, combined_now, pnl, reason)
            return new_state

        # Ask Claude if 20-35% up — should we exit early?
        if 20 <= pct_change < config.TAKE_PROFIT_PCT:
            decision = self._engine.assess_exit(pos, ce_ltp, pe_ltp, t_str, state)
            save_state(state, self._state_path)
            if decision.get("action") == "EXIT":
                pnl, new_state = exit_straddle(ce_ltp, pe_ltp, state, f"Claude EXIT: {decision.get('reasoning','')}")
                save_state(new_state, self._state_path)
                log_trade("EXIT", pos["index"], pos["strategy"],
                          pos.get("ce_strike", 0), pos.get("pe_strike", 0),
                          pos["ce_entry"], pos["pe_entry"], ce_ltp, pe_ltp,
                          lots, pnl, f"Claude: {decision.get('reasoning','')}")
                self._notifier.exit(pos["index"], pos["strategy"],
                                    pos.get("ce_strike", 0), pos.get("pe_strike", 0),
                                    combined_entry, combined_now, pnl, f"Claude EXIT")
                return new_state

        save_state(state, self._state_path)
        return state

    def _try_entry(self, state: dict) -> dict:
        if not is_entry_window():
            return state

        # Fetch spot prices and chains for both indices
        nifty_spot = get_spot_price(NIFTY_KEY)
        bnf_spot   = get_spot_price(BANKNIFTY_KEY)

        nifty_expiries = get_expiry_dates(NIFTY_KEY)
        bnf_expiries   = get_expiry_dates(BANKNIFTY_KEY)
        nifty_expiry   = _nearest_expiry(nifty_expiries)
        bnf_expiry     = _nearest_expiry(bnf_expiries)

        nifty_chain = get_option_chain(NIFTY_KEY, nifty_expiry)
        bnf_chain   = get_option_chain(BANKNIFTY_KEY, bnf_expiry)

        nifty_summary = _chain_summary(nifty_chain, nifty_spot, 50, "NIFTY")
        bnf_summary   = _chain_summary(bnf_chain, bnf_spot, 100, "BANKNIFTY")

        t_str = ist_now().strftime("%H:%M")
        decision = self._engine.assess_entry(nifty_spot, bnf_spot,
                                             nifty_summary, bnf_summary,
                                             t_str, state)
        save_state(state, self._state_path)

        action = decision.get("action", "SKIP")
        index = decision.get("index")
        strategy = decision.get("strategy", "STRADDLE")
        reasoning = decision.get("reasoning", "")

        print(f"[{t_str}] Claude → {action} | {index} {strategy} | {reasoning}")

        if action != "ENTER" or not index:
            return state

        # Select chain and parameters
        if index == "NIFTY":
            chain, spot, step, lots = nifty_chain, nifty_spot, 50, 1
            expiry = nifty_expiry
        else:
            chain, spot, step, lots = bnf_chain, bnf_spot, 100, 1
            expiry = bnf_expiry

        atm = get_atm_strike(spot, step)

        if strategy == "STRANGLE":
            instruments = find_strangle_instruments(chain, atm, step)
        else:
            instruments = find_straddle_instruments(chain, atm)

        ce_key = instruments.get("ce_key", "")
        pe_key = instruments.get("pe_key", "")
        ce_ltp = instruments.get("ce_ltp", 0)
        pe_ltp = instruments.get("pe_ltp", 0)
        ce_strike_val = instruments.get("ce_strike", atm)
        pe_strike_val = instruments.get("pe_strike", atm)

        if not ce_key or not pe_key or ce_ltp <= 0 or pe_ltp <= 0:
            print(f"[{t_str}] Entry aborted — could not find valid CE/PE instruments")
            return state

        combined = ce_ltp + pe_ltp
        lot_size = config.NIFTY_LOT_SIZE if index == "NIFTY" else config.BANKNIFTY_LOT_SIZE
        cost = combined * lot_size * lots
        print(f"[{t_str}] ENTER {index} {strategy} CE={ce_strike_val} PE={pe_strike_val} | "
              f"CE_LTP={ce_ltp:.1f} PE_LTP={pe_ltp:.1f} combined=Rs{combined:.1f} | "
              f"cost=Rs{cost:.0f} | expiry={expiry}")

        new_state = enter_straddle(index, strategy, ce_key, pe_key, ce_ltp, pe_ltp,
                                   ce_strike_val, pe_strike_val, lots, state)
        save_state(new_state, self._state_path)
        log_trade("ENTER", index, strategy, ce_strike_val, pe_strike_val,
                  ce_ltp, pe_ltp, 0, 0, lots, 0, reasoning)
        self._notifier.entry(index, strategy, ce_strike_val, pe_strike_val, ce_ltp, pe_ltp, lots)
        return new_state

    def run_cycle(self):
        try:
            if not is_market_open():
                return
            state = load_state(self._state_path)

            # Reset daily state at new day
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
        print("Options bot started.")
        self.run_cycle()
        schedule.every(1).minutes.do(self.run_cycle)
        while True:
            schedule.run_pending()
            time.sleep(15)


if __name__ == "__main__":
    OptionsScheduler().start()
