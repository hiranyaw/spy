"""
SPY Trader Dashboard Server
Run: python dashboard_server.py
Open: http://localhost:5000
"""
from flask import Flask, jsonify, send_from_directory, request
import json, os, subprocess, signal, sys, time, math
import psutil
from datetime import datetime

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

def load_trendline_breaks():
    try:
        with open(TRENDLINE_BREAKS) as f:
            return json.load(f)
    except:
        return {"breaks": []}

def save_trendline_breaks(data):
    with open(TRENDLINE_BREAKS, "w") as f:
        json.dump(data, f, indent=2)

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
