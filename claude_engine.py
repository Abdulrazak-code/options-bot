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
