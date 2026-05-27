# Iron Fly Selling Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the intraday options-buying bot with a positional Iron Fly selling strategy that collects premium, hedges with wings, holds overnight, and lets Claude decide entry/exit.

**Architecture:** Seven files are rewritten in dependency order — config → data_fetcher → order_executor → claude_engine → logger → notifier → scheduler. Each task is independently testable. Pure-logic functions get unit tests; API-dependent code is verified via paper trade smoke test at the end.

**Tech Stack:** Python 3.x, anthropic SDK, requests, schedule, python-dotenv, pytest

---

## File Map

| File | Change |
|------|--------|
| `config.py` | Replace intraday params with Iron Fly params |
| `data_fetcher.py` | Add `find_iron_fly_instruments()` |
| `order_executor.py` | Replace straddle functions with `enter_iron_fly` / `exit_iron_fly` / `calculate_pnl` |
| `claude_engine.py` | New selling-strategy system prompt + updated assess methods |
| `logger.py` | Rewrite for 4-leg schema |
| `notifier.py` | Rewrite entry/exit messages for Iron Fly |
| `scheduler.py` | Full rewrite — 30-min cycle, 4-leg P&L, multi-day hold, Claude-driven exit |
| `state.json` | Reset to new schema |
| `tests/test_core.py` | Unit tests for pure-logic functions |

---

## Task 1: Setup pytest and create test file

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_core.py`

- [ ] **Step 1: Install pytest**

```
pip install pytest
```

Expected output: `Successfully installed pytest-...`

- [ ] **Step 2: Create `tests/__init__.py`**

Create an empty file at `tests/__init__.py`.

- [ ] **Step 3: Create `tests/test_core.py` with placeholder**

```python
# tests/test_core.py
def test_placeholder():
    assert True
```

- [ ] **Step 4: Run tests to confirm setup works**

```
pytest tests/ -v
```

Expected:
```
tests/test_core.py::test_placeholder PASSED
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "chore: add pytest test infrastructure"
```

---

## Task 2: Update `config.py`

**Files:**
- Modify: `config.py`
- Modify: `.env`

- [ ] **Step 1: Write the test**

Replace `tests/test_core.py` content with:

```python
import importlib
import os
import sys


def _reload_config(overrides: dict):
    for k, v in overrides.items():
        os.environ[k] = v
    if "config" in sys.modules:
        del sys.modules["config"]
    import config
    return config


def test_defaults():
    cfg = _reload_config({
        "MAX_LOSS_INR": "5000",
        "WING_WIDTH_STEPS": "2",
        "TARGET_PROFIT_PCT": "50.0",
        "PRODUCT_TYPE": "NRML",
        "MAX_HOLD_DAYS": "5",
    })
    assert cfg.MAX_LOSS_INR == 5000.0
    assert cfg.WING_WIDTH_STEPS == 2
    assert cfg.TARGET_PROFIT_PCT == 50.0
    assert cfg.PRODUCT_TYPE == "NRML"
    assert cfg.MAX_HOLD_DAYS == 5


def test_override_via_env():
    cfg = _reload_config({"MAX_LOSS_INR": "7500"})
    assert cfg.MAX_LOSS_INR == 7500.0
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_core.py::test_defaults -v
```

Expected: FAIL — `MAX_LOSS_INR` not defined in config yet.

- [ ] **Step 3: Rewrite `config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

UPSTOX_API_KEY        = os.getenv("UPSTOX_API_KEY", "")
UPSTOX_API_SECRET     = os.getenv("UPSTOX_API_SECRET", "")
UPSTOX_ACCESS_TOKEN   = os.getenv("UPSTOX_ACCESS_TOKEN", "")
ANTHROPIC_API_KEY     = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "")

PAPER_TRADE           = os.getenv("PAPER_TRADE", "true").lower() == "true"

OPTIONS_CAPITAL_INR   = float(os.getenv("OPTIONS_CAPITAL_INR", "100000"))
NIFTY_LOT_SIZE        = int(os.getenv("NIFTY_LOT_SIZE", "75"))
BANKNIFTY_LOT_SIZE    = int(os.getenv("BANKNIFTY_LOT_SIZE", "35"))

MAX_LOSS_INR          = float(os.getenv("MAX_LOSS_INR", "5000"))
TARGET_PROFIT_PCT     = float(os.getenv("TARGET_PROFIT_PCT", "50.0"))
WING_WIDTH_STEPS      = int(os.getenv("WING_WIDTH_STEPS", "2"))
PRODUCT_TYPE          = os.getenv("PRODUCT_TYPE", "NRML")
MAX_HOLD_DAYS         = int(os.getenv("MAX_HOLD_DAYS", "5"))

CLAUDE_API_BUDGET_STOP_USD = float(os.getenv("CLAUDE_API_BUDGET_STOP_USD", "3.00"))
```

- [ ] **Step 4: Update `.env` — add new keys, remove old intraday keys**

Add these lines to `.env`:
```
MAX_LOSS_INR=5000
TARGET_PROFIT_PCT=50.0
WING_WIDTH_STEPS=2
PRODUCT_TYPE=NRML
MAX_HOLD_DAYS=5
```

Remove these lines from `.env`:
```
TAKE_PROFIT_PCT=40.0
STOP_LOSS_PCT=30.0
FORCE_EXIT_HOUR=13
FORCE_EXIT_MINUTE=30
ENTRY_START_HOUR=9
ENTRY_START_MINUTE=20
ENTRY_END_HOUR=10
ENTRY_END_MINUTE=30
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_core.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add config.py .env tests/test_core.py
git commit -m "feat: update config for Iron Fly selling strategy"
```

---

## Task 3: Update `data_fetcher.py` — add `find_iron_fly_instruments`

**Files:**
- Modify: `data_fetcher.py`
- Modify: `tests/test_core.py`

- [ ] **Step 1: Add the test**

Append to `tests/test_core.py`:

```python
from data_fetcher import find_iron_fly_instruments, get_atm_strike


def _make_chain_row(strike, ce_key, ce_ltp, ce_iv, pe_key, pe_ltp, pe_iv):
    return {
        "strike_price": strike,
        "call_options": {
            "instrument_key": ce_key,
            "market_data": {"ltp": ce_ltp, "iv": ce_iv, "oi": 1000},
        },
        "put_options": {
            "instrument_key": pe_key,
            "market_data": {"ltp": pe_ltp, "iv": pe_iv, "oi": 1000},
        },
    }


def test_find_iron_fly_instruments_nifty():
    chain = [
        _make_chain_row(23900, "CE23900", 30.0, 14.0, "PE23900", 85.0, 16.0),
        _make_chain_row(24000, "CE24000", 120.0, 15.0, "PE24000", 115.0, 15.0),
        _make_chain_row(24100, "CE24100", 45.0, 13.5, "PE24100", 20.0, 13.0),
    ]
    result = find_iron_fly_instruments(chain, atm_strike=24000, step=50, wing_steps=2)
    assert result["sell_ce_key"] == "CE24000"
    assert result["sell_pe_key"] == "PE24000"
    assert result["buy_ce_key"] == "CE24100"
    assert result["buy_pe_key"] == "PE23900"
    assert result["sell_ce_ltp"] == 120.0
    assert result["sell_pe_ltp"] == 115.0
    assert result["buy_ce_ltp"] == 45.0
    assert result["buy_pe_ltp"] == 30.0
    assert result["sell_ce_strike"] == 24000
    assert result["sell_pe_strike"] == 24000
    assert result["buy_ce_strike"] == 24100
    assert result["buy_pe_strike"] == 23900


def test_find_iron_fly_missing_strike_returns_partial():
    chain = [
        _make_chain_row(24000, "CE24000", 120.0, 15.0, "PE24000", 115.0, 15.0),
    ]
    result = find_iron_fly_instruments(chain, atm_strike=24000, step=50, wing_steps=2)
    assert result.get("sell_ce_key") == "CE24000"
    assert result.get("buy_ce_key") is None


def test_get_atm_strike():
    assert get_atm_strike(24023.5, 50) == 24000
    assert get_atm_strike(24076.0, 50) == 24100
    assert get_atm_strike(48350.0, 100) == 48400
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_core.py::test_find_iron_fly_instruments_nifty -v
```

Expected: FAIL — `find_iron_fly_instruments` not importable yet.

- [ ] **Step 3: Add `find_iron_fly_instruments` to `data_fetcher.py`**

Add this function after `find_strangle_instruments`:

```python
def find_iron_fly_instruments(chain: list, atm_strike: int, step: int, wing_steps: int = 2) -> dict:
    """
    Find all 4 legs of an Iron Fly:
      Sell ATM CE + Sell ATM PE
      Buy  OTM CE (atm + wing_steps*step) + Buy OTM PE (atm - wing_steps*step)
    Returns dict with sell_ce_*, sell_pe_*, buy_ce_*, buy_pe_* keys.
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_core.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add data_fetcher.py tests/test_core.py
git commit -m "feat: add find_iron_fly_instruments to data_fetcher"
```

---

## Task 4: Rewrite `order_executor.py`

**Files:**
- Modify: `order_executor.py`
- Modify: `tests/test_core.py`

- [ ] **Step 1: Add tests for `calculate_pnl` and `enter_iron_fly`**

Append to `tests/test_core.py`:

```python
import os
os.environ.setdefault("PAPER_TRADE", "true")
os.environ.setdefault("NIFTY_LOT_SIZE", "75")
os.environ.setdefault("BANKNIFTY_LOT_SIZE", "35")
os.environ.setdefault("PRODUCT_TYPE", "NRML")

from order_executor import calculate_pnl, enter_iron_fly, exit_iron_fly


def _make_position():
    return {
        "index": "NIFTY",
        "strategy": "IRON_FLY",
        "lots": 1,
        "lot_size": 75,
        "qty": 75,
        "sell_ce_key": "CE24000", "sell_ce_strike": 24000, "sell_ce_entry": 120.0,
        "sell_pe_key": "PE24000", "sell_pe_strike": 24000, "sell_pe_entry": 115.0,
        "buy_ce_key":  "CE24100", "buy_ce_strike": 24100,  "buy_ce_entry": 45.0,
        "buy_pe_key":  "PE23900", "buy_pe_strike": 23900,  "buy_pe_entry": 30.0,
        "net_credit": 160.0,
        "max_profit_inr": 12000.0,
        "entry_date": "2026-05-26",
    }


def test_calculate_pnl_profit():
    pos = _make_position()
    # premium decayed: sell legs cheaper, buy legs also cheaper
    ltps = {"CE24000": 80.0, "PE24000": 70.0, "CE24100": 25.0, "PE23900": 15.0}
    # current_net = (80+70)-(25+15) = 110. pnl = (160-110)*75 = 3750
    pnl = calculate_pnl(pos, ltps)
    assert pnl == 3750.0


def test_calculate_pnl_loss():
    pos = _make_position()
    # big move up: sell CE exploded
    ltps = {"CE24000": 250.0, "PE24000": 20.0, "CE24100": 150.0, "PE23900": 5.0}
    # current_net = (250+20)-(150+5) = 115. pnl = (160-115)*75 = 3375 ... wait
    # actually net went UP from 160 to... hmm let me recalc
    # entry net_credit = (120+115)-(45+30) = 160
    # current_net = (250+20)-(150+5) = 115
    # pnl = (160-115)*75 = 3375 -- this is profit because sell legs still net positive
    # Let me make a real loss scenario:
    ltps = {"CE24000": 300.0, "PE24000": 10.0, "CE24100": 180.0, "PE23900": 3.0}
    # current_net = (300+10)-(180+3) = 127
    # pnl = (160-127)*75 = 2475 -- still profit because hedge limits it
    # Real loss: when net_credit < current_net... net_credit=160, need current_net > 160
    ltps = {"CE24000": 350.0, "PE24000": 5.0, "CE24100": 195.0, "PE23900": 2.0}
    # current_net = (350+5)-(195+2) = 158 ... still below 160
    # To get a loss, the move must exceed the wing width:
    ltps = {"CE24000": 400.0, "PE24000": 2.0, "CE24100": 200.0, "PE23900": 1.0}
    # current_net = (400+2)-(200+1) = 201. pnl = (160-201)*75 = -3075
    pnl = calculate_pnl(pos, ltps)
    assert pnl == -3075.0


def test_enter_iron_fly_paper_trade():
    instruments = {
        "sell_ce_key": "CE24000", "sell_ce_strike": 24000, "sell_ce_ltp": 120.0,
        "sell_pe_key": "PE24000", "sell_pe_strike": 24000, "sell_pe_ltp": 115.0,
        "buy_ce_key":  "CE24100", "buy_ce_strike": 24100,  "buy_ce_ltp": 45.0,
        "buy_pe_key":  "PE23900", "buy_pe_strike": 23900,  "buy_pe_ltp": 30.0,
    }
    state = {"position": None, "daily_pnl": 0.0, "total_pnl": 0.0,
             "claude_spend_usd": 0.0, "last_trade_date": None}
    new_state = enter_iron_fly("NIFTY", instruments, 1, state)
    pos = new_state["position"]
    assert pos is not None
    assert pos["strategy"] == "IRON_FLY"
    assert pos["net_credit"] == 160.0
    assert pos["sell_ce_strike"] == 24000
    assert pos["buy_ce_strike"] == 24100


def test_exit_iron_fly_paper_trade():
    instruments = {
        "sell_ce_key": "CE24000", "sell_ce_strike": 24000, "sell_ce_ltp": 120.0,
        "sell_pe_key": "PE24000", "sell_pe_strike": 24000, "sell_pe_ltp": 115.0,
        "buy_ce_key":  "CE24100", "buy_ce_strike": 24100,  "buy_ce_ltp": 45.0,
        "buy_pe_key":  "PE23900", "buy_pe_strike": 23900,  "buy_pe_ltp": 30.0,
    }
    state = {"position": None, "daily_pnl": 0.0, "total_pnl": 0.0,
             "claude_spend_usd": 0.0, "last_trade_date": None}
    state = enter_iron_fly("NIFTY", instruments, 1, state)
    ltps = {"CE24000": 80.0, "PE24000": 70.0, "CE24100": 25.0, "PE23900": 15.0}
    pnl, new_state = exit_iron_fly(ltps, state, "test exit")
    assert pnl == 3750.0
    assert new_state["position"] is None
    assert new_state["total_pnl"] == 3750.0
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_core.py::test_calculate_pnl_profit -v
```

Expected: FAIL — `calculate_pnl` not defined yet.

- [ ] **Step 3: Rewrite `order_executor.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_core.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add order_executor.py tests/test_core.py
git commit -m "feat: rewrite order_executor for Iron Fly 4-leg strategy"
```

---

## Task 5: Rewrite `claude_engine.py`

**Files:**
- Modify: `claude_engine.py`

No unit tests — Claude API calls are integration-only. Verified in smoke test at end.

- [ ] **Step 1: Rewrite `claude_engine.py`**

```python
import json
import re

import anthropic
import config

_SYSTEM_PROMPT = """You are an options trading assistant for NSE index options (NIFTY and BANKNIFTY).
You manage an Iron Fly selling strategy — selling ATM options and buying OTM options as a hedge.

IRON FLY SELLING STRATEGY:
- We SELL ATM CE + ATM PE (collect premium = profit if market stays range-bound)
- We BUY OTM CE + OTM PE as protection (limits max loss)
- We PROFIT from time decay (theta) and low volatility
- We LOSE if the market makes a large directional move beyond our wing strikes

ENTRY RULES:
- Only recommend ENTER when IV is elevated: IV > 15% for NIFTY or IV > 18% for BANKNIFTY
- High IV means expensive premiums = more credit collected = better risk/reward
- Skip if IV is low (< 12%) — premiums too thin to justify the risk
- Skip if a major event is happening TODAY (RBI policy, budget, election results) — gap risk too high
- Pick the index with higher IV and better net credit premium
- Entry is only valid between 9:30–10:00 AM IST

EXIT RULES (for monitoring an open position):
- Recommend EXIT if premium remaining < 20% of original credit (profit mostly captured)
- Recommend EXIT if market has broken out strongly in one direction with continuing momentum
- Recommend HOLD if premium > 30% of credit remaining and market is range-bound
- Recommend HOLD if close to weekly expiry (last 2 days) — theta accelerates, let it decay
- After 4+ days held, lean toward EXIT to avoid expiry risk

Respond ONLY with valid JSON:
{"action": "ENTER"|"SKIP"|"EXIT"|"HOLD", "index": "NIFTY"|"BANKNIFTY"|null,
 "confidence": 0.0-1.0, "reasoning": "<one sentence>"}"""


class ClaudeEngine:
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY,
                                           max_retries=3, timeout=30.0)

    def assess_entry(self, nifty_spot: float, banknifty_spot: float,
                     nifty_chain_summary: str, banknifty_chain_summary: str,
                     time_str: str, state: dict) -> dict:
        if state.get("claude_spend_usd", 0) >= config.CLAUDE_API_BUDGET_STOP_USD:
            return {"action": "SKIP", "index": None,
                    "confidence": 0.0, "reasoning": "budget limit reached"}

        user_content = (
            f"Time: {time_str} IST\n"
            f"NIFTY spot: {nifty_spot:.2f}\n{nifty_chain_summary}\n\n"
            f"BANKNIFTY spot: {banknifty_spot:.2f}\n{banknifty_chain_summary}\n\n"
            f"Daily P&L so far: Rs{state.get('daily_pnl', 0):+.0f}\n"
            "Should we sell an Iron Fly today? Which index has better IV conditions?\n\n"
            "Respond with JSON only."
        )
        try:
            msg = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                system=[{"type": "text", "text": _SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_content}],
            )
            raw = msg.content[0].text.strip()
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            parsed = json.loads(m.group()) if m else {}
            cost = (msg.usage.input_tokens * 0.80 + msg.usage.output_tokens * 4.0) / 1_000_000
            state["claude_spend_usd"] = round(state.get("claude_spend_usd", 0) + cost, 6)
            return parsed
        except Exception as e:
            return {"action": "SKIP", "index": None,
                    "confidence": 0.0, "reasoning": f"Claude error: {e}"}

    def assess_exit(self, position: dict, current_ltps: dict, time_str: str,
                    days_held: int, state: dict) -> dict:
        if state.get("claude_spend_usd", 0) >= config.CLAUDE_API_BUDGET_STOP_USD:
            return {"action": "HOLD", "confidence": 0.0, "reasoning": "budget limit"}

        sell_ce = current_ltps.get(position["sell_ce_key"], position["sell_ce_entry"])
        sell_pe = current_ltps.get(position["sell_pe_key"], position["sell_pe_entry"])
        buy_ce  = current_ltps.get(position["buy_ce_key"],  position["buy_ce_entry"])
        buy_pe  = current_ltps.get(position["buy_pe_key"],  position["buy_pe_entry"])
        current_net = (sell_ce + sell_pe) - (buy_ce + buy_pe)
        pct_remaining = (current_net / position["net_credit"] * 100) if position["net_credit"] else 0

        user_content = (
            f"Time: {time_str} IST | Days held: {days_held}\n"
            f"Open Iron Fly: {position['index']}\n"
            f"Sell CE {position['sell_ce_strike']}: entry Rs{position['sell_ce_entry']:.1f} → now Rs{sell_ce:.1f}\n"
            f"Sell PE {position['sell_pe_strike']}: entry Rs{position['sell_pe_entry']:.1f} → now Rs{sell_pe:.1f}\n"
            f"Buy  CE {position['buy_ce_strike']}:  entry Rs{position['buy_ce_entry']:.1f}  → now Rs{buy_ce:.1f}\n"
            f"Buy  PE {position['buy_pe_strike']}:  entry Rs{position['buy_pe_entry']:.1f}  → now Rs{buy_pe:.1f}\n"
            f"Net credit at entry: Rs{position['net_credit']:.1f} | "
            f"Current net: Rs{current_net:.1f} ({pct_remaining:.0f}% remaining)\n"
            "Should we EXIT now or HOLD for more theta decay?\n\nRespond with JSON only."
        )
        try:
            msg = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                system=[{"type": "text", "text": _SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_content}],
            )
            raw = msg.content[0].text.strip()
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            parsed = json.loads(m.group()) if m else {}
            cost = (msg.usage.input_tokens * 0.80 + msg.usage.output_tokens * 4.0) / 1_000_000
            state["claude_spend_usd"] = round(state.get("claude_spend_usd", 0) + cost, 6)
            return parsed
        except Exception as e:
            return {"action": "HOLD", "confidence": 0.0, "reasoning": f"Claude error: {e}"}
```

- [ ] **Step 2: Run all tests to confirm nothing broke**

```
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add claude_engine.py
git commit -m "feat: rewrite claude_engine for Iron Fly selling strategy"
```

---

## Task 6: Rewrite `logger.py`

**Files:**
- Modify: `logger.py`
- Modify: `tests/test_core.py`

- [ ] **Step 1: Add logger test**

Append to `tests/test_core.py`:

```python
import os, tempfile
from logger import log_trade


def test_log_trade_creates_csv():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        tmp = f.name
    import logger as lg
    original = lg._LOG_FILE
    lg._LOG_FILE = tmp
    try:
        log_trade("ENTER", "NIFTY", "IRON_FLY",
                  24000, 24000, 24100, 23900,
                  120.0, 115.0, 45.0, 30.0,
                  0, 0, 0, 0,
                  160.0, 1, 0, "test entry")
        log_trade("EXIT", "NIFTY", "IRON_FLY",
                  24000, 24000, 24100, 23900,
                  120.0, 115.0, 45.0, 30.0,
                  80.0, 70.0, 25.0, 15.0,
                  160.0, 1, 3750.0, "target-profit")
        import csv
        with open(tmp) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert rows[0]["action"] == "ENTER"
        assert rows[1]["action"] == "EXIT"
        assert float(rows[1]["pnl"]) == 3750.0
    finally:
        lg._LOG_FILE = original
        os.unlink(tmp)
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_core.py::test_log_trade_creates_csv -v
```

Expected: FAIL — wrong signature.

- [ ] **Step 3: Rewrite `logger.py`**

```python
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
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add logger.py tests/test_core.py
git commit -m "feat: rewrite logger for 4-leg Iron Fly schema"
```

---

## Task 7: Rewrite `notifier.py`

**Files:**
- Modify: `notifier.py`

No unit test — Telegram calls are side effects. Message format is verified visually in smoke test.

- [ ] **Step 1: Rewrite `notifier.py`**

```python
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
```

- [ ] **Step 2: Run all tests**

```
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add notifier.py
git commit -m "feat: rewrite notifier for Iron Fly entry/exit messages"
```

---

## Task 8: Rewrite `scheduler.py`

**Files:**
- Modify: `scheduler.py`
- Modify: `tests/test_core.py`

- [ ] **Step 1: Add scheduler time-logic tests**

Append to `tests/test_core.py`:

```python
from unittest.mock import patch
from datetime import datetime, timezone, timedelta


_IST = timezone(timedelta(hours=5, minutes=30))


def _mock_ist(hour, minute, weekday=0):
    dt = datetime(2026, 5, 25 + weekday, hour, minute, 0, tzinfo=_IST)
    return dt


import scheduler as sched


def test_is_market_open_weekday():
    with patch("scheduler.ist_now", return_value=_mock_ist(10, 0, weekday=0)):
        assert sched.is_market_open() is True


def test_is_market_open_weekend():
    with patch("scheduler.ist_now", return_value=_mock_ist(10, 0, weekday=5)):
        assert sched.is_market_open() is False


def test_is_entry_time_in_window():
    with patch("scheduler.ist_now", return_value=_mock_ist(9, 45)):
        assert sched.is_entry_time() is True


def test_is_entry_time_outside_window():
    with patch("scheduler.ist_now", return_value=_mock_ist(10, 30)):
        assert sched.is_entry_time() is False


def test_is_expiry_force_exit_nifty_thursday():
    with patch("scheduler.ist_now", return_value=_mock_ist(15, 5, weekday=3)):
        assert sched.is_expiry_force_exit("NIFTY") is True


def test_is_expiry_force_exit_nifty_not_thursday():
    with patch("scheduler.ist_now", return_value=_mock_ist(15, 5, weekday=0)):
        assert sched.is_expiry_force_exit("NIFTY") is False


def test_days_held():
    from scheduler import _days_held
    with patch("scheduler.ist_now", return_value=_mock_ist(10, 0)):
        pos = {"entry_date": "2026-05-25"}
        assert _days_held(pos) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_core.py::test_is_market_open_weekday -v
```

Expected: FAIL — `scheduler` imports may fail due to old function names.

- [ ] **Step 3: Rewrite `scheduler.py`**

```python
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
    """Exit on expiry day at 3 PM: Thursday for NIFTY, Wednesday for BANKNIFTY."""
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
              f"credit=Rs{net_credit:.1f} | max_loss=Rs{max_loss_inr:.0f} | expiry={nifty_expiry if index == 'NIFTY' else bnf_expiry}")

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
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduler.py tests/test_core.py
git commit -m "feat: rewrite scheduler for Iron Fly positional strategy"
```

---

## Task 9: Reset `state.json` and run smoke test

**Files:**
- Modify: `state.json`

- [ ] **Step 1: Reset `state.json` to new schema**

```json
{
  "position": null,
  "daily_pnl": 0.0,
  "total_pnl": 0.0,
  "claude_spend_usd": 0.0,
  "last_trade_date": null
}
```

- [ ] **Step 2: Run the full test suite one final time**

```
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Smoke test — import check**

```
python -c "from scheduler import OptionsScheduler; print('Import OK')"
```

Expected: `Import OK`

- [ ] **Step 4: Commit**

```bash
git add state.json
git commit -m "chore: reset state.json for Iron Fly strategy"
```

- [ ] **Step 5: Push to GitHub**

```bash
git push origin master
```

---

## Task 10: End-to-end paper trade verification

This task has no automated test — it requires market hours (9:30–10:00 AM IST on a weekday).

- [ ] **Step 1: Confirm `PAPER_TRADE=true` in `.env`**

```
python -c "import config; print('PAPER_TRADE:', config.PAPER_TRADE)"
```

Expected: `PAPER_TRADE: True`

- [ ] **Step 2: Start the bot**

```
python scheduler.py
```

Expected output on a market day at 9:30 AM:
```
Options bot started (Iron Fly selling strategy).
[09:30] Claude → ENTER | NIFTY | IV elevated, good credit available
[09:30] ENTER NIFTY IRON_FLY ATM=24000 | credit=Rs148.5 | max_loss=Rs3863 | expiry=2026-05-29
```

- [ ] **Step 3: Verify `state.json` updated**

After entry, `state.json` should contain a `position` object with all 4 keys, strikes, `net_credit`, and `entry_date`.

- [ ] **Step 4: Verify `trades.csv` has an ENTER row**

Check that `trades.csv` was created with the correct columns and one ENTER row.

- [ ] **Step 5: Verify Telegram message received**

Check your Telegram chat for an "IRON FLY ENTRY" message showing all 4 legs, net credit, max profit, and max loss.

- [ ] **Step 6: Monitor for 30 minutes**

After 30 minutes the bot should print a monitoring line:
```
[10:00] NIFTY IRON_FLY day=0 | unrealized=Rs+450 | sell=130.0/120.0
```

- [ ] **Step 7: Final commit if all looks good**

```bash
git add trades.csv
git commit -m "chore: first paper trade run — Iron Fly selling strategy"
```
