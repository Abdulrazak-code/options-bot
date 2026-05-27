# Every Morning Checklist — Options Bot

## Before 9:25 AM IST (do this every trading day)

**Step 1 — Refresh Upstox token** (expires daily at 3:30 AM)
```
python auth.py
```
→ Browser opens → Log in to Upstox → Paste the redirect URL back → Token saved automatically

**Step 2 — Validate token**
```
python -c "from auth import validate_token; import config; print('Token valid:', validate_token(config.UPSTOX_ACCESS_TOKEN))"
```
Expected: `Token valid: True`

**Step 3 — Start the bot**
```
python scheduler.py
```

---

## What the bot does automatically

| Time | Action |
|------|--------|
| 9:30–10:00 AM | Asks Claude whether to enter Iron Fly (NIFTY or BANKNIFTY) |
| Every 30 min | Monitors open position, checks P&L |
| Anytime | Exits if loss hits Rs 5,000 or profit hits 50% of credit |
| Wednesday 3 PM | Force exits BANKNIFTY position (expiry day) |
| Thursday 3 PM | Force exits NIFTY position (expiry day) |
| Max 5 days | Force exits if position held too long |

---

## Check during the day

- Watch Telegram for IRON FLY ENTRY / EXIT alerts
- Check `trades.csv` for all logged trades
- Check `state.json` for current position and P&L

---

## Mode

Currently: `PAPER_TRADE=true` — no real orders placed.  
To go live: change `PAPER_TRADE=false` in `.env` after paper trading for a few days.
