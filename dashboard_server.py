"""
SPY Trader Dashboard Server
Run: python dashboard_server.py
Open: http://localhost:5000
"""
from flask import Flask, jsonify, send_from_directory, request
import json, os, subprocess, signal, sys, time, math
import psutil
from datetime import datetime, timedelta
import pytz
import pandas as pd
import yfinance as yf
import tos_parser

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except:
    pass

# Database support (with JSON fallback for local dev)
try:
    from database import db
    DB_AVAILABLE = db.connect()
except:
    DB_AVAILABLE = False
    print("⚠️  Database not available, using JSON fallback")

def sanitize(obj):
    """Recursively replace NaN/Infinity with None so JSON serialization is valid."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj

app = Flask(__name__)

@app.after_request
def disable_csp(response):
    response.headers.pop('Content-Security-Policy', None)
    return response

BASE    = os.path.dirname(os.path.abspath(__file__))
SIGNALS = os.path.join(BASE, "signals.json")
PAPER   = os.path.join(BASE, "paper_trades.json")
LOG     = os.path.join(BASE, "spy_trader.log")
DB_LOG  = os.path.join(BASE, "database_log.txt")
BAT     = os.path.join(BASE, "launch_spy_trader.bat")
BOT_PY  = os.path.join(BASE, "spy_trader_bot.py")
BRIEFING= os.path.join(BASE, "premarket_briefing.py")
TARGET_APP_FILE = os.path.join(BASE, "target_app.txt")
UPDATE_INTERVAL_FILE = os.path.join(BASE, "update_interval.txt")
MANUAL_TRADES = os.path.join(BASE, "manual_trades.json")
TRENDLINE_BREAKS = os.path.join(BASE, "trendline_breaks.json")
TRADE_JOURNAL = os.path.join(BASE, "trade_journal.json")
TOS_DIR = os.path.join(BASE, "TOS")

if not os.path.exists(TOS_DIR):
    os.makedirs(TOS_DIR)

def load_trendline_breaks():
    try:
        with open(TRENDLINE_BREAKS) as f:
            return json.load(f)
    except:
        return {"breaks": []}

def save_trendline_breaks(data):
    with open(TRENDLINE_BREAKS, "w") as f:
        json.dump(data, f, indent=2)

def load_journal():
    try:
        with open(TRADE_JOURNAL) as f:
            return json.load(f)
    except:
        return []

def save_journal(entries):
    with open(TRADE_JOURNAL, "w") as f:
        json.dump(entries, f, indent=2)

def get_today_journal_entry():
    today = datetime.now().strftime("%Y-%m-%d")
    entries = load_journal()
    return next((e for e in entries if e.get("date") == today), None)

def record_trendline_break(symbol, direction, price, time_str):
    """Record a trendline break event"""
    data = load_trendline_breaks()
    data["breaks"].append({
        "date": time.strftime("%Y-%m-%d"),
        "time": time_str,
        "symbol": symbol,
        "direction": direction,
        "price": price
    })
    save_trendline_breaks(data)

def load_manual_trades():
    try:
        with open(MANUAL_TRADES) as f:
            return json.load(f)
    except:
        return []

def save_manual_trades(trades):
    with open(MANUAL_TRADES, "w") as f:
        json.dump(trades, f, indent=2)

def manual_trade_stats(trades):
    closed = [t for t in trades if t.get("closed") and t.get("pnl") is not None]
    if not closed:
        return {"total": 0, "wins": 0, "win_rate": 0, "total_pnl": 0,
                "avg_win": 0, "avg_loss": 0, "calls": 0, "puts": 0}
    wins   = [t for t in closed if t.get("win")]
    losses = [t for t in closed if not t.get("win")]
    return {
        "total":     len(closed),
        "wins":      len(wins),
        "win_rate":  round(len(wins) / len(closed) * 100, 1),
        "total_pnl": round(sum(t["pnl"] for t in closed), 3),
        "avg_win":   round(sum(t["pnl"] for t in wins)   / len(wins),   3) if wins   else 0,
        "avg_loss":  round(sum(t["pnl"] for t in losses) / len(losses), 3) if losses else 0,
        "calls":     len([t for t in closed if t["direction"] == "CALL"]),
        "puts":      len([t for t in closed if t["direction"] == "PUT"]),
    }

def get_target_app():
    if os.path.exists(TARGET_APP_FILE):
        try:
            with open(TARGET_APP_FILE, "r") as f:
                val = f.read().strip()
                if val in ("Chrome", "TradingView"):
                    return val
        except:
            pass
    return "Chrome"

def get_update_interval():
    if os.path.exists(UPDATE_INTERVAL_FILE):
        try:
            with open(UPDATE_INTERVAL_FILE, "r") as f:
                val = int(f.read().strip())
                if val in (15, 30, 45, 60):
                    return val
        except:
            pass
    return 60

# ── Data endpoints ─────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(BASE, "dashboard.html")

@app.route("/lightweight-charts.js")
def serve_lightweight_charts():
    return send_from_directory(BASE, "lightweight-charts.js")

@app.route("/data")
def data():
    d = {}

    # Get signal data from database or JSON
    if DB_AVAILABLE:
        try:
            latest_signal = db.get_latest_signal()
            if latest_signal:
                d = {
                    "signal": latest_signal.get("signal", "WAITING"),
                    "signal_type": latest_signal.get("signal_type"),
                    "details": json.loads(latest_signal.get("raw_data", "{}")),
                    "last_update": latest_signal.get("timestamp").isoformat() if latest_signal.get("timestamp") else None,
                    "history": [dict(h) for h in db.get_signal_history(60)]
                }
            else:
                d = {"signal":"WAITING","details":{},"history":[],"last_update":None}
        except Exception as e:
            print(f"Database error in /data: {e}")
            d = {"signal":"WAITING","details":{},"history":[],"last_update":None}
    else:
        # Fallback to JSON
        try:
            with open(SIGNALS) as f:
                d = json.load(f)
        except FileNotFoundError:
            d = {"signal":"WAITING","details":{},"history":[],"last_update":None}
        except Exception as e:
            return jsonify({"error":str(e)}), 500

    chrome_pid, tv_pid = find_cdp_status()
    d["chrome_running"] = chrome_pid is not None
    d["tv_running"] = tv_pid is not None
    d["target_app"] = get_target_app()
    d["update_interval"] = get_update_interval()

    # Paper trades from database
    if DB_AVAILABLE:
        try:
            d["paper_trades"] = [dict(t) for t in db.get_paper_trades(100)]
            d["paper_stats"] = dict(db.get_paper_stats())
        except Exception as e:
            print(f"Error fetching paper trades: {e}")
            d["paper_trades"] = []
            d["paper_stats"] = {}
    else:
        d["paper_trades"] = []
        d["paper_stats"] = {}

    # Manual trades from database
    if DB_AVAILABLE:
        try:
            manual = [dict(t) for t in db.get_manual_trades(100)]
            open_manual = next((t for t in reversed(manual) if not t.get("closed")), None)
            d["manual_trades"] = [t for t in manual if t.get("closed")]
            d["open_manual_trade"] = open_manual
            d["manual_stats"] = manual_trade_stats(manual)
        except Exception as e:
            print(f"Error fetching manual trades: {e}")
            d["manual_trades"] = []
            d["open_manual_trade"] = None
            d["manual_stats"] = {}
    else:
        # Fallback to JSON
        manual = load_manual_trades()
        open_manual = next((t for t in reversed(manual) if not t.get("closed")), None)
        d["manual_trades"]    = [t for t in manual if t.get("closed")]
        d["open_manual_trade"] = open_manual
        d["manual_stats"]     = manual_trade_stats(manual)

    # Trendline breaks from database
    if DB_AVAILABLE:
        try:
            d["trendline_breaks"] = [dict(t) for t in db.get_trendline_breaks(1)]
        except Exception as e:
            print(f"Error fetching trendline breaks: {e}")
            d["trendline_breaks"] = []
    else:
        # Fallback to JSON
        tl_data = load_trendline_breaks()
        d["trendline_breaks"] = tl_data.get("breaks", [])

    return jsonify(sanitize(d))

@app.route("/control/log")
def log():
    try:
        lines = int(request.args.get("lines", 50))
        with open(LOG, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return jsonify({"lines": all_lines[-lines:]})
    except Exception as e:
        return jsonify({"lines":[], "error":str(e)})

@app.route("/control/db-log")
def db_log():
    """Get database operation logs"""
    try:
        lines = int(request.args.get("lines", 50))
        if os.path.exists(DB_LOG):
            with open(DB_LOG, encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            return jsonify({"lines": all_lines[-lines:], "status": "ok"})
        else:
            return jsonify({"lines": ["[INFO] Database logging started...\n"], "status": "no_logs_yet"})
    except Exception as e:
        return jsonify({"lines": [], "error": str(e)})

@app.route("/control/db-status")
def db_status():
    """Check database connection status"""
    status = {
        "db_connected": DB_AVAILABLE,
        "db_module": "database.py" if DB_AVAILABLE else "Not loaded",
        "status": "✓ Connected" if DB_AVAILABLE else "✗ Using JSON fallback"
    }
    return jsonify(status)

@app.route("/trendline-breaks")
def trendline_breaks_endpoint():
    """Get daily trendline break history"""
    try:
        if DB_AVAILABLE:
            breaks = [dict(b) for b in db.get_trendline_breaks(30)]  # Last 30 days
        else:
            data = load_trendline_breaks()
            breaks = data.get("breaks", [])

        # Group by date
        by_date = {}
        for br in breaks:
            date = br.get("date", "unknown")
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(br)

        return jsonify({"breaks": breaks, "by_date": by_date})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/webhook/trendline", methods=["POST"])
def webhook_trendline():
    """Receive trendline break alerts from TradingView via webhook"""
    try:
        data = request.get_json() or request.form.to_dict()

        # Extract from TradingView alert message
        # Format: "SPY B↑ 425.50" or "SPY B↓ 424.80" or custom format
        message = data.get("message", "") or data.get("text", "")

        # Parse direction from message
        direction = None
        if "B↑" in message or "UP" in message.upper() or "BREAKOUT" in message.upper():
            direction = "UP"
        elif "B↓" in message or "DN" in message.upper() or "BREAKDOWN" in message.upper():
            direction = "DN"

        if not direction:
            return jsonify({"error": "Could not parse direction from message"}), 400

        # Extract price if provided
        price = data.get("price", "?")

        # Record to JSON
        try:
            if os.path.exists(TRENDLINE_BREAKS):
                with open(TRENDLINE_BREAKS, "r") as f:
                    tl_data = json.load(f)
            else:
                tl_data = {"breaks": []}

            from datetime import datetime
            now = datetime.now()

            tl_data["breaks"].append({
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "symbol": "SPY",
                "direction": direction,
                "price": str(price),
                "source": "webhook"
            })

            with open(TRENDLINE_BREAKS, "w") as f:
                json.dump(tl_data, f, indent=2)

            print(f"[WEBHOOK] Recorded: SPY {direction} @ {price}")
            return jsonify({"ok": True, "message": f"Recorded SPY {direction}"})
        except Exception as e:
            print(f"[WEBHOOK] Error recording: {e}")
            return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/trendline-breaks/record", methods=["POST"])
def record_trendline_break_manual():
    """Manually record a trendline break (for when auto-detection fails)"""
    try:
        req_data = request.get_json()
        direction = req_data.get("direction", "").upper()
        price = req_data.get("price", "?")
        time_str = req_data.get("time", time.strftime("%H:%M:%S"))

        if direction not in ("UP", "DN"):
            return jsonify({"error": "Direction must be UP or DN"}), 400

        date_str = datetime.now().strftime("%Y-%m-%d")

        # Record to database
        if DB_AVAILABLE:
            db.save_trendline_break({
                "date": date_str,
                "time": time_str,
                "symbol": "SPY",
                "direction": direction,
                "price": str(price),
                "is_manual": True
            })
        else:
            # Fallback to JSON
            data = load_trendline_breaks()
            data["breaks"].append({
                "date": date_str,
                "time": time_str,
                "symbol": "SPY",
                "direction": direction,
                "price": str(price),
                "manual": True
            })
            save_trendline_breaks(data)

        return jsonify({"ok": True, "message": f"Recorded SPY {direction} @ {price}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Control endpoints ──────────────────────────────────────────
def find_bot_pids():
    """Find all PIDs running spy_trader_bot.py"""
    pids = []
    for proc in psutil.process_iter(['pid','name','cmdline']):
        try:
            cmd = " ".join(proc.info['cmdline'] or [])
            if "spy_trader_bot" in cmd and "python" in cmd.lower():
                pids.append(proc.info['pid'])
        except:
            pass
    return pids

def find_cdp_status():
    """Find what process is running on port 9222 (Chrome or TradingView)"""
    chrome_pid = None
    tv_pid = None
    for proc in psutil.process_iter(['pid','name','cmdline']):
        try:
            cmd = " ".join(proc.info['cmdline'] or [])
            if "9222" in cmd:
                name_lower = proc.info['name'].lower()
                cmd_lower = cmd.lower()
                if "tradingview" in name_lower or "tradingview" in cmd_lower:
                    tv_pid = proc.info['pid']
                elif "chrome" in name_lower or "chrome" in cmd_lower:
                    chrome_pid = proc.info['pid']
        except:
            pass
    return chrome_pid, tv_pid

@app.route("/control/status")
def status():
    bot_pids  = find_bot_pids()
    chrome_pid, tv_pid = find_cdp_status()
    try:
        with open(SIGNALS) as f:
            d = json.load(f)
        last_update = d.get("last_update","")
        signal_val  = d.get("signal","")
        # Check if stale (>3 min)
        if last_update:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(last_update)
                age_s = (datetime.now() - dt).total_seconds()
                stale = age_s > 180
            except:
                stale = True
        else:
            stale = True
    except:
        last_update = None; signal_val = ""; stale = True

    return jsonify({
        "bot_running":  len(bot_pids) > 0,
        "bot_pids":     bot_pids,
        "chrome_running": chrome_pid is not None,
        "chrome_pid":   chrome_pid,
        "tv_running":   tv_pid is not None,
        "tv_pid":       tv_pid,
        "target_app":   get_target_app(),
        "update_interval": get_update_interval(),
        "last_update":  last_update,
        "signal":       signal_val,
        "stale":        stale,
    })

@app.route("/control/get_target")
def get_target():
    return jsonify({"target_app": get_target_app()})

@app.route("/control/set_target", methods=["POST"])
def set_target():
    try:
        req = request.get_json(force=True)
        val = req.get("target_app", "Chrome")
        if val not in ("Chrome", "TradingView"):
            return jsonify({"ok": False, "error": "Invalid target app"}), 400
        with open(TARGET_APP_FILE, "w") as f:
            f.write(val)
        return jsonify({"ok": True, "target_app": val})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/control/set_interval", methods=["POST"])
def set_interval():
    try:
        req = request.get_json(force=True)
        val = int(req.get("interval", 60))
        if val not in (15, 30, 45, 60):
            return jsonify({"ok": False, "error": "Invalid interval"}), 400
        with open(UPDATE_INTERVAL_FILE, "w") as f:
            f.write(str(val))
        return jsonify({"ok": True, "interval": val})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/control/restart", methods=["POST"])
def restart():
    """Kill current bot + Chrome/TV CDP, then relaunch via bat"""
    msgs = []
    # Kill bot
    for pid in find_bot_pids():
        try: psutil.Process(pid).terminate(); msgs.append(f"Stopped bot PID {pid}")
        except: pass
    # Kill Chrome/TV CDP
    chrome_pid, tv_pid = find_cdp_status()
    if chrome_pid:
        try: psutil.Process(chrome_pid).terminate(); msgs.append(f"Stopped Chrome PID {chrome_pid}")
        except: pass
    if tv_pid:
        try: psutil.Process(tv_pid).terminate(); msgs.append(f"Stopped TradingView PID {tv_pid}")
        except: pass
    time.sleep(1)
    # Relaunch bat
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", BAT],
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform=="win32" else 0,
            cwd=BASE
        )
        msgs.append("launch_spy_trader.bat started")
    except Exception as e:
        msgs.append(f"Launch failed: {e}")
        return jsonify({"ok": False, "messages": msgs}), 500
    return jsonify({"ok": True, "messages": msgs})

@app.route("/control/stop", methods=["POST"])
def stop_bot():
    """Stop just the bot process (keep Chrome open)"""
    pids = find_bot_pids()
    if not pids:
        return jsonify({"ok": True, "messages": ["Bot was not running"]})
    msgs = []
    for pid in pids:
        try: psutil.Process(pid).terminate(); msgs.append(f"Stopped bot PID {pid}")
        except Exception as e: msgs.append(f"Could not stop {pid}: {e}")
    return jsonify({"ok": True, "messages": msgs})

@app.route("/control/start", methods=["POST"])
def start_bot():
    """Start bot only (Chrome already running)"""
    if find_bot_pids():
        return jsonify({"ok": False, "messages": ["Bot is already running"]})
    try:
        subprocess.Popen(
            ["python", BOT_PY],
            cwd=BASE,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform=="win32" else 0
        )
        return jsonify({"ok": True, "messages": ["Bot started"]})
    except Exception as e:
        return jsonify({"ok": False, "messages": [str(e)]}), 500

@app.route("/control/briefing", methods=["POST"])
def run_briefing():
    """Run the pre-market briefing now"""
    try:
        result = subprocess.run(
            ["python", BRIEFING],
            capture_output=True, text=True, timeout=30, cwd=BASE,
            encoding="utf-8", errors="replace"
        )
        output = (result.stdout + result.stderr).strip()
        return jsonify({"ok": True, "output": output})
    except Exception as e:
        return jsonify({"ok": False, "output": str(e)}), 500

@app.route("/control/clear_paper", methods=["POST"])
def clear_paper():
    """Reset all paper trades"""
    try:
        with open(PAPER, "w") as f: json.dump([], f)
        return jsonify({"ok": True, "messages": ["Paper trades cleared"]})
    except Exception as e:
        return jsonify({"ok": False, "messages": [str(e)]}), 500

@app.route("/manual_trade/open", methods=["POST"])
def manual_trade_open():
    """Open a manual paper trade (CALL or PUT) with current indicator snapshot"""
    req = request.get_json(force=True)
    direction = req.get("direction", "CALL")
    if direction not in ("CALL", "PUT"):
        return jsonify({"ok": False, "error": "direction must be CALL or PUT"}), 400

    # Snapshot current signal data
    sig = {}
    det = {}
    spy_price = None

    if DB_AVAILABLE:
        try:
            latest_signal = db.get_latest_signal()
            if latest_signal:
                sig = json.loads(latest_signal.get("raw_data", "{}"))
                det = sig.get("details", {}) if isinstance(sig, dict) else {}
                spy_price = det.get("spy_price") or latest_signal.get("spy_price")
        except Exception as e:
            print(f"Error getting signal from DB: {e}")

    # Fallback to JSON
    if not spy_price:
        try:
            with open(SIGNALS) as f:
                sig = json.load(f)
            det = sig.get("details", {})
            spy_price = det.get("spy_price")
        except:
            pass

    if not spy_price:
        return jsonify({"ok": False, "error": "No SPY price — is the bot running?"}), 400

    # Check for open trades
    if DB_AVAILABLE:
        open_trades = [t for t in db.get_manual_trades(100) if not t.get("closed")]
        if open_trades:
            return jsonify({"ok": False, "error": "A trade is already open. Close it first."}), 400
    else:
        trades = load_manual_trades()
        if any(not t.get("closed") for t in trades):
            return jsonify({"ok": False, "error": "A trade is already open. Close it first."}), 400

    now = datetime.now()
    trade = {
        "id":          int(now.timestamp() * 1000),
        "direction":   direction,
        "entry_time":  now.strftime("%H:%M:%S"),
        "entry_date":  now.strftime("%Y-%m-%d"),
        "entry_price": spy_price,
        "snapshot": {
            "signal":      sig.get("signal", "--"),
            "signal_type": sig.get("signal_type", "--"),
            "conf_tv":     det.get("conf_tv"),
            "rev_score":   det.get("rev_score"),
            "rev_dir":     det.get("rev_dir"),
            "macd_dir":    det.get("signal_tv"),
            "qqq_price":   det.get("qqq_price"),
            "add":         det.get("add"),
            "vwap_pct":    det.get("vwap_pct"),
            "st_flip":     det.get("st_flip"),
            "div_signal":  det.get("div_signal"),
            "spy1_dir":    det.get("spy1_dir"),
            "spy5_dir":    det.get("spy5_dir"),
        },
        "closed":      False,
        "exit_price":  None,
        "exit_time":   None,
        "pnl":         None,
        "pnl_pct":     None,
        "win":         None,
    }

    # Save to database or JSON
    if DB_AVAILABLE:
        db.save_manual_trade(trade)
    else:
        trades = load_manual_trades()
        trades.append(trade)
        save_manual_trades(trades)

    return jsonify({"ok": True, "trade": trade})


@app.route("/manual_trade/close", methods=["POST"])
def manual_trade_close():
    """Close the open manual paper trade and calculate P&L"""
    # Get current SPY price
    exit_price = None

    if DB_AVAILABLE:
        try:
            latest_signal = db.get_latest_signal()
            if latest_signal:
                exit_price = float(latest_signal.get("spy_price", 0)) if latest_signal.get("spy_price") else None
        except Exception as e:
            print(f"Error getting price from DB: {e}")

    # Fallback to JSON
    if not exit_price:
        try:
            with open(SIGNALS) as f:
                sig = json.load(f)
            exit_price = sig.get("details", {}).get("spy_price")
            if exit_price is not None:
                exit_price = float(exit_price)
        except:
            pass

    if not exit_price:
        return jsonify({"ok": False, "error": "No SPY price — is the bot running?"}), 400

    # Find and close open trade
    if DB_AVAILABLE:
        open_trades = [t for t in db.get_manual_trades(100) if not t.get("closed")]
        if not open_trades:
            return jsonify({"ok": False, "error": "No open trade to close"}), 400

        # Close the first open trade
        trade_id = open_trades[0].get("id")
        db.close_manual_trade(trade_id, exit_price)
        closed_trade = open_trades[0]
        closed_trade["exit_price"] = exit_price

        return jsonify({"ok": True, "trade": closed_trade, "pnl": closed_trade.get("pnl")})
    else:
        trades = load_manual_trades()
        open_list = [t for t in trades if not t.get("closed")]
        if not open_list:
            return jsonify({"ok": False, "error": "No open trade to close"}), 400

        now = datetime.now()
        for trade in trades:
            if not trade.get("closed"):
                entry = float(trade["entry_price"])
                if trade["direction"] == "CALL":
                    pnl = round(exit_price - entry, 3)
                else:
                    pnl = round(entry - exit_price, 3)
                pnl_pct = round(pnl / entry * 100, 3) if entry else 0
                trade["closed"]      = True
                trade["exit_price"]  = exit_price
                trade["exit_time"]   = now.strftime("%H:%M:%S")
                trade["pnl"]         = pnl
                trade["pnl_pct"]     = pnl_pct
                trade["win"]         = pnl > 0
                break

        save_manual_trades(trades)
        closed_trade = next(t for t in reversed(trades) if t.get("closed"))
        return jsonify({"ok": True, "trade": closed_trade, "pnl": closed_trade["pnl"]})


@app.route("/manual_trade/clear", methods=["POST"])
def manual_trade_clear():
    """Clear all manual paper trades"""
    try:
        save_manual_trades([])
        return jsonify({"ok": True, "messages": ["Manual trades cleared"]})
    except Exception as e:
        return jsonify({"ok": False, "messages": [str(e)]}), 500


@app.route("/manual_trade/delete/<int:trade_id>", methods=["POST"])
def manual_trade_delete(trade_id):
    """Delete a single manual paper trade by ID"""
    try:
        trades = load_manual_trades()
        trades = [t for t in trades if t.get("id") != trade_id]
        save_manual_trades(trades)
        return jsonify({"ok": True, "messages": ["Trade deleted"]})
    except Exception as e:
        return jsonify({"ok": False, "messages": [str(e)]}), 500


@app.route("/journal/get", methods=["GET"])
def journal_get():
    """Get all journal entries or today's entry"""
    try:
        today = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
        entries = load_journal()

        if today == "all":
            return jsonify({"ok": True, "entries": entries})

        entry = next((e for e in entries if e.get("date") == today), None)
        if entry:
            return jsonify({"ok": True, "entry": entry})
        return jsonify({"ok": True, "entry": None})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/journal/save", methods=["POST"])
def journal_save():
    """Save or update today's journal entry"""
    try:
        req = request.get_json(force=True)
        content = req.get("content", "")
        pnl = req.get("pnl")
        date = req.get("date", datetime.now().strftime("%Y-%m-%d"))

        entries = load_journal()

        # Find existing entry for this date
        existing_idx = next((i for i, e in enumerate(entries) if e.get("date") == date), None)

        entry = {
            "date": date,
            "content": content,
            "pnl": pnl,
            "created_at": datetime.now().isoformat()
        }

        if existing_idx is not None:
            entries[existing_idx] = entry
        else:
            entries.append(entry)

        save_journal(entries)
        return jsonify({"ok": True, "message": "Journal entry saved"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/journal/delete", methods=["POST"])
def journal_delete():
    """Delete a journal entry by date"""
    try:
        req = request.get_json(force=True)
        date = req.get("date")

        if not date:
            return jsonify({"ok": False, "error": "Date required"}), 400

        entries = load_journal()
        entries = [e for e in entries if e.get("date") != date]
        save_journal(entries)

        return jsonify({"ok": True, "message": "Journal entry deleted"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Trade Analysis Endpoints ────────────────────────────────────
@app.route("/api/analysis/files")
def analysis_files():
    """List all CSV files in the TOS folder"""
    try:
        if not os.path.exists(TOS_DIR):
            os.makedirs(TOS_DIR)
        files = [f for f in os.listdir(TOS_DIR) if f.endswith(".csv")]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(TOS_DIR, x)), reverse=True)
        return jsonify({"ok": True, "files": files})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/analysis/upload", methods=["POST"])
def analysis_upload():
    """Upload a local TOS CSV file to the TOS directory"""
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "No file part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"ok": False, "error": "No selected file"}), 400
        
    if file and file.filename.endswith('.csv'):
        filename = os.path.basename(file.filename)
        filepath = os.path.join(TOS_DIR, filename)
        try:
            file.save(filepath)
            return jsonify({"ok": True, "filename": filename, "message": f"Successfully uploaded {filename}"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    else:
        return jsonify({"ok": False, "error": "Only CSV files are allowed"}), 400


@app.route("/api/analysis/trades")
def analysis_trades():
    """Parse trades from a selected TOS CSV file"""
    filename = request.args.get("filename")
    if not filename:
        return jsonify({"ok": False, "error": "Filename is required"}), 400
    
    filename = os.path.basename(filename)
    filepath = os.path.join(TOS_DIR, filename)
    
    if not os.path.exists(filepath):
        return jsonify({"ok": False, "error": f"File {filename} not found"}), 404
        
    try:
        trades = tos_parser.load_and_parse_trades(filepath)
        
        serialized_trades = []
        for t in trades:
            t_copy = t.copy()
            t_copy["entry_time"] = t["entry_time"].strftime("%Y-%m-%d %H:%M:%S")
            if t.get("exit_time"):
                t_copy["exit_time"] = t["exit_time"].strftime("%Y-%m-%d %H:%M:%S")
            
            t_copy["entries"] = [
                {"time": e["time"].strftime("%Y-%m-%d %H:%M:%S"), "price": e["price"], "qty": e["qty"]}
                for e in t["entries"]
            ]
            t_copy["exits"] = [
                {"time": ex["time"].strftime("%Y-%m-%d %H:%M:%S"), "price": ex["price"], "qty": ex["qty"]}
                for ex in t["exits"]
            ]
            serialized_trades.append(t_copy)
            
        return jsonify({"ok": True, "trades": serialized_trades})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/analysis/chart")
def analysis_chart():
    """Download SPY chart data and run stop loss analysis for a trade"""
    date_str = request.args.get("date")          # format: "YYYY-MM-DD"
    entry_time_str = request.args.get("entry_time")  # format: "YYYY-MM-DD HH:MM:SS"
    exit_time_str = request.args.get("exit_time")    # format: "YYYY-MM-DD HH:MM:SS" (optional)
    direction = request.args.get("direction", "LONG").upper()
    option_type = request.args.get("option_type", "None").upper()
    user_tz_str = request.args.get("timezone", "US/Eastern")
    realized_pnl = request.args.get("pnl")
    
    if not date_str or not entry_time_str:
        return jsonify({"ok": False, "error": "date and entry_time are required"}), 400
        
    try:
        # Determine the predicted direction of the underlying stock SPY
        if option_type == "PUT":
            underlying_dir = "SHORT" if direction == "LONG" else "LONG"
        else:
            underlying_dir = direction

        dt = datetime.strptime(date_str, "%Y-%m-%d")
        next_dt = dt + timedelta(days=1)
        start_date = dt.strftime("%Y-%m-%d")
        end_date = next_dt.strftime("%Y-%m-%d")
        
        df = yf.Ticker("SPY").history(start=start_date, end=end_date, interval="1m", prepost=True)
        
        if df.empty:
            return jsonify({
                "ok": False,
                "error": f"No chart data found for SPY on {date_str}. (Note: Yahoo Finance only stores 1-minute data for the last 30 days)"
            }), 404
            
        tz = pytz.timezone(user_tz_str)
        try:
            df.index = df.index.tz_convert(tz)
        except Exception as e:
            pass
            
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['TP_Vol'] = df['Typical_Price'] * df['Volume']
        df['VWAP'] = df['TP_Vol'].cumsum() / df['Volume'].cumsum()
        df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        
        entry_dt = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
        entry_dt = tz.localize(entry_dt)
        
        exit_dt = None
        if exit_time_str and exit_time_str != "None":
            exit_dt = datetime.strptime(exit_time_str, "%Y-%m-%d %H:%M:%S")
            exit_dt = tz.localize(exit_dt)
            
        entry_idx = int(df.index.get_indexer([entry_dt], method='nearest')[0])
        spy_entry_price = float(df.iloc[entry_idx]['Close'])
        spy_entry_time_unix = int(df.index[entry_idx].timestamp())
        
        if exit_dt:
            exit_idx = int(df.index.get_indexer([exit_dt], method='nearest')[0])
            spy_exit_price = float(df.iloc[exit_idx]['Close'])
            spy_exit_time_unix = int(df.index[exit_idx].timestamp())
        else:
            exit_idx = len(df) - 1
            spy_exit_price = float(df.iloc[exit_idx]['Close'])
            spy_exit_time_unix = int(df.index[exit_idx].timestamp())
            
        start_idx = min(entry_idx, exit_idx)
        end_idx = max(entry_idx, exit_idx)
        
        trade_df = df.iloc[start_idx:end_idx+1]
        
        max_spy_price = float(trade_df['High'].max())
        min_spy_price = float(trade_df['Low'].min())
        
        if underlying_dir == "LONG":
            max_runup = max_spy_price - spy_entry_price
            max_drawdown = spy_entry_price - min_spy_price
        else:
            max_runup = spy_entry_price - min_spy_price
            max_drawdown = max_spy_price - spy_entry_price
            
        post_exit_dt = (exit_dt if exit_dt else entry_dt) + timedelta(minutes=60)
        post_exit_idx = int(df.index.get_indexer([post_exit_dt], method='nearest')[0])
        
        post_df = df.iloc[exit_idx:post_exit_idx+1] if post_exit_idx > exit_idx else pd.DataFrame()
        
        if not post_df.empty:
            max_spy_post = float(post_df['High'].max())
            min_spy_post = float(post_df['Low'].min())
            
            if underlying_dir == "LONG":
                max_post_runup = max_spy_post - spy_entry_price
                max_post_drawdown = spy_entry_price - min_spy_post
                favorable_post_exit_move = max_spy_post - spy_exit_price
            else:
                max_post_runup = spy_entry_price - min_spy_post
                max_post_drawdown = max_spy_post - spy_entry_price
                favorable_post_exit_move = spy_exit_price - min_spy_post
        else:
            max_post_runup = 0.0
            max_post_drawdown = 0.0
            favorable_post_exit_move = 0.0
            
        try:
            pnl_val = float(realized_pnl) if realized_pnl is not None else 0.0
        except:
            pnl_val = 0.0
            
        is_win = pnl_val > 0 or (spy_exit_price > spy_entry_price if underlying_dir == "LONG" else spy_exit_price < spy_entry_price)
        
        MOVE_THRESHOLD = 0.50
        
        verdict = "UNKNOWN"
        verdict_details = ""
        
        if is_win:
            if favorable_post_exit_move >= MOVE_THRESHOLD:
                verdict = "EARLY_EXIT"
                verdict_details = f"You won this trade, but you exited early! SPY ran another ${favorable_post_exit_move:.2f} in your direction within 60 minutes after you exited."
            else:
                verdict = "GREAT_TRADE"
                verdict_details = "Excellent trade execution! You captured the move and exited at the right time."
        else:
            overall_max_runup = max(max_runup, max_post_runup)
            
            if overall_max_runup >= MOVE_THRESHOLD:
                verdict = "STOPPED_OUT_BUT_CORRECT"
                verdict_details = f"Your direction was correct, but you were stopped out! SPY reached a max run-up of ${overall_max_runup:.2f} in your direction, but you were shaken out by a drawdown of ${max_drawdown:.2f} first."
            else:
                verdict = "WRONG_DIRECTION"
                verdict_details = f"Wrong direction setup. SPY immediately went against you (drawdown: ${max_drawdown:.2f}) and never went in your direction (max run-up: ${overall_max_runup:.2f}). Good thing you had a stop loss!"
                
        candles = []
        for idx, row in df.iterrows():
            candles.append({
                "time": int(idx.timestamp()),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": int(row['Volume']),
                "vwap": float(row['VWAP']) if not pd.isna(row['VWAP']) else None,
                "ema9": float(row['EMA9']) if not pd.isna(row['EMA9']) else None,
                "ema21": float(row['EMA21']) if not pd.isna(row['EMA21']) else None
            })
            
        analysis = {
            "spy_entry_price": spy_entry_price,
            "spy_exit_price": spy_exit_price,
            "spy_entry_time_unix": spy_entry_time_unix,
            "spy_exit_time_unix": spy_exit_time_unix,
            "max_runup": round(max_runup, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_post_runup": round(max_post_runup, 2),
            "max_post_drawdown": round(max_post_drawdown, 2),
            "favorable_post_exit_move": round(favorable_post_exit_move, 2),
            "verdict": verdict,
            "verdict_details": verdict_details,
            "spy_during_trade_min": min_spy_price,
            "spy_during_trade_max": max_spy_price
        }
        
        return jsonify(sanitize({
            "ok": True,
            "candles": candles,
            "analysis": analysis
        }))
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


CACHE_FILE = os.path.join(TOS_DIR, "trade_analysis_cache.json")

def load_analysis_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading cache: {e}")
    return {}

def save_analysis_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Error saving cache: {e}")

@app.route("/api/analysis/summary")
def analysis_summary():
    """Generate daily summary and recommendations for a selected TOS CSV file"""
    filename = request.args.get("filename")
    if not filename:
        return jsonify({"ok": False, "error": "Filename is required"}), 400
        
    filename = os.path.basename(filename)
    filepath = os.path.join(TOS_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"ok": False, "error": f"File {filename} not found"}), 404
        
    try:
        cache = load_analysis_cache()
        mtime = os.path.getmtime(filepath)
        if filename in cache and cache[filename].get("mtime") == mtime:
            return jsonify({"ok": True, "summary": cache[filename]["summary"]})

        executions = tos_parser.parse_tos_csv(filepath)
        trades = tos_parser.pair_trades(executions)
        
        spy_trades = [t for t in trades if t.get("underlying") == "SPY" and t.get("closed")]
        if not spy_trades:
            summary = {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "wins_count": 0,
                "losses_count": 0,
                "stopped_out_correct": 0,
                "wrong_direction": 0,
                "early_exits": 0,
                "great_trades": 0,
                "avg_drawdown_stopped": 0.0,
                "right_direction_count": 0,
                "sim_3_total": 0,
                "sim_3_wins": 0,
                "sim_3_losses": 0,
                "sim_3_pnl": 0.0,
                "sim_2l_total": 0,
                "sim_2l_wins": 0,
                "sim_2l_losses": 0,
                "sim_2l_pnl": 0.0,
                "recommendations": ["No closed SPY trades found in this statement."],
                "donts": []
            }
            # Cache empty state
            cache[filename] = {
                "mtime": mtime,
                "summary": summary
            }
            save_analysis_cache(cache)
            return jsonify({"ok": True, "summary": summary})
            
        # Sort chronologically (ascending) for simulation and timezone calculations
        spy_trades.sort(key=lambda x: x["entry_time"])
            
        # Get unique entry dates
        dates = set(t["entry_time"].strftime("%Y-%m-%d") for t in spy_trades)
        spy_data = {}
        for d_str in dates:
            dt = datetime.strptime(d_str, "%Y-%m-%d")
            next_dt = dt + timedelta(days=1)
            ticker = yf.Ticker("SPY")
            df = ticker.history(start=d_str, end=next_dt.strftime("%Y-%m-%d"), interval="1m", prepost=True)
            if not df.empty:
                tz = pytz.timezone("US/Pacific")
                try:
                    df.index = df.index.tz_convert(tz)
                except Exception as e:
                    print(f"Error converting timezone: {e}")
                spy_data[d_str] = df
                
        stopped_out_correct_count = 0
        wrong_direction_count = 0
        early_exits_count = 0
        great_trades_count = 0
        
        stopped_drawdowns = []
        early_exit_moves = []
        
        MOVE_THRESHOLD = 0.50
        
        for t in spy_trades:
            d_str = t["entry_time"].strftime("%Y-%m-%d")
            if d_str not in spy_data:
                continue
            df = spy_data[d_str]
            
            tz = pytz.timezone("US/Pacific")
            entry_dt = tz.localize(t["entry_time"])
            exit_dt = tz.localize(t["exit_time"])
            
            try:
                entry_idx = int(df.index.get_indexer([entry_dt], method='nearest')[0])
                exit_idx = int(df.index.get_indexer([exit_dt], method='nearest')[0])
            except Exception as e:
                continue
                
            spy_entry_price = float(df.iloc[entry_idx]['Close'])
            spy_exit_price = float(df.iloc[exit_idx]['Close'])
            
            start_idx = min(entry_idx, exit_idx)
            end_idx = max(entry_idx, exit_idx)
            trade_df = df.iloc[start_idx:end_idx+1]
            
            max_spy_price = float(trade_df['High'].max())
            min_spy_price = float(trade_df['Low'].min())
            
            if t.get("option_type") == "PUT":
                underlying_dir = "SHORT" if t["direction"] == "LONG" else "LONG"
            else:
                underlying_dir = t["direction"]
                
            if underlying_dir == "LONG":
                max_runup = max_spy_price - spy_entry_price
                max_drawdown = spy_entry_price - min_spy_price
            else:
                max_runup = spy_entry_price - min_spy_price
                max_drawdown = max_spy_price - spy_entry_price
                
            # Post exit move (60 minutes)
            post_exit_dt = exit_dt + timedelta(minutes=60)
            post_exit_idx = int(df.index.get_indexer([post_exit_dt], method='nearest')[0])
            post_df = df.iloc[exit_idx:post_exit_idx+1] if post_exit_idx > exit_idx else pd.DataFrame()
            
            if not post_df.empty:
                max_spy_post = float(post_df['High'].max())
                min_spy_post = float(post_df['Low'].min())
                
                if underlying_dir == "LONG":
                    max_post_runup = max_spy_post - spy_entry_price
                    favorable_post_exit_move = max_spy_post - spy_exit_price
                else:
                    max_post_runup = spy_entry_price - min_spy_post
                    favorable_post_exit_move = spy_exit_price - min_spy_post
            else:
                max_post_runup = 0.0
                favorable_post_exit_move = 0.0
                
            is_win = t["pnl"] > 0
            if is_win:
                if favorable_post_exit_move >= MOVE_THRESHOLD:
                    early_exits_count += 1
                    early_exit_moves.append(favorable_post_exit_move)
                else:
                    great_trades_count += 1
            else:
                overall_max_runup = max(max_runup, max_post_runup)
                if overall_max_runup >= MOVE_THRESHOLD:
                    stopped_out_correct_count += 1
                    stopped_drawdowns.append(max_drawdown)
                else:
                    wrong_direction_count += 1
                    
        total_pnl = sum(t["pnl"] for t in spy_trades)
        wins = [t for t in spy_trades if t["win"]]
        losses = [t for t in spy_trades if not t["win"]]
        win_rate = (len(wins) / len(spy_trades)) * 100 if spy_trades else 0.0
        
        avg_drawdown_stopped = sum(stopped_drawdowns) / len(stopped_drawdowns) if stopped_drawdowns else 0.0
        max_early_move = max(early_exit_moves) if early_exit_moves else 0.0
        
        # 1. Stop after first 3 trades of the day
        trades_3 = spy_trades[:3]
        sim_3_total = len(trades_3)
        sim_3_wins = len([t for t in trades_3 if t["win"]])
        sim_3_losses = len([t for t in trades_3 if not t["win"]])
        sim_3_pnl = sum(t["pnl"] for t in trades_3)
        
        # 2. Stop after 2 consecutive losses
        trades_2l = []
        consec_losses = 0
        for t in spy_trades:
            trades_2l.append(t)
            if not t["win"]:
                consec_losses += 1
            else:
                consec_losses = 0
            if consec_losses >= 2:
                break
                
        sim_2l_total = len(trades_2l)
        sim_2l_wins = len([t for t in trades_2l if t["win"]])
        sim_2l_losses = len([t for t in trades_2l if not t["win"]])
        sim_2l_pnl = sum(t["pnl"] for t in trades_2l)
        
        recommendations = []
        donts = []
        
        if stopped_out_correct_count > 0:
            recommendations.append(f"Increase stop-loss buffer to ${avg_drawdown_stopped + 0.15:.2f} on SPY chart. Your average shakeout drawdown on correct entries was ${avg_drawdown_stopped:.2f}. Letting them breathe will turn losses into wins.")
            donts.append(f"DO NOT use tight stops under ${avg_drawdown_stopped + 0.10:.2f} on SPY options, which trigger premature shakeouts.")
        else:
            recommendations.append("Your stop-losses are well-placed. Keep using technical indicators (like 9/21 EMAs or swing lows) for placement.")
            
        if early_exits_count > 0:
            recommendations.append(f"Implement a 2-stage exit: sell 50% at your initial target, and trail the remainder using the 1-minute 9 EMA to capture extended runs (SPY ran up to +${max_early_move:.2f} post-exit today).")
            donts.append("DO NOT panic sell 100% of your position at the first minor profit target; let your runners capture the main trend.")
            
        if len(spy_trades) > 5:
            recommendations.append(f"Limit your trading frequency. You executed {len(spy_trades)} trades in a single session. Aim for 2-3 high-conviction A+ setups.")
            donts.append(f"DO NOT trade more than 3 positions per session to avoid overtrading, emotional fatigue, and high commission costs.")
            
        early_entries = [t for t in spy_trades if t["entry_time"].time() < datetime.strptime("06:35:00", "%H:%M:%S").time()]
        if early_entries:
            donts.append("DO NOT enter trades during the first 5 minutes of market open (before 6:35 AM PT / 9:35 AM ET) when volatility and options spreads are widest.")
            recommendations.append("Wait at least 5-15 minutes after market open for initial range discovery before taking a position.")
            
        summary = {
            "total_trades": len(spy_trades),
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "wins_count": len(wins),
            "losses_count": len(losses),
            "stopped_out_correct": stopped_out_correct_count,
            "wrong_direction": wrong_direction_count,
            "early_exits": early_exits_count,
            "great_trades": great_trades_count,
            "avg_drawdown_stopped": round(avg_drawdown_stopped, 2),
            "right_direction_count": len(wins) + stopped_out_correct_count,
            "sim_3_total": sim_3_total,
            "sim_3_wins": sim_3_wins,
            "sim_3_losses": sim_3_losses,
            "sim_3_pnl": round(sim_3_pnl, 2),
            "sim_2l_total": sim_2l_total,
            "sim_2l_wins": sim_2l_wins,
            "sim_2l_losses": sim_2l_losses,
            "sim_2l_pnl": round(sim_2l_pnl, 2),
            "recommendations": recommendations,
            "donts": donts
        }
        
        # Save cache
        cache[filename] = {
            "mtime": mtime,
            "summary": summary
        }
        save_analysis_cache(cache)
        
        return jsonify({"ok": True, "summary": summary})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/analysis/monthly")
def api_analysis_monthly():
    """Aggregate cached daily summaries chronologically for monthly/historical charting"""
    try:
        cache = load_analysis_cache()
        files = [f for f in os.listdir(TOS_DIR) if f.endswith(".csv")]
        
        monthly_data = []
        cache_dirty = False
        
        for f in files:
            filepath = os.path.join(TOS_DIR, f)
            mtime = os.path.getmtime(filepath)
            
            if f in cache and cache[f].get("mtime") == mtime:
                # If cached summary doesn't have right_direction_count or sim data, force recompute
                summary = cache[f]["summary"]
                if "right_direction_count" in summary and "sim_3_pnl" in summary:
                    monthly_data.append(summary)
                    continue
            
            # Recompute and cache if missing
            try:
                executions = tos_parser.parse_tos_csv(filepath)
                trades = tos_parser.pair_trades(executions)
                
                spy_trades = [t for t in trades if t.get("underlying") == "SPY" and t.get("closed")]
                if not spy_trades:
                    continue
                    
                spy_trades.sort(key=lambda x: x["entry_time"])
                
                # Fetch yfinance price history
                dates = set(t["entry_time"].strftime("%Y-%m-%d") for t in spy_trades)
                spy_data = {}
                for d_str in dates:
                    dt = datetime.strptime(d_str, "%Y-%m-%d")
                    next_dt = dt + timedelta(days=1)
                    df = yf.Ticker("SPY").history(start=d_str, end=next_dt.strftime("%Y-%m-%d"), interval="1m", prepost=True)
                    if not df.empty:
                        tz = pytz.timezone("US/Pacific")
                        try:
                            df.index = df.index.tz_convert(tz)
                        except:
                            pass
                        spy_data[d_str] = df
                        
                stopped_out_correct_count = 0
                wrong_direction_count = 0
                early_exits_count = 0
                great_trades_count = 0
                stopped_drawdowns = []
                early_exit_moves = []
                
                MOVE_THRESHOLD = 0.50
                
                for t in spy_trades:
                    d_str = t["entry_time"].strftime("%Y-%m-%d")
                    if d_str not in spy_data:
                        continue
                    df = spy_data[d_str]
                    
                    tz = pytz.timezone("US/Pacific")
                    entry_dt = tz.localize(t["entry_time"])
                    exit_dt = tz.localize(t["exit_time"])
                    
                    try:
                        entry_idx = int(df.index.get_indexer([entry_dt], method='nearest')[0])
                        exit_idx = int(df.index.get_indexer([exit_dt], method='nearest')[0])
                    except:
                        continue
                        
                    spy_entry_price = float(df.iloc[entry_idx]['Close'])
                    spy_exit_price = float(df.iloc[exit_idx]['Close'])
                    
                    start_idx = min(entry_idx, exit_idx)
                    end_idx = max(entry_idx, exit_idx)
                    trade_df = df.iloc[start_idx:end_idx+1]
                    
                    max_spy_price = float(trade_df['High'].max())
                    min_spy_price = float(trade_df['Low'].min())
                    
                    if t.get("option_type") == "PUT":
                        underlying_dir = "SHORT" if t["direction"] == "LONG" else "LONG"
                    else:
                        underlying_dir = t["direction"]
                        
                    if underlying_dir == "LONG":
                        max_runup = max_spy_price - spy_entry_price
                        max_drawdown = spy_entry_price - min_spy_price
                    else:
                        max_runup = spy_entry_price - min_spy_price
                        max_drawdown = max_spy_price - spy_entry_price
                        
                    post_exit_dt = exit_dt + timedelta(minutes=60)
                    post_exit_idx = int(df.index.get_indexer([post_exit_dt], method='nearest')[0])
                    post_df = df.iloc[exit_idx:post_exit_idx+1] if post_exit_idx > exit_idx else pd.DataFrame()
                    
                    if not post_df.empty:
                        max_spy_post = float(post_df['High'].max())
                        min_spy_post = float(post_df['Low'].min())
                        
                        if underlying_dir == "LONG":
                            max_post_runup = max_spy_post - spy_entry_price
                            favorable_post_exit_move = max_spy_post - spy_exit_price
                        else:
                            max_post_runup = spy_entry_price - min_spy_post
                            favorable_post_exit_move = spy_exit_price - min_spy_post
                    else:
                        max_post_runup = 0.0
                        favorable_post_exit_move = 0.0
                        
                    is_win = t["pnl"] > 0
                    if is_win:
                        if favorable_post_exit_move >= MOVE_THRESHOLD:
                            early_exits_count += 1
                            early_exit_moves.append(favorable_post_exit_move)
                        else:
                            great_trades_count += 1
                    else:
                        overall_max_runup = max(max_runup, max_post_runup)
                        if overall_max_runup >= MOVE_THRESHOLD:
                            stopped_out_correct_count += 1
                            stopped_drawdowns.append(max_drawdown)
                        else:
                            wrong_direction_count += 1
                            
                total_pnl = sum(t["pnl"] for t in spy_trades)
                wins = [t for t in spy_trades if t["win"]]
                losses = [t for t in spy_trades if not t["win"]]
                win_rate = (len(wins) / len(spy_trades)) * 100 if spy_trades else 0.0
                
                avg_drawdown_stopped = sum(stopped_drawdowns) / len(stopped_drawdowns) if stopped_drawdowns else 0.0
                max_early_move = max(early_exit_moves) if early_exit_moves else 0.0
                
                # 1. Stop after first 3 trades of the day
                trades_3 = spy_trades[:3]
                sim_3_total = len(trades_3)
                sim_3_wins = len([t for t in trades_3 if t["win"]])
                sim_3_losses = len([t for t in trades_3 if not t["win"]])
                sim_3_pnl = sum(t["pnl"] for t in trades_3)
                
                # 2. Stop after 2 consecutive losses
                trades_2l = []
                consec_losses = 0
                for t in spy_trades:
                    trades_2l.append(t)
                    if not t["win"]:
                        consec_losses += 1
                    else:
                        consec_losses = 0
                    if consec_losses >= 2:
                        break
                        
                sim_2l_total = len(trades_2l)
                sim_2l_wins = len([t for t in trades_2l if t["win"]])
                sim_2l_losses = len([t for t in trades_2l if not t["win"]])
                sim_2l_pnl = sum(t["pnl"] for t in trades_2l)
                
                recommendations = []
                donts = []
                
                if stopped_out_correct_count > 0:
                    recommendations.append(f"Increase stop-loss buffer to ${avg_drawdown_stopped + 0.15:.2f} on SPY chart. Your average shakeout drawdown on correct entries was ${avg_drawdown_stopped:.2f}. Letting them breathe will turn losses into wins.")
                    donts.append(f"DO NOT use tight stops under ${avg_drawdown_stopped + 0.10:.2f} on SPY options, which trigger premature shakeouts.")
                else:
                    recommendations.append("Your stop-losses are well-placed. Keep using technical indicators (like 9/21 EMAs or swing lows) for placement.")
                    
                if early_exits_count > 0:
                    recommendations.append(f"Implement a 2-stage exit: sell 50% at your initial target, and trail the remainder using the 1-minute 9 EMA to capture extended runs (SPY ran up to +${max_early_move:.2f} post-exit today).")
                    donts.append("DO NOT panic sell 100% of your position at the first minor profit target; let your runners capture the main trend.")
                    
                if len(spy_trades) > 5:
                    recommendations.append(f"Limit your trading frequency. You executed {len(spy_trades)} trades in a single session. Aim for 2-3 high-conviction A+ setups.")
                    donts.append(f"DO NOT trade more than 3 positions per session to avoid overtrading, emotional fatigue, and high commission costs.")
                    
                early_entries = [t for t in spy_trades if t["entry_time"].time() < datetime.strptime("06:35:00", "%H:%M:%S").time()]
                if early_entries:
                    donts.append("DO NOT enter trades during the first 5 minutes of market open (before 6:35 AM PT / 9:35 AM ET) when volatility and options spreads are widest.")
                    recommendations.append("Wait at least 5-15 minutes after market open for initial range discovery before taking a position.")
                
                summary = {
                    "date": spy_trades[0]["entry_time"].strftime("%Y-%m-%d"),
                    "total_trades": len(spy_trades),
                    "win_rate": round(win_rate, 1),
                    "total_pnl": round(total_pnl, 2),
                    "wins_count": len(wins),
                    "losses_count": len(losses),
                    "stopped_out_correct": stopped_out_correct_count,
                    "wrong_direction": wrong_direction_count,
                    "early_exits": early_exits_count,
                    "great_trades": great_trades_count,
                    "avg_drawdown_stopped": round(avg_drawdown_stopped, 2),
                    "right_direction_count": len(wins) + stopped_out_correct_count,
                    "sim_3_total": sim_3_total,
                    "sim_3_wins": sim_3_wins,
                    "sim_3_losses": sim_3_losses,
                    "sim_3_pnl": round(sim_3_pnl, 2),
                    "sim_2l_total": sim_2l_total,
                    "sim_2l_wins": sim_2l_wins,
                    "sim_2l_losses": sim_2l_losses,
                    "sim_2l_pnl": round(sim_2l_pnl, 2),
                    "recommendations": recommendations,
                    "donts": donts
                }
                
                cache[f] = {
                    "mtime": mtime,
                    "summary": summary
                }
                cache_dirty = True
                monthly_data.append(summary)
            except Exception as e:
                print(f"Error parsing file {f}: {e}")
                continue
                
        if cache_dirty:
            save_analysis_cache(cache)
            
        # Sort chronologically by date
        monthly_data.sort(key=lambda x: x["date"])
        return jsonify({"ok": True, "data": monthly_data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

import xml.etree.ElementTree as ET

@app.route("/api/news")
def get_market_news():
    """Fetch live market news for SPY from Alpaca or Yahoo Finance RSS"""
    alpaca_key = os.getenv("ALPACA_API_KEY")
    alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
    
    if alpaca_key and alpaca_secret:
        try:
            import urllib.request
            headers = {
                "Apca-Api-Key-Id": alpaca_key,
                "Apca-Api-Secret-Key": alpaca_secret
            }
            url = "https://data.alpaca.markets/v1beta1/news?symbols=SPY&limit=10"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                news_data = json.loads(response.read().decode('utf-8'))
                
            news_items = []
            for item in news_data.get("news", []):
                news_items.append({
                    "title": item["headline"],
                    "source": item.get("source", "Alpaca"),
                    "link": item["url"],
                    "time": item["updated_at"]
                })
            return jsonify({"ok": True, "news": news_items, "source": "Alpaca"})
        except Exception as e:
            print(f"Error fetching Alpaca news: {e}")
            
    # Fallback to Yahoo Finance RSS
    try:
        import urllib.request
        url = "https://finance.yahoo.com/rss/headline?s=SPY"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        news_items = []
        for item in root.findall('.//item')[:10]:
            title_el = item.find('title')
            link_el = item.find('link')
            pub_el = item.find('pubDate')
            
            title = title_el.text if title_el is not None else "No Title"
            link = link_el.text if link_el is not None else "#"
            pubDate = pub_el.text if pub_el is not None else "Just Now"
            
            news_items.append({
                "title": title,
                "source": "Yahoo Finance",
                "link": link,
                "time": pubDate
            })
        return jsonify({"ok": True, "news": news_items, "source": "Yahoo RSS"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/live-chart-history")
def get_live_chart_history():
    """Fetch current day's 1-minute historical candles for SPY live chart"""
    tz = pytz.timezone("US/Pacific")
    try:
        ticker = yf.Ticker("SPY")
        df = ticker.history(period="3d", interval="1m", prepost=True)
        if df.empty:
            return jsonify({"ok": False, "error": "No price data found"}), 404
            
        df.index = df.index.tz_convert(tz)
        
        # Filter to the latest active day in the index
        latest_date = df.index[-1].date()
        df = df[df.index.date == latest_date]
        
        # Calculate VWAP, EMA 9, EMA 21
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        df['TypicalVolume'] = typical_price * df['Volume']
        df['CumTypicalVolume'] = df['TypicalVolume'].cumsum()
        df['CumVolume'] = df['Volume'].cumsum()
        df['VWAP'] = df['CumTypicalVolume'] / df['CumVolume'].replace(0, 1)
        
        df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        
        candles = []
        for idx, row in df.iterrows():
            candles.append({
                "time": int(idx.timestamp()),
                "open": round(float(row['Open']), 2),
                "high": round(float(row['High']), 2),
                "low": round(float(row['Low']), 2),
                "close": round(float(row['Close']), 2),
                "volume": int(row['Volume']),
                "vwap": round(float(row['VWAP']), 2) if not pd.isna(row['VWAP']) else None,
                "ema9": round(float(row['EMA9']), 2) if not pd.isna(row['EMA9']) else None,
                "ema21": round(float(row['EMA21']), 2) if not pd.isna(row['EMA21']) else None
            })
            
        return jsonify({
            "ok": True, 
            "candles": candles, 
            "date": latest_date.strftime("%Y-%m-%d")
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/control/restart_server", methods=["POST"])
def restart_server():
    """Restart the dashboard server process to pick up code changes."""
    import threading
    def do_restart():
        time.sleep(0.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=do_restart, daemon=True).start()
    return jsonify({"ok": True, "messages": ["Server restarting..."]})


if __name__ == "__main__":
    # install psutil if missing
    try:
        import psutil
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "psutil", "-q"])
        import psutil
    print("Dashboard running at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
