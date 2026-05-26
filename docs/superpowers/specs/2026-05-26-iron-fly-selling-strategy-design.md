# Iron Fly Selling Strategy — Design Spec
**Date:** 2026-05-26  
**Project:** options-bot  

---

## Goal

Replace the current intraday options-buying strategy with a positional Iron Fly selling strategy. The bot sells options premium (collects money upfront), holds overnight when conditions are good, and exits automatically when profit target or max loss is hit. Claude decides entry, exit, and index selection based on IV and market conditions.

---

## Strategy Summary

**Iron Fly:**
- Sell 1 ATM Call + Sell 1 ATM Put (collect premium)
- Buy 1 OTM Call + Buy 1 OTM Put 2 steps away (hedge/protection)
- Net credit = premium collected − hedge cost = maximum possible profit
- Max loss = wing width − net credit (per unit) × lot size × lots
- Profit zone = market stays near ATM strike through the holding period

**Why Iron Fly over naked selling:**  
Overnight positions without a hedge can blow up on gap opens. The wings cap the max loss at exactly Rs 5,000 regardless of how much the market moves.

---

## Parameters

| Parameter | Value | Configurable |
|-----------|-------|--------------|
| Capital per trade | Rs 1,00,000 | Yes (`.env`) |
| Max loss per trade | Rs 5,000 | Yes (`.env`) |
| Target profit | 50% of net credit collected | Yes (`.env`) |
| Wing width | 2 steps (100pts NIFTY, 200pts BANKNIFTY) | Yes (`.env`) |
| Product type | NRML (overnight allowed) | Yes (`.env`) |
| Max holding days | 5 days | Yes (`.env`) |
| Monitor frequency | Every 30 minutes during market hours | Fixed |
| Entry time | 9:30–10:00 AM IST (after opening volatility settles) | Fixed |
| Index selection | Claude picks NIFTY or BANKNIFTY daily | — |
| Entry decision | Claude evaluates IV — enters only when IV is high enough | — |
| Exit decision | Claude decides daily; overridden by hard stop-loss and target profit | — |

---

## P&L Calculation

At entry:
```
net_credit = (sell_ce_ltp + sell_pe_ltp) - (buy_ce_ltp + buy_pe_ltp)
max_profit_inr = net_credit × lot_size × lots
max_loss_inr = (wing_width_pts - net_credit) × lot_size × lots  [capped at MAX_LOSS_INR]
```

At any time during the trade:
```
current_net = (current_sell_ce + current_sell_pe) - (current_buy_ce + current_buy_pe)
unrealized_pnl = (net_credit - current_net) × lot_size × lots
```
- Positive unrealized_pnl = position moving in our favour (premium decaying)
- Negative unrealized_pnl = position moving against us

Exit triggers (in priority order):
1. `unrealized_pnl <= -MAX_LOSS_INR` → hard stop, exit immediately
2. `unrealized_pnl >= TARGET_PROFIT_PCT% × max_profit_inr` → take profit, exit
3. Claude says EXIT → exit
4. Days held >= MAX_HOLD_DAYS → force exit
5. Expiry day at 3:00 PM → force exit before expiry (Thursday for NIFTY, Wednesday for BANKNIFTY)

---

## File-by-File Changes

### `config.py`
Add:
- `MAX_LOSS_INR` (default 5000)
- `WING_WIDTH_STEPS` (default 2)
- `TARGET_PROFIT_PCT` (default 50.0 — percentage of max credit to lock in)
- `PRODUCT_TYPE` (default "NRML")
- `MAX_HOLD_DAYS` (default 5)

Remove:
- `TAKE_PROFIT_PCT`, `STOP_LOSS_PCT` (replaced by INR-based limits)
- `FORCE_EXIT_HOUR`, `FORCE_EXIT_MINUTE`, `ENTRY_START/END` (Claude-driven now)

### `data_fetcher.py`
Add `find_iron_fly_instruments(chain, atm_strike, step, wing_steps)`:
- Returns: `sell_ce_key`, `sell_pe_key`, `buy_ce_key`, `buy_pe_key` and their LTPs and strikes
- sell strikes = ATM, buy_ce_strike = ATM + (wing_steps × step), buy_pe_strike = ATM - (wing_steps × step)

Update `get_ltp()` to handle 4 keys at once (already supports lists, no change needed).

### `order_executor.py`
Replace `enter_straddle` / `exit_straddle` with:

`enter_iron_fly(index, sell_ce_key, sell_pe_key, buy_ce_key, buy_pe_key, ltps, strikes, lots, state)`:
- Places 2 SELL orders + 2 BUY orders with product=NRML
- Stores full position in state: all 4 keys, strikes, entry LTPs, net_credit, max_profit_inr, entry_date

`exit_iron_fly(current_ltps, state, reason)`:
- Places 2 BUY orders (close sells) + 2 SELL orders (close buys) with product=NRML
- Calculates final P&L
- Returns (pnl, new_state)

### `claude_engine.py`
New system prompt focused on:
- Options selling: high IV = good time to sell, low IV = skip
- Iron Fly context: profit from time decay and range-bound movement
- Multi-day holding: assess whether to hold or exit based on premium remaining and market regime
- Index selection criteria: pick whichever has higher IV / better premium

Update `assess_entry()`:
- Input includes IV levels from chain summary for both indices
- Output: ENTER/SKIP + index + confidence + reasoning

Update `assess_exit()`:
- Input includes days held, premium remaining as % of original credit, current market conditions
- Output: EXIT/HOLD + reasoning

### `scheduler.py`
Major rewrite:
- `is_entry_time()`: true between 9:30–10:00 AM (window so missed cycles are retried)
- `_try_entry()`: fetches chain, finds Iron Fly instruments, calculates net credit, checks max loss fits within Rs 5,000 before entering
- `_monitor_position()`: fetches 4-leg LTPs, calculates unrealized P&L, checks hard stop and target, asks Claude if neither triggered
- `run_cycle()`: runs every 30 minutes; handles both entry and monitoring
- No more `FORCE_EXIT_HOUR` — Claude + hard limits drive exit

### `logger.py`
Add columns: `buy_ce_entry`, `buy_pe_entry`, `buy_ce_exit`, `buy_pe_exit`, `net_credit`

### `notifier.py`
Update `entry()` and `exit()` messages to show all 4 legs and net credit collected.

---

## Error Handling

- If Iron Fly instruments not found (illiquid chain): skip entry, notify via Telegram
- If net credit ≤ 0 (hedge costs more than premium): skip entry
- If calculated max loss > MAX_LOSS_INR: skip entry, notify
- If any leg order fails during exit: retry once, then notify and log as partial exit
- API errors during monitoring: log, notify, continue (do not exit on transient errors)

---

## State Structure

```json
{
  "position": {
    "index": "NIFTY",
    "strategy": "IRON_FLY",
    "lots": 1,
    "lot_size": 75,
    "qty": 75,
    "sell_ce_key": "...", "sell_ce_strike": 24000, "sell_ce_entry": 120.5,
    "sell_pe_key": "...", "sell_pe_strike": 24000, "sell_pe_entry": 115.0,
    "buy_ce_key": "...",  "buy_ce_strike": 24100, "buy_ce_entry": 45.0,
    "buy_pe_key": "...",  "buy_pe_strike": 23900, "buy_pe_entry": 42.0,
    "net_credit": 148.5,
    "max_profit_inr": 11137.5,
    "entry_date": "2026-05-26"
  },
  "daily_pnl": 0.0,
  "total_pnl": 0.0,
  "claude_spend_usd": 0.0,
  "last_trade_date": null
}
```

---

## What Does Not Change

- `.env` loading via `config.py`
- Telegram notification flow (`notifier.py` structure)
- Paper trade mode (`PAPER_TRADE=true` still works)
- `get_spot_price`, `get_option_chain`, `get_expiry_dates`, `get_ltp` in `data_fetcher.py`
- CSV trade log format (columns added, existing ones kept)
