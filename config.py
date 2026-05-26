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

OPTIONS_CAPITAL_INR   = float(os.getenv("OPTIONS_CAPITAL_INR", "50000"))
NIFTY_LOT_SIZE        = int(os.getenv("NIFTY_LOT_SIZE", "75"))
BANKNIFTY_LOT_SIZE    = int(os.getenv("BANKNIFTY_LOT_SIZE", "35"))

TAKE_PROFIT_PCT       = float(os.getenv("TAKE_PROFIT_PCT", "40.0"))
STOP_LOSS_PCT         = float(os.getenv("STOP_LOSS_PCT", "30.0"))

FORCE_EXIT_HOUR       = int(os.getenv("FORCE_EXIT_HOUR", "13"))
FORCE_EXIT_MINUTE     = int(os.getenv("FORCE_EXIT_MINUTE", "30"))

ENTRY_START_HOUR      = int(os.getenv("ENTRY_START_HOUR", "9"))
ENTRY_START_MINUTE    = int(os.getenv("ENTRY_START_MINUTE", "20"))
ENTRY_END_HOUR        = int(os.getenv("ENTRY_END_HOUR", "10"))
ENTRY_END_MINUTE      = int(os.getenv("ENTRY_END_MINUTE", "30"))

CLAUDE_API_BUDGET_STOP_USD = float(os.getenv("CLAUDE_API_BUDGET_STOP_USD", "3.00"))
