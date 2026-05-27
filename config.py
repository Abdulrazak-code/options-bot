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
