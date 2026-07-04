# -*- coding: utf-8 -*-
"""
premarket_briefing.py
Runs at 6:25 AM PT every trading day.
Sends a Windows notification + saves briefing to signals.json.
Schedule via Windows Task Scheduler or add to launch_spy_trader.bat.
"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BOT_DIR)

from market_context import get_full_context, get_upcoming_events
from datetime import datetime
import pytz

pacific = pytz.timezone("US/Pacific")
BRIEFING_FILE = os.path.join(BOT_DIR, "premarket_briefing.json")

def send_notification(title, message):
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="SPY Trader", timeout=20)
    except Exception:
        try:
            import subprocess
            ps = (f'Add-Type -AssemblyName System.Windows.Forms;'
                  f'$n=New-Object System.Windows.Forms.NotifyIcon;'
                  f'$n.Icon=[System.Drawing.SystemIcons]::Information;'
                  f'$n.Visible=$true;'
                  f'$n.ShowBalloonTip(18000,"{title}","{message}",[System.Windows.Forms.ToolTipIcon]::Info);'
                  f'Start-Sleep -s 19;$n.Dispose()')
            subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", ps])
        except Exception as e:
            print(f"Notification failed: {e}")

def run_briefing():
    now = datetime.now(pacific)
    print(f"\n=== PRE-MARKET BRIEFING {now.strftime('%A %b %d, %Y — %I:%M %p PT')} ===\n")

    ctx = get_full_context()

    # VIX
    vix_line = f"VIX: {ctx['vix']} ({ctx['vix_regime']})" if ctx['vix'] else "VIX: unavailable"

    # Gap
    gap = ctx.get('gap')
    if gap:
        arrow = "UP" if gap['direction'] == "UP" else "DOWN" if gap['direction'] == "DOWN" else "FLAT"
        gap_line = f"Gap: {arrow} {gap['gap_pct']:+.2f}% (prev close ${gap['prev_close']} -> open ${gap['today_open']})"
        gap_rule = {
            "UP":   "BIAS: BUY signals only today (gap up)",
            "DOWN": "BIAS: SELL signals only today (gap down)",
            "FLAT": "BIAS: Both directions OK (flat gap)",
        }.get(arrow, "")
    else:
        gap_line = "Gap: unavailable"
        gap_rule = ""

    # Events today
    events, is_blocked, block_reason = get_upcoming_events(block_minutes_before=9999)
    if events:
        ev_lines = [f"  {e['time_et']} ET — {e['name']} [{e['impact']}]" for e in events]
        events_str = "Today's events:\n" + "\n".join(ev_lines)
        ev_warn = f"  PAUSE trading 30 min before + 15 min after HIGH events"
    else:
        events_str = "No high-impact events today"
        ev_warn = ""

    # VIX rules
    warn = ctx['vix_adj'].get('warn', '')

    # Load yesterday's paper stats
    try:
        with open(os.path.join(BOT_DIR, 'signals.json')) as f:
            d = json.load(f)
        ps = d.get('paper_stats', {})
        paper_line = f"Paper trades: {ps.get('total',0)} total, {ps.get('win_rate',0)}% WR, PnL {ps.get('total_pnl',0):+.3f} pts"
    except:
        paper_line = "Paper trades: no data yet"

    # Build summary
    lines = [
        f"SPY Trader — Pre-Market Briefing",
        f"{now.strftime('%A %b %d %Y')} | Trading: 6:30-8:15 AM PT",
        "",
        vix_line,
        gap_line,
        gap_rule,
        "",
        events_str,
        ev_warn,
        "",
        warn if warn else "Market conditions: normal",
        paper_line,
    ]
    summary = "\n".join(l for l in lines if l is not None)
    print(summary)

    # Notification (short version)
    notif_lines = [
        vix_line,
        gap_line,
        f"{len(events)} event(s) today" if events else "No major events",
        warn or "Normal conditions",
    ]
    notif_msg = " | ".join(l for l in notif_lines if l)

    send_notification("SPY Trader Pre-Market Briefing", notif_msg)

    # Save briefing
    briefing = {
        "date":       now.strftime("%Y-%m-%d"),
        "time":       now.strftime("%H:%M PT"),
        "vix":        ctx['vix'],
        "vix_regime": ctx['vix_regime'],
        "vix_warn":   warn,
        "gap":        gap,
        "gap_rule":   gap_rule,
        "events":     events,
        "summary":    summary,
    }
    with open(BRIEFING_FILE, "w") as f:
        json.dump(briefing, f, indent=2, default=str)
    print(f"\nBriefing saved to premarket_briefing.json")
    return briefing

if __name__ == "__main__":
    run_briefing()
