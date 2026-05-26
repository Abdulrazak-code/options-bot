import json
import re

import anthropic
import config

_SYSTEM_PROMPT = """You are an options trading assistant for NSE index options (NIFTY and BANKNIFTY).
You assess whether market conditions are suitable for entering a straddle or strangle position.

A STRADDLE buys ATM CE + ATM PE at the same strike — profits from a big move in either direction.
A STRANGLE buys OTM CE + OTM PE — cheaper but needs a bigger move.

ENTRY RULES:
- Only recommend ENTER if there is a clear reason for a large move today: high IV, event risk,
  key support/resistance level, or unusual opening range expansion.
- If the market is drifting sideways with low volatility and no catalyst, say SKIP — straddles
  lose money from time decay (theta) in flat markets.
- Prefer STRADDLE when IV is moderate (fair premium). Prefer STRANGLE when IV is high (expensive ATM).
- Never recommend ENTER after 10:30 AM — theta decay makes buying too expensive.
- NIFTY lot = 75 units, BANKNIFTY lot = 35 units.

EXIT RULES (for monitoring an open position):
- Recommend EXIT if combined premium is up >= 35% from entry (take profit early if move is strong).
- Recommend EXIT if you see signs the move is exhausting (price reversing, volume fading).
- Recommend HOLD if combined premium is up but momentum still intact.
- Mandatory exit happens automatically at 1:30 PM regardless.

Respond ONLY with valid JSON:
{"action": "ENTER"|"SKIP"|"EXIT"|"HOLD", "index": "NIFTY"|"BANKNIFTY"|null,
 "strategy": "STRADDLE"|"STRANGLE"|null, "confidence": 0.0-1.0, "reasoning": "<one sentence>"}"""


class ClaudeEngine:
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=3, timeout=30.0)

    def assess_entry(self, nifty_spot: float, banknifty_spot: float,
                     nifty_chain_summary: str, banknifty_chain_summary: str,
                     time_str: str, state: dict) -> dict:
        if state.get("claude_spend_usd", 0) >= config.CLAUDE_API_BUDGET_STOP_USD:
            return {"action": "SKIP", "index": None, "strategy": None,
                    "confidence": 0.0, "reasoning": "budget limit reached"}

        user_content = (
            f"Time: {time_str} IST\n"
            f"NIFTY spot: {nifty_spot:.2f}\n{nifty_chain_summary}\n\n"
            f"BANKNIFTY spot: {banknifty_spot:.2f}\n{banknifty_chain_summary}\n\n"
            f"Daily P&L so far: Rs{state.get('daily_pnl', 0):+.0f}\n"
            "Should we enter a straddle/strangle today? Which index and which strategy?"
        )
        try:
            msg = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_content +
                           "\n\nRespond with JSON only."}],
            )
            raw = msg.content[0].text.strip()
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            parsed = json.loads(m.group()) if m else {}
            cost = (msg.usage.input_tokens * 0.80 + msg.usage.output_tokens * 4.0) / 1_000_000
            state["claude_spend_usd"] = round(state.get("claude_spend_usd", 0) + cost, 6)
            return parsed
        except Exception as e:
            return {"action": "SKIP", "index": None, "strategy": None,
                    "confidence": 0.0, "reasoning": f"Claude error: {e}"}

    def assess_exit(self, position: dict, ce_ltp: float, pe_ltp: float,
                    time_str: str, state: dict) -> dict:
        if state.get("claude_spend_usd", 0) >= config.CLAUDE_API_BUDGET_STOP_USD:
            return {"action": "HOLD", "confidence": 0.0, "reasoning": "budget limit"}

        combined_entry = position["combined_entry"]
        combined_now = ce_ltp + pe_ltp
        pct_change = (combined_now - combined_entry) / combined_entry * 100 if combined_entry else 0

        user_content = (
            f"Time: {time_str} IST\n"
            f"Open position: {position['index']} {position['strategy']}\n"
            f"CE entry: Rs{position['ce_entry']:.1f} | now: Rs{ce_ltp:.1f}\n"
            f"PE entry: Rs{position['pe_entry']:.1f} | now: Rs{pe_ltp:.1f}\n"
            f"Combined: Rs{combined_entry:.1f} → Rs{combined_now:.1f} ({pct_change:+.1f}%)\n"
            "Should we EXIT now or HOLD for more?"
        )
        try:
            msg = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_content + "\n\nRespond with JSON only."}],
            )
            raw = msg.content[0].text.strip()
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            parsed = json.loads(m.group()) if m else {}
            cost = (msg.usage.input_tokens * 0.80 + msg.usage.output_tokens * 4.0) / 1_000_000
            state["claude_spend_usd"] = round(state.get("claude_spend_usd", 0) + cost, 6)
            return parsed
        except Exception as e:
            return {"action": "HOLD", "confidence": 0.0, "reasoning": f"Claude error: {e}"}
