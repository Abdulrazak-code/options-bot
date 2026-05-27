"""Lightweight dashboard — run with: python dashboard.py"""
import csv
import json
import os
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

_IST = timezone(timedelta(hours=5, minutes=30))
PORT = 8080


def _load_state():
    if os.path.exists("state.json"):
        with open("state.json") as f:
            return json.load(f)
    return {"position": None, "daily_pnl": 0.0, "total_pnl": 0.0, "claude_spend_usd": 0.0}


def _load_trades():
    if not os.path.exists("trades.csv"):
        return []
    with open("trades.csv", newline="") as f:
        return list(csv.DictReader(f))


def _pnl_color(val):
    try:
        return "#2ecc71" if float(val) >= 0 else "#e74c3c"
    except (ValueError, TypeError):
        return "#888"


def _fmt_inr(val):
    try:
        v = float(val)
        sign = "+" if v >= 0 else ""
        return f"{sign}Rs {v:,.0f}"
    except (ValueError, TypeError):
        return str(val)


def _build_html():
    state = _load_state()
    trades = _load_trades()
    pos = state.get("position")
    now = datetime.now(_IST).strftime("%d %b %Y, %I:%M %p IST")

    # ── stats ──────────────────────────────────────────────────────────────
    total_trades = len([t for t in trades if t.get("action") == "EXIT"])
    winning = len([t for t in trades if t.get("action") == "EXIT" and float(t.get("pnl", 0)) > 0])
    win_rate = f"{winning/total_trades*100:.0f}%" if total_trades else "—"
    total_pnl = state.get("total_pnl", 0.0)
    daily_pnl = state.get("daily_pnl", 0.0)
    claude_usd = state.get("claude_spend_usd", 0.0)

    # ── open position card ─────────────────────────────────────────────────
    if pos:
        entry_date = pos.get("entry_date", "—")
        days_held = (datetime.now(_IST).date() -
                     datetime.strptime(entry_date, "%Y-%m-%d").date()).days if entry_date != "—" else 0
        pos_html = f"""
        <div class="card pos-card">
          <div class="card-title">Open Position — {pos.get('index')} Iron Fly</div>
          <div class="legs-grid">
            <div class="leg sell"><span class="badge sell-badge">SELL CE</span> {int(pos.get('sell_ce_strike',0))}
              <br><small>Entry: Rs {float(pos.get('sell_ce_entry',0)):.1f}</small></div>
            <div class="leg sell"><span class="badge sell-badge">SELL PE</span> {int(pos.get('sell_pe_strike',0))}
              <br><small>Entry: Rs {float(pos.get('sell_pe_entry',0)):.1f}</small></div>
            <div class="leg buy"><span class="badge buy-badge">BUY CE</span> {int(pos.get('buy_ce_strike',0))}
              <br><small>Entry: Rs {float(pos.get('buy_ce_entry',0)):.1f}</small></div>
            <div class="leg buy"><span class="badge buy-badge">BUY PE</span> {int(pos.get('buy_pe_strike',0))}
              <br><small>Entry: Rs {float(pos.get('buy_pe_entry',0)):.1f}</small></div>
          </div>
          <div class="pos-meta">
            <span>Net Credit: <strong>Rs {float(pos.get('net_credit',0)):.1f}</strong></span>
            <span>Max Profit: <strong>Rs {float(pos.get('max_profit_inr',0)):.0f}</strong></span>
            <span>Lots: <strong>{pos.get('lots')}</strong></span>
            <span>Entry: <strong>{entry_date}</strong></span>
            <span>Days Held: <strong>{days_held}</strong></span>
          </div>
        </div>"""
    else:
        pos_html = """
        <div class="card pos-card no-pos">
          <div class="card-title">Open Position</div>
          <div class="no-pos-msg">No open position</div>
        </div>"""

    # ── trade rows ─────────────────────────────────────────────────────────
    exit_trades = [t for t in reversed(trades) if t.get("action") == "EXIT"]
    rows_html = ""
    for t in exit_trades:
        pnl_val = float(t.get("pnl", 0))
        color = _pnl_color(pnl_val)
        rows_html += f"""
        <tr>
          <td>{t.get('timestamp','')}</td>
          <td><span class="idx-badge">{t.get('index','')}</span></td>
          <td>{int(float(t.get('sell_ce_strike',0)))}/{int(float(t.get('sell_pe_strike',0)))}</td>
          <td>{int(float(t.get('buy_ce_strike',0)))}/{int(float(t.get('buy_pe_strike',0)))}</td>
          <td>Rs {float(t.get('net_credit',0)):.1f}</td>
          <td style="color:{color};font-weight:600">{_fmt_inr(pnl_val)}</td>
          <td><span class="reason">{t.get('reason','')}</span></td>
        </tr>"""

    if not rows_html:
        rows_html = '<tr><td colspan="7" style="text-align:center;color:#888;padding:32px">No completed trades yet</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="30">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Options Bot Dashboard</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e0e0e0;min-height:100vh}}
  .topbar{{background:#1a1d27;border-bottom:1px solid #2a2d3a;padding:16px 28px;display:flex;justify-content:space-between;align-items:center}}
  .topbar h1{{font-size:18px;font-weight:600;color:#fff;letter-spacing:.5px}}
  .topbar .ts{{font-size:12px;color:#888}}
  .mode-badge{{background:#f39c12;color:#000;font-size:11px;font-weight:700;padding:3px 8px;border-radius:4px;margin-left:10px}}
  .content{{padding:24px 28px;max-width:1100px;margin:0 auto}}

  /* stat cards */
  .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px}}
  .stat{{background:#1a1d27;border:1px solid #2a2d3a;border-radius:10px;padding:18px 20px}}
  .stat .label{{font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px}}
  .stat .value{{font-size:26px;font-weight:700}}

  /* position card */
  .card{{background:#1a1d27;border:1px solid #2a2d3a;border-radius:10px;padding:20px;margin-bottom:24px}}
  .card-title{{font-size:13px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.8px;margin-bottom:16px}}
  .legs-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}}
  .leg{{background:#12151f;border-radius:8px;padding:12px;text-align:center;font-size:15px;font-weight:600}}
  .badge{{display:block;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;margin-bottom:6px;width:fit-content;margin:0 auto 6px}}
  .sell-badge{{background:#e74c3c22;color:#e74c3c;border:1px solid #e74c3c44}}
  .buy-badge{{background:#2ecc7122;color:#2ecc71;border:1px solid #2ecc7144}}
  .pos-meta{{display:flex;flex-wrap:wrap;gap:20px;font-size:13px;color:#aaa;border-top:1px solid #2a2d3a;padding-top:14px}}
  .pos-meta strong{{color:#e0e0e0}}
  .no-pos{{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:80px}}
  .no-pos-msg{{color:#555;font-size:15px}}

  /* table */
  .table-wrap{{background:#1a1d27;border:1px solid #2a2d3a;border-radius:10px;overflow:hidden}}
  .table-header{{padding:14px 20px;font-size:13px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:.8px;border-bottom:1px solid #2a2d3a}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{background:#12151f;color:#888;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.6px;padding:10px 16px;text-align:left}}
  td{{padding:11px 16px;border-bottom:1px solid #1e2130;vertical-align:middle}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#1e2130}}
  .idx-badge{{background:#3498db22;color:#3498db;border:1px solid #3498db44;padding:2px 7px;border-radius:4px;font-size:11px;font-weight:700}}
  .reason{{background:#ffffff0a;padding:2px 8px;border-radius:4px;font-size:11px;color:#aaa}}

  @media(max-width:700px){{
    .stats{{grid-template-columns:repeat(2,1fr)}}
    .legs-grid{{grid-template-columns:repeat(2,1fr)}}
  }}
</style>
</head>
<body>
<div class="topbar">
  <h1>Options Bot <span class="mode-badge">PAPER</span></h1>
  <span class="ts">Auto-refreshes every 30s &nbsp;·&nbsp; {now}</span>
</div>
<div class="content">

  <div class="stats">
    <div class="stat">
      <div class="label">Total P&amp;L</div>
      <div class="value" style="color:{_pnl_color(total_pnl)}">{_fmt_inr(total_pnl)}</div>
    </div>
    <div class="stat">
      <div class="label">Today's P&amp;L</div>
      <div class="value" style="color:{_pnl_color(daily_pnl)}">{_fmt_inr(daily_pnl)}</div>
    </div>
    <div class="stat">
      <div class="label">Trades / Win Rate</div>
      <div class="value">{total_trades} <span style="font-size:16px;color:#888">/ {win_rate}</span></div>
    </div>
    <div class="stat">
      <div class="label">Claude Spend</div>
      <div class="value" style="font-size:20px">${claude_usd:.4f}</div>
    </div>
  </div>

  {pos_html}

  <div class="table-wrap">
    <div class="table-header">Trade History</div>
    <table>
      <thead>
        <tr>
          <th>Time</th><th>Index</th><th>Sell CE/PE</th><th>Buy CE/PE</th>
          <th>Net Credit</th><th>P&amp;L</th><th>Exit Reason</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>

</div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_response(404)
            self.end_headers()
            return
        html = _build_html().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, fmt, *args):
        pass  # silence request logs


if __name__ == "__main__":
    server = HTTPServer(("", PORT), Handler)
    print(f"Dashboard running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()
