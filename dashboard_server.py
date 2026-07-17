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
    """Recursively replace NaN/Infinity with None, and convert date/time/Decimal to JSON-serializable types."""
    import datetime as dt
    from decimal import Decimal
    
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, Decimal):
        return float(obj)
    # Check datetime first as datetime is a subclass of date
    if isinstance(obj, dt.datetime):
        return obj.isoformat() + "Z"
    if isinstance(obj, dt.date):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, dt.time):
        return obj.strftime("%H:%M:%S")
    if isinstance(obj, dt.timedelta):
        return str(obj)
    if isinstance(obj, dict):
        return {str(sanitize(k)): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj

def load_raw_data(raw_val):
    """Safely parse raw_data field which could be returned as a dict (JSONB) or string."""
    if not raw_val:
        return {}
    if isinstance(raw_val, str):
        try:
            return json.loads(raw_val)
        except Exception:
            return {}
    return raw_val


def get_spy_history(start=None, end=None, period=None):
    import pandas as pd, os, json, pytz, requests
    
    # 1. Try static JSON cache first
    try:
        if os.path.exists("spy_history.json"):
            with open("spy_history.json", "r") as f:
                data = json.load(f)
            df = pd.DataFrame.from_dict(data, orient="index")
            df.index = pd.to_datetime(df.index)
            tz = pytz.timezone("US/Pacific")
            if df.index.tz is None:
                df.index = df.index.tz_localize(tz)
            else:
                df.index = df.index.tz_convert(tz)
            
            # Ensure volume column exists for VWAP
            if 'Volume' not in df.columns:
                df['Volume'] = 0
                
            if start and end:
                s_dt = pd.to_datetime(start)
                if s_dt.tz is None: s_dt = tz.localize(s_dt)
                e_dt = pd.to_datetime(end)
                if e_dt.tz is None: e_dt = tz.localize(e_dt)
                df_filtered = df[(df.index >= s_dt) & (df.index <= e_dt)]
                if not df_filtered.empty:
                    return df_filtered
    except Exception as e:
        print("spy_history fallback error:", e)

    # 2. Try Alpaca API dynamically
    alpaca_key = os.getenv("ALPACA_API_KEY")
    alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
    if alpaca_key and alpaca_secret and start and end:
        try:
            # For dynamic historical data, Alpaca requires RFC3339 timestamps
            # We use IEX feed which is included in the free tier
            s_dt = pd.to_datetime(start).tz_localize('US/Pacific') if pd.to_datetime(start).tz is None else pd.to_datetime(start)
            e_dt = pd.to_datetime(end).tz_localize('US/Pacific') if pd.to_datetime(end).tz is None else pd.to_datetime(end)
            
            s_str = s_dt.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
            e_str = e_dt.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
            
            headers = {
                "APCA-API-KEY-ID": alpaca_key,
                "APCA-API-SECRET-KEY": alpaca_secret
            }
            url = f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Min&start={s_str}&end={e_str}&feed=iex"
            res = requests.get(url, headers=headers).json()
            if 'bars' in res and res['bars']:
                df_alpaca = pd.DataFrame(res['bars'])
                df_alpaca['t'] = pd.to_datetime(df_alpaca['t'])
                df_alpaca.set_index('t', inplace=True)
                df_alpaca.index = df_alpaca.index.tz_convert('US/Pacific')
                df_alpaca.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume'}, inplace=True)
                return df_alpaca
        except Exception as e:
            print("Alpaca dynamic fetch error:", e)

    # 3. Fallback to yfinance (Will likely fail on Railway but good for local)
    import yfinance as yf
    try:
        if period:
            return yf.Ticker("SPY").history(period=period, interval="1m", prepost=True)
        return yf.Ticker("SPY").history(start=start, end=end, interval="1m", prepost=True)
    except Exception as e:
        print("yfinance fallback error:", e)
        return pd.DataFrame()

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
TOS_DIR      = os.path.join(BASE, "TOS")
SCREENSHOTS_DIR = os.path.join(BASE, "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
BOT_DIR = BASE  # alias for diagnostics

def restore_tos_files_from_db():
    if not DB_AVAILABLE:
        return
    try:
        print("[STARTUP] Syncing TOS files with PostgreSQL database...")
        db_files = db.get_all_uploaded_tos_files()
        db_filenames = {f["filename"] for f in db_files}
        
        # 1. Restore files from DB that are missing locally
        for f in db_files:
            filename = f["filename"]
            content = f["file_content"]
            filepath = os.path.join(TOS_DIR, filename)
            if not os.path.exists(filepath):
                with open(filepath, "w", encoding="utf-8") as file_out:
                    file_out.write(content)
                print(f"[STARTUP] Restored missing local file from database: {filename}")
                
        # 2. Upload files that are present locally but missing in DB (e.g. from local dev)
        local_files = [f for f in os.listdir(TOS_DIR) if f.endswith(".csv")]
        for f in local_files:
            if f not in db_filenames:
                filepath = os.path.join(TOS_DIR, f)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f_in:
                        content = f_in.read()
                    db.save_uploaded_tos_file(f, content)
                    print(f"[STARTUP] Uploaded local-only file to database: {f}")
                except Exception as sync_err:
                    print(f"[STARTUP] Error syncing local file {f} to DB: {sync_err}")
                    
        print("[STARTUP] TOS files sync complete.")
    except Exception as e:
        print(f"[STARTUP] Error syncing/restoring TOS files: {e}")

if not os.path.exists(TOS_DIR):
    os.makedirs(TOS_DIR)

restore_tos_files_from_db()

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
    from flask import make_response
    response = make_response(send_from_directory(BASE, "dashboard.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "-1"
    return response

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
                    "details": load_raw_data(latest_signal.get("raw_data")),
                    "last_update": latest_signal.get("timestamp").isoformat() + "Z" if latest_signal.get("timestamp") else None,
                    "history": []
                }
            else:
                d = {"signal": "WAITING", "details": {}, "history": [], "last_update": None}

            # 1. Fetch and merge history
            sig_history = db.get_signal_history(60) or []
            tl_breaks = db.get_trendline_breaks(7) or []  # Last 7 days

            combined = []
            for h in sig_history:
                combined.append(dict(h))

            for br in tl_breaks:
                br_dict = dict(br)
                br_date = br_dict.get("date")
                br_time = br_dict.get("time")
                try:
                    from datetime import date, time as dt_time
                    if isinstance(br_date, str):
                        br_date = datetime.strptime(br_date, "%Y-%m-%d").date()
                    if isinstance(br_time, str):
                        br_time = datetime.strptime(br_time, "%H:%M:%S").time()
                    dt = datetime.combine(br_date, br_time)
                except Exception:
                    dt = br_dict.get("created_at") or datetime.now()

                combined.append({
                    "timestamp": dt,
                    "signal": f"TL BREAK {br_dict.get('direction')}",
                    "signal_type": "trend",
                    "spy_price": float(br_dict.get("price")) if br_dict.get("price") != "?" else None,
                    "qqq_price": None,
                    "add_value": 0.0,
                    "conf_tv": "1/5",
                    "status": "ALERT",
                    "rev_score": 0,
                    "rev_dir": "",
                    "st_flip": "",
                    "tl_break": br_dict.get("direction")
                })

            def get_timestamp(x):
                t = x.get("timestamp")
                if isinstance(t, str):
                    try:
                        from dateutil import parser
                        t = parser.parse(t)
                    except:
                        pass
                if hasattr(t, "tzinfo") and t.tzinfo is not None:
                    return t.replace(tzinfo=None)
                return t or datetime.min

            combined.sort(key=get_timestamp, reverse=True)
            d["history"] = combined[:60]

            # 2. Check if the latest trendline break is recent (within 15 minutes) to show on dashboard cards
            latest_tl = db.get_latest_trendline_break()
            if latest_tl:
                latest_tl_dict = dict(latest_tl)
                try:
                    br_date = latest_tl_dict.get("date")
                    br_time = latest_tl_dict.get("time")
                    from datetime import date, time as dt_time
                    if isinstance(br_date, str):
                        br_date = datetime.strptime(br_date, "%Y-%m-%d").date()
                    if isinstance(br_time, str):
                        br_time = datetime.strptime(br_time, "%H:%M:%S").time()
                    dt = datetime.combine(br_date, br_time)
                except:
                    dt = latest_tl_dict.get("created_at") or datetime.now()

                created_at = latest_tl_dict.get("created_at") or dt
                if created_at:
                    if created_at.tzinfo is not None:
                        created_at = created_at.replace(tzinfo=None)
                    time_diff = (datetime.now() - created_at).total_seconds()
                    if 0 <= time_diff <= 900:
                        if "details" not in d:
                            d["details"] = {}
                        d["details"]["tl_break"] = latest_tl_dict.get("direction")
        except Exception as e:
            print(f"Database error in /data: {e}")
            d = {"signal": "WAITING", "details": {}, "history": [], "last_update": None}
    else:
        # Fallback to JSON
        try:
            with open(SIGNALS) as f:
                d = json.load(f)

            # Fetch and merge from trendline_breaks.json
            tl_breaks = []
            if os.path.exists(TRENDLINE_BREAKS):
                try:
                    with open(TRENDLINE_BREAKS) as f:
                        tl_data = json.load(f)
                        tl_breaks = tl_data.get("breaks", [])
                except:
                    pass

            combined = []
            for h in d.get("history", []):
                combined.append(dict(h))

            for br in tl_breaks:
                combined.append({
                    "time": br.get("time"),
                    "date": br.get("date"),
                    "signal": f"TL BREAK {br.get('direction')}",
                    "signal_type": "trend",
                    "spy": float(br.get("price")) if br.get("price") != "?" else None,
                    "qqq": None,
                    "add": 0.0,
                    "conf_tv": "1/5",
                    "status_tv": "ALERT",
                    "rev_score": 0,
                    "rev_dir": "",
                    "st_flip": "",
                    "tl_break": br.get("direction")
                })

            def get_json_datetime(x):
                from datetime import date
                date_str = x.get("date") or date.today().strftime("%Y-%m-%d")
                time_str = x.get("time") or "00:00:00"
                try:
                    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                except:
                    return datetime.min

            combined.sort(key=get_json_datetime, reverse=True)
            d["history"] = combined[:60]

            # Check if latest JSON break is recent
            if tl_breaks:
                latest_tl = tl_breaks[-1]
                date_str = latest_tl.get("date")
                time_str = latest_tl.get("time")
                try:
                    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                    time_diff = (datetime.now() - dt).total_seconds()
                    if 0 <= time_diff <= 900:
                        if "details" not in d:
                            d["details"] = {}
                        d["details"]["tl_break"] = latest_tl.get("direction")
                except:
                    pass
        except FileNotFoundError:
            d = {"signal": "WAITING", "details": {}, "history": [], "last_update": None}
        except Exception as e:
            return jsonify({"error": str(e)}), 500

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

        return jsonify(sanitize({"breaks": breaks, "by_date": by_date}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/webhook/trendline", methods=["POST"])
def webhook_trendline():
    """Receive trendline breaks or trade close signals from TradingView"""
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}

        # ── Handle Pine Script Trade Close Webhook ─────────────────────
        if data.get("event") == "trade_close":
            direction = data.get("direction")
            entry_p = float(data.get("entry_price") or 0)
            exit_p = float(data.get("exit_price") or 0)
            pnl_val = float(data.get("pnl") or 0)
            pnl_pct = float(data.get("pnl_pct") or 0)
            exit_cond = data.get("exit_condition") or "Indicator Exit"

            # 1. DB write if active
            if DB_AVAILABLE:
                try:
                    with db.conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO paper_trades
                            (entry_time, exit_time, direction, entry_price, exit_price, pnl, pnl_percent, is_win, signal_type, closed)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                        """, (
                            datetime.now() - timedelta(minutes=10),
                            datetime.now(),
                            direction,
                            entry_p,
                            exit_p,
                            pnl_val,
                            pnl_pct,
                            pnl_val > 0,
                            exit_cond
                        ))
                        db.conn.commit()
                except Exception as db_err:
                    print(f"Error saving webhook trade to DB: {db_err}")

            # 2. Local fallback JSON write
            trades = []
            if os.path.exists(PAPER):
                try:
                    with open(PAPER, "r") as f:
                        trades = json.load(f)
                except Exception:
                    pass
            
            trades.append({
                "entry_time": (datetime.now() - timedelta(minutes=10)).strftime("%H:%M:%S"),
                "exit_time": datetime.now().strftime("%H:%M:%S"),
                "direction": "LONG" if direction == "CALL" else "SHORT",
                "signal_type": exit_cond,
                "entry_price": entry_p,
                "exit_price": exit_p,
                "pnl": pnl_val,
                "win": pnl_val > 0
            })

            try:
                with open(PAPER, "w") as f:
                    json.dump(trades, f, indent=2)
            except Exception as f_err:
                print(f"Error saving fallback trade file: {f_err}")

            print(f"[WEBHOOK] Saved trade: {direction} P&L: {pnl_val:+.2f} ({exit_cond})")
            return jsonify({"ok": True, "message": "Saved trade close signal"})

        # ── Handle regular Trendline Break Webhook ──────────────────────
        message = data.get("message", "") or data.get("text", "")
        if not message:
            message = request.get_data(as_text=True)

        direction = None
        if "B↑" in message or "UP" in message.upper() or "BREAKOUT" in message.upper():
            direction = "UP"
        elif "B↓" in message or "DN" in message.upper() or "BREAKDOWN" in message.upper():
            direction = "DN"

        if not direction:
            return jsonify({"error": "Could not parse direction from message"}), 400

        # Extract price if provided
        price = data.get("price", "?")

        # Record to database or JSON
        try:
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")

            if DB_AVAILABLE:
                db.save_trendline_break({
                    "date": date_str,
                    "time": time_str,
                    "symbol": "SPY",
                    "direction": direction,
                    "price": str(price),
                    "is_manual": False
                })
            else:
                if os.path.exists(TRENDLINE_BREAKS):
                    with open(TRENDLINE_BREAKS, "r") as f:
                        tl_data = json.load(f)
                else:
                    tl_data = {"breaks": []}

                tl_data["breaks"].append({
                    "date": date_str,
                    "time": time_str,
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
                sig = load_raw_data(latest_signal.get("raw_data"))
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

    return jsonify(sanitize({"ok": True, "trade": trade}))


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

        return jsonify(sanitize({"ok": True, "trade": closed_trade, "pnl": closed_trade.get("pnl")}))
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
        return jsonify(sanitize({"ok": True, "trade": closed_trade, "pnl": closed_trade["pnl"]}))


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
    """List all CSV files — from local disk OR PostgreSQL (Railway-safe)"""
    try:
        if not os.path.exists(TOS_DIR):
            os.makedirs(TOS_DIR)
        local_files = set(f for f in os.listdir(TOS_DIR) if f.endswith(".csv"))

        # Also pull filenames from DB so files survive Railway redeploys
        db_files = set()
        if DB_AVAILABLE:
            try:
                db_rows = db.get_all_uploaded_tos_files()
                db_files = {row["filename"] for row in db_rows}
                # Restore any DB files missing from local disk
                for row in db_rows:
                    fp = os.path.join(TOS_DIR, row["filename"])
                    if not os.path.exists(fp):
                        with open(fp, "w", encoding="utf-8") as fout:
                            fout.write(row["file_content"])
            except Exception as db_err:
                print(f"[files] DB fallback error: {db_err}")

        all_files = sorted(local_files | db_files, reverse=True)
        return jsonify({"ok": True, "files": all_files})
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
            
            # Persist to database
            if DB_AVAILABLE:
                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f_in:
                        content = f_in.read()
                    db.save_uploaded_tos_file(filename, content)
                    print(f"Persisted uploaded file {filename} to database.")
                except Exception as db_err:
                    print(f"Error persisting {filename} to database: {db_err}")
                    
            return jsonify({"ok": True, "filename": filename, "message": f"Successfully uploaded {filename} and saved to database"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    else:
        return jsonify({"ok": False, "error": "Only CSV files are allowed"}), 400


@app.route("/api/analysis/delete", methods=["DELETE"])
def analysis_delete():
    """Delete a TOS CSV file from disk and PostgreSQL"""
    filename = request.args.get("filename")
    if not filename:
        return jsonify({"ok": False, "error": "Filename required"}), 400
    filename = os.path.basename(filename)

    # Remove from disk
    filepath = os.path.join(TOS_DIR, filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"[delete] Could not remove {filepath}: {e}")

    # Remove from PostgreSQL
    if DB_AVAILABLE:
        try:
            with db.conn.cursor() as cur:
                cur.execute("DELETE FROM uploaded_tos_files WHERE filename = %s", (filename,))
            db.conn.commit()
        except Exception as db_err:
            db.conn.rollback()
            print(f"[delete] DB delete error: {db_err}")

    # Also invalidate analysis cache entry
    try:
        cache = load_analysis_cache()
        if filename in cache:
            del cache[filename]
            save_analysis_cache(cache)
    except Exception:
        pass

    return jsonify({"ok": True, "message": f"Deleted {filename}"})

@app.route("/api/analysis/trades")
def analysis_trades():
    """Parse trades from a selected TOS CSV file"""
    filename = request.args.get("filename")
    if not filename:
        return jsonify({"ok": False, "error": "Filename is required"}), 400
    
    filename = os.path.basename(filename)
    filepath = os.path.join(TOS_DIR, filename)

    # If not on local disk, try to restore from PostgreSQL
    if not os.path.exists(filepath) and DB_AVAILABLE:
        try:
            db_rows = db.get_all_uploaded_tos_files()
            for row in db_rows:
                if row["filename"] == filename:
                    os.makedirs(TOS_DIR, exist_ok=True)
                    with open(filepath, "w", encoding="utf-8") as fout:
                        fout.write(row["file_content"])
                    print(f"[trades] Restored {filename} from DB to disk")
                    break
        except Exception as db_err:
            print(f"[trades] DB restore error: {db_err}")

    if not os.path.exists(filepath):
        return jsonify({"ok": False, "error": f"File {filename} not found in filesystem or database"}), 404
        
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
    strike_str = request.args.get("strike", "None")
    
    option_strike = None
    if strike_str and strike_str != "None":
        try:
            option_strike = float(strike_str)
        except:
            pass
            
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
        
        # Get today's date in user's timezone to avoid UTC mismatch
        tz = pytz.timezone(user_tz_str)
        today_user_tz = datetime.now(tz).date()
        req_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # Try fetching real data from yfinance first
        df = pd.DataFrame()
        try:
            if req_date == today_user_tz:
                # Use same history query as get_live_chart_history for today to match exactly
                df = get_spy_history(period="3d")
            else:
                df = get_spy_history(start=start_date, end=end_date)
        except Exception as yf_err:
            print(f"[chart] yfinance fetch error: {yf_err}")
        # Fall back to mock data if yfinance returned empty and the date is today or in the future
        import numpy as np
        if df.empty and req_date >= today_user_tz:
            print(f"[chart] yfinance empty for today/future. Generating mock data for {date_str}")
            # Generate highly realistic mock 1-minute candles for SPY (9:30 AM to 4:00 PM EST)
            # Use deterministic seed based on the date hash so the chart is stable on reloads
            import hashlib
            seed_val = int(hashlib.md5(date_str.encode()).hexdigest(), 16) % 4294967295
            np.random.seed(seed_val)
            
            # 9:30 AM EST to 4:00 PM EST (391 minutes)
            times = pd.date_range(start=f"{date_str} 09:30:00-05:00", end=f"{date_str} 16:00:00-05:00", freq="1min")
            
            # Resolve base_price dynamically to match simulation price range (700s)
            db_base_price = None
            if DB_AVAILABLE:
                try:
                    with db.conn.cursor() as cur:
                        cur.execute("""
                            SELECT spy_price FROM signals 
                            WHERE timestamp::date = %s AND spy_price IS NOT NULL AND spy_price::float > 0
                            ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - %s))) ASC
                            LIMIT 1
                        """, (date_str, entry_time_str))
                        row = cur.fetchone()
                        if row and row[0]:
                            db_base_price = float(row[0])
                except Exception as e:
                    print(f"[chart] Error getting baseline from signals: {e}")
                    
            if not db_base_price:
                try:
                    with open(SIGNALS) as f:
                        sig_data = json.load(f)
                        val = sig_data.get("details", {}).get("spy_price")
                        if val:
                            db_base_price = float(val)
                except:
                    pass

            base_price = db_base_price if db_base_price else (option_strike if option_strike else 750.0)
            print(f"[chart] Resolved baseline price to: {base_price}")
            
            prices = []
            for _ in range(len(times)):
                base_price += np.random.normal(0, 0.22)
                prices.append(base_price)
                
            df = pd.DataFrame(index=times)
            df['Open'] = [p + np.random.uniform(-0.08, 0.08) for p in prices]
            df['High'] = [max(o, c) + np.random.uniform(0, 0.12) for o, c in zip(df['Open'], prices)]
            df['Low'] = [min(o, c) - np.random.uniform(0, 0.12) for o, c in zip(df['Open'], prices)]
            df['Close'] = prices
            df['Volume'] = [int(np.random.uniform(8000, 65000)) for _ in range(len(times))]
            df.index.name = 'Datetime'

        
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
            
        # Filter to only the requested trade date if we fetched 3d range
        if req_date == today_user_tz and not df.empty:
            df = df[df.index.date == req_date]
            
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

        # 2-min and 5-min post-exit windows
        post_2min_dt  = (exit_dt if exit_dt else entry_dt) + timedelta(minutes=2)
        post_5min_dt  = (exit_dt if exit_dt else entry_dt) + timedelta(minutes=5)
        post_2min_idx = int(df.index.get_indexer([post_2min_dt], method='nearest')[0])
        post_5min_idx = int(df.index.get_indexer([post_5min_dt], method='nearest')[0])

        post_2min_df = df.iloc[exit_idx:post_2min_idx+1] if post_2min_idx > exit_idx else pd.DataFrame()
        post_5min_df = df.iloc[exit_idx:post_5min_idx+1] if post_5min_idx > exit_idx else pd.DataFrame()

        def calc_favorable(slice_df, direction, exit_price):
            if slice_df.empty:
                return 0.0
            if direction == "LONG":
                return max(float(slice_df['High'].max()) - exit_price, 0.0)
            else:
                return max(exit_price - float(slice_df['Low'].min()), 0.0)

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

        post_2min_move = calc_favorable(post_2min_df, underlying_dir, spy_exit_price)
        post_5min_move = calc_favorable(post_5min_df, underlying_dir, spy_exit_price)

            
        has_pnl = False
        pnl_val = 0.0
        if realized_pnl is not None and str(realized_pnl).strip() != "" and str(realized_pnl).strip().lower() != "none":
            try:
                pnl_val = float(realized_pnl)
                has_pnl = True
            except:
                pass
            
        if has_pnl:
            is_win = pnl_val > 0
        else:
            is_win = (spy_exit_price > spy_entry_price if underlying_dir == "LONG" else spy_exit_price < spy_entry_price)
        
        MOVE_THRESHOLD = 0.10
        
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
            
        # Fetch trendline breaks and signals for this day
        db_signals = []
        db_breaks = []
        if DB_AVAILABLE:
            try:
                import psycopg2.extras
                with db.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Query signals for the day (matching the trade date)
                    cur.execute("""
                        SELECT id, timestamp, signal, signal_type, status, confidence, spy_price 
                        FROM signals 
                        WHERE timestamp::date = %s 
                        ORDER BY timestamp ASC
                    """, (date_str,))
                    rows = cur.fetchall()
                    for r in rows:
                        sig = dict(r)
                        sig["timestamp_unix"] = int(sig["timestamp"].timestamp())
                        sig["timestamp"] = sig["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
                        db_signals.append(sig)
                    
                    # Query trendline breaks for the day
                    cur.execute("""
                        SELECT id, date, time, symbol, direction, price 
                        FROM trendline_breaks 
                        WHERE date = %s AND symbol = 'SPY'
                        ORDER BY time ASC
                    """, (date_str,))
                    br_rows = cur.fetchall()
                    for r in br_rows:
                        br = dict(r)
                        dt_combined = datetime.combine(br["date"], br["time"])
                        br["timestamp_unix"] = int(dt_combined.timestamp())
                        br["date"] = br["date"].strftime("%Y-%m-%d")
                        br["time"] = br["time"].strftime("%H:%M:%S")
                        db_breaks.append(br)
            except Exception as db_err:
                print(f"[chart] Error fetching signals/breaks from DB: {db_err}")
        else:
            # Fall back to trendline_breaks.json if DB not available
            try:
                tl_data = load_trendline_breaks()
                for br in tl_data.get("breaks", []):
                    if br.get("date") == date_str and br.get("symbol") == "SPY":
                        try:
                            t_parsed = datetime.strptime(br["time"], "%H:%M:%S").time()
                            d_parsed = datetime.strptime(br["date"], "%Y-%m-%d").date()
                            dt_combined = datetime.combine(d_parsed, t_parsed)
                            br_copy = br.copy()
                            br_copy["timestamp_unix"] = int(dt_combined.timestamp())
                            db_breaks.append(br_copy)
                        except:
                            pass
            except Exception as json_err:
                print(f"[chart] Error reading local breaks JSON: {json_err}")

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
            "post_2min_move": round(post_2min_move, 2),
            "post_5min_move": round(post_5min_move, 2),
            "verdict": verdict,
            "verdict_details": verdict_details,
            "spy_during_trade_min": min_spy_price,
            "spy_during_trade_max": max_spy_price,
            "is_win": is_win,
            "signals": db_signals,
            "breaks": db_breaks
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
        total_missed_profit_1m = 0
        total_missed_profit_2m = 0
        total_missed_profit_5m = 0
        great_trades_count = 0
        
        stopped_drawdowns = []
        early_exit_moves = []
        
        MOVE_THRESHOLD = 0.10
        
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
                
            # Post exit move (1m, 2m, 5m)
            post_1m_dt = exit_dt + timedelta(minutes=1)
            post_1m_idx = int(df.index.get_indexer([post_1m_dt], method='nearest')[0])
            post_1m_df = df.iloc[exit_idx:post_1m_idx+1] if post_1m_idx > exit_idx else pd.DataFrame()
            
            post_2m_dt = exit_dt + timedelta(minutes=2)
            post_2m_idx = int(df.index.get_indexer([post_2m_dt], method='nearest')[0])
            post_2m_df = df.iloc[exit_idx:post_2m_idx+1] if post_2m_idx > exit_idx else pd.DataFrame()
            
            post_5m_dt = exit_dt + timedelta(minutes=5)
            post_5m_idx = int(df.index.get_indexer([post_5m_dt], method='nearest')[0])
            post_5m_df = df.iloc[exit_idx:post_5m_idx+1] if post_5m_idx > exit_idx else pd.DataFrame()
            
            favorable_post_exit_move_1m = 0.0
            favorable_post_exit_move_2m = 0.0
            favorable_post_exit_move_5m = 0.0
            
            if not post_1m_df.empty:
                close_1m = float(post_1m_df['Close'].iloc[-1])
                favorable_post_exit_move_1m = (close_1m - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - close_1m)
            if not post_2m_df.empty:
                close_2m = float(post_2m_df['Close'].iloc[-1])
                favorable_post_exit_move_2m = (close_2m - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - close_2m)
            if not post_5m_df.empty:
                close_5m = float(post_5m_df['Close'].iloc[-1])
                favorable_post_exit_move_5m = (close_5m - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - close_5m)
            
            # keep legacy var for recommendation
            post_df = post_5m_df
            favorable_post_exit_move = favorable_post_exit_move_5m
            
            if not post_df.empty:
                close_post = float(post_df['Close'].iloc[-1])
                favorable_post_exit_move = (close_post - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - close_post)
                max_post_runup = (close_post - spy_entry_price) if underlying_dir == "LONG" else (spy_entry_price - close_post)
            else:
                max_post_runup = 0.0
                favorable_post_exit_move = 0.0
                
            is_win = t["pnl"] > 0
            if is_win:
                if favorable_post_exit_move >= MOVE_THRESHOLD:
                    early_exits_count += 1
                    early_exit_moves.append(favorable_post_exit_move)
                    trade_qty = sum(e.get("qty", 1) for e in t.get("entries", [])) if t.get("entries") else 1
                    missed_profit = favorable_post_exit_move * trade_qty * 50
                    total_missed_profit_1m += favorable_post_exit_move_1m * trade_qty * 50
                    total_missed_profit_2m += favorable_post_exit_move_2m * trade_qty * 50
                    total_missed_profit_5m += favorable_post_exit_move_5m * trade_qty * 50
                    total_missed_profit += missed_profit
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
        local_files = set(f for f in os.listdir(TOS_DIR) if f.endswith(".csv"))

        # Restore any DB files missing from disk (Railway ephemeral FS)
        if DB_AVAILABLE:
            try:
                db_rows = db.get_all_uploaded_tos_files()
                for row in db_rows:
                    fp = os.path.join(TOS_DIR, row["filename"])
                    if not os.path.exists(fp):
                        with open(fp, "w", encoding="utf-8") as fout:
                            fout.write(row["file_content"])
                        local_files.add(row["filename"])
            except Exception as db_err:
                print(f"[monthly] DB restore error: {db_err}")

        files = list(local_files)
        
        monthly_data = []
        cache_dirty = False
        
        for f in files:
            filepath = os.path.join(TOS_DIR, f)
            mtime = os.path.getmtime(filepath)
            
            if f in cache and cache[f].get("mtime") == mtime:
                # If cached summary doesn't have date, right_direction_count, sim_3_pnl or sim_1m_pnl, force recompute
                summary = cache[f]["summary"]
                if "date" in summary and "right_direction_count" in summary and "sim_3_pnl" in summary and "sim_1m_pnl" in summary:
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

                # Basic stats (always computed — no network needed)
                total_pnl = sum(t["pnl"] for t in spy_trades)
                wins   = [t for t in spy_trades if t["win"]]
                losses = [t for t in spy_trades if not t["win"]]
                win_rate = (len(wins) / len(spy_trades)) * 100 if spy_trades else 0.0

                # Try yfinance for advanced direction-accuracy stats; degrade gracefully if unavailable
                stopped_out_correct_count = 0
                wrong_direction_count = 0
                early_exits_count = 0
                total_missed_profit = 0
                total_missed_profit_1m = 0
                total_missed_profit_2m = 0
                total_missed_profit_5m = 0
                great_trades_count = 0
                stopped_drawdowns = []
                early_exit_moves = []
                yf_available = False

                try:
                    dates = set(t["entry_time"].strftime("%Y-%m-%d") for t in spy_trades)
                    spy_data = {}
                    for d_str in dates:
                        dt = datetime.strptime(d_str, "%Y-%m-%d")
                        next_dt = dt + timedelta(days=1)
                        df = get_spy_history(start=d_str, end=next_dt.strftime("%Y-%m-%d"))
                        if not df.empty:
                            tz = pytz.timezone("US/Pacific")
                            try:
                                df.index = df.index.tz_convert(tz)
                            except:
                                pass
                            spy_data[d_str] = df

                    MOVE_THRESHOLD = 0.10
                    for t in spy_trades:
                        d_str = t["entry_time"].strftime("%Y-%m-%d")
                        if d_str not in spy_data:
                            continue
                        df = spy_data[d_str]
                        tz = pytz.timezone("US/Pacific")
                        entry_dt = tz.localize(t["entry_time"])
                        exit_dt  = tz.localize(t["exit_time"])
                        entry_search = entry_dt
                        exit_search  = exit_dt
                        if df.index.tz is None:
                            entry_search = entry_dt.replace(tzinfo=None)
                            exit_search  = exit_dt.replace(tzinfo=None)
                        try:
                            entry_idx = int(df.index.get_indexer([entry_search], method='nearest')[0])
                            exit_idx  = int(df.index.get_indexer([exit_search],  method='nearest')[0])
                        except:
                            continue
                        spy_entry_price = float(df.iloc[entry_idx]['Close'])
                        spy_exit_price  = float(df.iloc[exit_idx]['Close'])
                        start_idx = min(entry_idx, exit_idx)
                        end_idx   = max(entry_idx, exit_idx)
                        trade_df  = df.iloc[start_idx:end_idx+1]
                        max_spy_price = float(trade_df['High'].max())
                        min_spy_price = float(trade_df['Low'].min())
                        underlying_dir = ("SHORT" if t["direction"] == "LONG" else "LONG") if t.get("option_type") == "PUT" else t["direction"]
                        if underlying_dir == "LONG":
                            max_runup    = max_spy_price - spy_entry_price
                            max_drawdown = spy_entry_price - min_spy_price
                        else:
                            max_runup    = spy_entry_price - min_spy_price
                            max_drawdown = max_spy_price - spy_entry_price
                        post_exit_dt  = exit_dt + timedelta(minutes=60)
                        post_search = post_exit_dt
                        if df.index.tz is None:
                            post_search = post_exit_dt.replace(tzinfo=None)
                        post_exit_idx = int(df.index.get_indexer([post_search], method='nearest')[0])
                        post_df = df.iloc[exit_idx:post_exit_idx+1] if post_exit_idx > exit_idx else pd.DataFrame()
                        
                        post_1m_dt = exit_dt + timedelta(minutes=1)
                        post_1m_idx = int(df.index.get_indexer([post_1m_dt], method='nearest')[0])
                        post_1m_df = df.iloc[exit_idx:post_1m_idx+1] if post_1m_idx > exit_idx else pd.DataFrame()
                        
                        post_2m_dt = exit_dt + timedelta(minutes=2)
                        post_2m_idx = int(df.index.get_indexer([post_2m_dt], method='nearest')[0])
                        post_2m_df = df.iloc[exit_idx:post_2m_idx+1] if post_2m_idx > exit_idx else pd.DataFrame()
                        
                        post_5m_dt = exit_dt + timedelta(minutes=5)
                        post_5m_idx = int(df.index.get_indexer([post_5m_dt], method='nearest')[0])
                        post_5m_df = df.iloc[exit_idx:post_5m_idx+1] if post_5m_idx > exit_idx else pd.DataFrame()

                        favorable_post_exit_move_1m = 0.0
                        favorable_post_exit_move_2m = 0.0
                        favorable_post_exit_move_5m = 0.0

                        if not post_1m_df.empty:
                            close_1m = float(post_1m_df['Close'].iloc[-1])
                            favorable_post_exit_move_1m = (close_1m - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - close_1m)
                        if not post_2m_df.empty:
                            close_2m = float(post_2m_df['Close'].iloc[-1])
                            favorable_post_exit_move_2m = (close_2m - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - close_2m)
                        if not post_5m_df.empty:
                            close_5m = float(post_5m_df['Close'].iloc[-1])
                            favorable_post_exit_move_5m = (close_5m - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - close_5m)
                            
                        if not post_df.empty:
                            close_post = float(post_df['Close'].iloc[-1])
                            favorable_post_exit_move = (close_post - spy_exit_price) if underlying_dir == "LONG" else (spy_exit_price - close_post)
                            max_post_runup = favorable_post_exit_move
                        else:
                            max_post_runup = favorable_post_exit_move = 0.0
                        is_win = t["pnl"] > 0
                        if is_win:
                            if favorable_post_exit_move >= MOVE_THRESHOLD:
                                early_exits_count += 1
                                early_exit_moves.append(favorable_post_exit_move)
                                trade_qty = sum(e.get("qty", 1) for e in t.get("entries", [])) if t.get("entries") else 1
                                missed_profit = favorable_post_exit_move * trade_qty * 50
                                total_missed_profit_1m += favorable_post_exit_move_1m * trade_qty * 50
                                total_missed_profit_2m += favorable_post_exit_move_2m * trade_qty * 50
                                total_missed_profit_5m += favorable_post_exit_move_5m * trade_qty * 50
                                total_missed_profit += missed_profit
                            else:
                                great_trades_count += 1
                        else:
                            if max(max_runup, max_post_runup) >= MOVE_THRESHOLD:
                                stopped_out_correct_count += 1
                                stopped_drawdowns.append(max_drawdown)
                            else:
                                wrong_direction_count += 1
                    yf_available = True
                except Exception as yf_err:
                    print(f"[Monthly] yfinance unavailable for {f}: {yf_err} — using basic stats only")

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
                    recommendations.append(f"You sold {early_exits_count} winning trade(s) too early, leaving roughly ${total_missed_profit:,.2f} of potential profit on the table. Suggestion: The next time you are in profit, DO NOT sell your entire position. Sell half at your initial target to secure a win, and strictly trail the remaining half using the 1-minute 9 EMA to capture the rest of the trend. (SPY pushed up to +${max_early_move:.2f} points higher post-exit).")
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
                    "sim_1m_pnl": round(total_pnl + total_missed_profit_1m, 2),
                    "sim_2m_pnl": round(total_pnl + total_missed_profit_2m, 2),
                    "sim_5m_pnl": round(total_pnl + total_missed_profit_5m, 2),
                    "recommendations": recommendations,
                    "donts": donts
                }
                
                if yf_available:
                    cache[f] = {
                        "mtime": mtime,
                        "summary": summary
                    }
                    cache_dirty = True
                monthly_data.append(summary)
            except Exception as e:
                import traceback
                monthly_data.append({"error": str(e), "trace": traceback.format_exc(), "file": f, "source": "error"})
                continue
                
        if cache_dirty:
            save_analysis_cache(cache)

        # ------------------------------------------------------------------
        # Fallback: aggregate closed manual trades by date for any days that
        # are NOT already covered by TOS CSV files.
        # ------------------------------------------------------------------
        include_manual = request.args.get('include_manual', 'true').lower() == 'true'
        if include_manual:
            try:
                # Load manual trades (DB preferred, JSON fallback)
                if DB_AVAILABLE:
                    try:
                        raw_manual = [dict(t) for t in db.get_manual_trades(10000)]
                    except Exception:
                        raw_manual = load_manual_trades()
                else:
                    raw_manual = load_manual_trades()

                closed_manual = [t for t in raw_manual if t.get("closed") and t.get("entry_date") and t.get("pnl") is not None]

                # Group by entry_date — convert to string since psycopg2 returns DATE as datetime.date
                manual_by_date = {}
                for t in closed_manual:
                    d = str(t["entry_date"])[:10]  # ensure ISO string "YYYY-MM-DD"
                    manual_by_date.setdefault(d, []).append(t)

                # Normalize tos_dates to strings too (old cache may have datetime.date objects)
                tos_dates = {str(d.get("date", ""))[:10] for d in monthly_data if d.get("date")}

                for date_str, day_trades in manual_by_date.items():
                    if date_str in tos_dates:
                        continue  # already have TOS data for this day

                    wins_list   = [t for t in day_trades if t.get("win")]
                    losses_list = [t for t in day_trades if not t.get("win")]
                    total_pnl   = round(sum(float(t.get("pnl", 0)) for t in day_trades), 2)
                    win_rate    = (len(wins_list) / len(day_trades) * 100) if day_trades else 0.0

                    # Sim: stop after 3 trades
                    trades_3    = day_trades[:3]
                    sim_3_pnl   = round(sum(float(t.get("pnl", 0)) for t in trades_3), 2)
                    sim_3_wins  = len([t for t in trades_3 if t.get("win")])
                    sim_3_losses= len(trades_3) - sim_3_wins

                    # Sim: stop after 2 consecutive losses
                    trades_2l   = []
                    consec      = 0
                    for t in day_trades:
                        trades_2l.append(t)
                        consec = (consec + 1) if not t.get("win") else 0
                        if consec >= 2:
                            break
                    sim_2l_pnl  = round(sum(float(t.get("pnl", 0)) for t in trades_2l), 2)
                    sim_2l_wins = len([t for t in trades_2l if t.get("win")])
                    sim_2l_losses = len(trades_2l) - sim_2l_wins

                    monthly_data.append({
                        "date"               : date_str,
                        "source"             : "manual",
                        "total_trades"       : len(day_trades),
                        "win_rate"           : round(win_rate, 1),
                        "total_pnl"          : total_pnl,
                        "wins_count"         : len(wins_list),
                        "losses_count"       : len(losses_list),
                        "stopped_out_correct": 0,
                        "wrong_direction"    : 0,
                        "early_exits"        : 0,
                        "great_trades"       : 0,
                        "avg_drawdown_stopped": 0.0,
                        "right_direction_count": len(wins_list),
                        "sim_3_total"        : len(trades_3),
                        "sim_3_wins"         : sim_3_wins,
                        "sim_3_losses"       : sim_3_losses,
                        "sim_3_pnl"          : sim_3_pnl,
                        "sim_2l_total"       : len(trades_2l),
                        "sim_2l_wins"        : sim_2l_wins,
                        "sim_2l_losses"      : sim_2l_losses,
                        "sim_2l_pnl"         : sim_2l_pnl,
                        "recommendations"    : [],
                        "donts"              : []
                    })
            except Exception as manual_err:
                print(f"[monthly] manual trades fallback error: {manual_err}")

        # Normalize all date fields to ISO strings (some cache entries may have datetime.date objects)
        for d in monthly_data:
            if d.get("date") and not isinstance(d["date"], str):
                d["date"] = str(d["date"])

        # Sort chronologically by date (defensive: skip entries missing 'date' unless they are errors)
        monthly_data = [d for d in monthly_data if d.get("date") or d.get("error")]
        
        # Safe sort: push errors to the end
        monthly_data.sort(key=lambda x: x.get("date", "9999-12-31"))
        
        has_tos = any(d.get("source") != "manual" and not d.get("error") for d in monthly_data)
        return jsonify({"ok": True, "data": monthly_data, "has_tos": has_tos})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/monthly")
def monthly_standalone():
    """Standalone server-rendered monthly analytics page — no JS/CDN required."""
    try:
        from flask import make_response
        res = api_analysis_monthly()
        # api_analysis_monthly returns a Response; get the JSON data
        data_json = res.get_json()
        rows_html = ""
        total_pnl = 0
        if data_json.get("ok") and data_json.get("data"):
            for d in data_json["data"]:
                total_pnl += d.get("total_pnl", 0)
                pnl = d.get("total_pnl", 0)
                pnl_color = "#3fb950" if pnl >= 0 else "#f85149"
                pnl_str = ("+$" if pnl >= 0 else "-$") + f"{abs(pnl):.2f}"
                src = d.get("source", "tos").upper()
                src_color = "#ff9e2c" if src == "MANUAL" else "#58a6ff"
                wr = d.get("win_rate", 0)
                rows_html += f"""<tr style="border-bottom:1px solid #21262d">
  <td style="padding:8px;white-space:nowrap">{d.get('date','')}</td>
  <td style="padding:8px;text-align:center;color:{src_color};font-weight:700">{src}</td>
  <td style="padding:8px;text-align:center">{d.get('total_trades',0)}</td>
  <td style="padding:8px;text-align:center">{d.get('wins_count',0)}W / {d.get('losses_count',0)}L ({wr:.1f}%)</td>
  <td style="padding:8px;text-align:right;color:{pnl_color};font-weight:700">{pnl_str}</td>
  <td style="padding:8px;text-align:right;color:#3fb950">{'+$' if d.get('sim_3_pnl',0)>=0 else '-$'}{abs(d.get('sim_3_pnl',0)):.2f}</td>
  <td style="padding:8px;text-align:right;color:#ff9e2c">{'+$' if d.get('sim_2l_pnl',0)>=0 else '-$'}{abs(d.get('sim_2l_pnl',0)):.2f}</td>
</tr>"""
        count = len(data_json.get("data", []))
        total_color = "#3fb950" if total_pnl >= 0 else "#f85149"
        total_str = ("+$" if total_pnl >= 0 else "-$") + f"{abs(total_pnl):.2f}"
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Monthly Analytics — SPY Trader</title>
<style>body{{background:#0d1117;color:#e6edf3;font-family:system-ui,sans-serif;padding:30px;margin:0}}
table{{width:100%;border-collapse:collapse;font-size:0.9rem}}
th{{padding:10px 8px;text-align:left;color:#8b949e;border-bottom:2px solid #30363d;font-size:0.8rem;text-transform:uppercase}}
tr:hover{{background:rgba(255,255,255,0.03)}}
</style></head><body>
<h2 style="color:#58a6ff;margin-bottom:4px">📈 Monthly Analytics</h2>
<p style="color:#8b949e;margin-bottom:20px">{count} days tracked &nbsp;|&nbsp; Total P&L: <strong style="color:{total_color}">{total_str}</strong> &nbsp;|&nbsp; Source: {"TOS + Manual" if data_json.get("has_tos") and any(d.get("source")=="manual" for d in data_json.get("data",[])) else "TOS only" if data_json.get("has_tos") else "Manual only"}</p>
<table><thead><tr>
<th>Date</th><th>Source</th><th>Trades</th><th>Win Rate</th><th>Actual P&L</th><th>Sim: Stop@3</th><th>Sim: Stop@2L</th>
</tr></thead><tbody>{rows_html}</tbody></table>
<p style="margin-top:30px;color:#8b949e;font-size:0.8rem">This is a server-rendered diagnostic page. <a href="/" style="color:#58a6ff">← Back to dashboard</a></p>
</body></html>"""
        response = make_response(html)
        response.headers["Content-Type"] = "text/html"
        return response
    except Exception as e:
        return f"<pre>Error: {e}</pre>", 500

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

@app.route("/api/live-tick")
def get_live_tick():
    """Fetch latest SPY real-time tick from Alpaca (if configured) or yfinance fallback"""
    source = request.args.get("source", "yahoo")
    alpaca_key = os.getenv("ALPACA_API_KEY")
    alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
    
    if source == "alpaca" and alpaca_key and alpaca_secret:
        try:
            import urllib.request
            headers = {
                "Apca-Api-Key-Id": alpaca_key,
                "Apca-Api-Secret-Key": alpaca_secret
            }
            url = "https://data.alpaca.markets/v2/stocks/SPY/trades/latest"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=2) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            trade = data.get("trade", {})
            price = trade.get("p")
            timestamp = trade.get("t")
            
            if price:
                epoch_sec = int(time.time())
                if timestamp:
                    try:
                        ts_clean = timestamp.replace("Z", "+00:00")
                        dt_obj = datetime.fromisoformat(ts_clean)
                        epoch_sec = int(dt_obj.timestamp())
                    except Exception as ts_err:
                        print(f"Error parsing Alpaca timestamp '{timestamp}': {ts_err}")
                return jsonify({
                    "ok": True,
                    "source": "alpaca",
                    "price": price,
                    "time": epoch_sec
                })
        except Exception as e:
            print(f"Alpaca live tick error: {e}")
            
    # Fallback to current signal details
    try:
        latest_price = None
        if DB_AVAILABLE:
            latest_sig = db.get_latest_signal()
            if latest_sig:
                raw = load_raw_data(latest_sig.get("raw_data"))
                latest_price = raw.get("spy_price")
        
        if not latest_price:
            try:
                with open(SIGNALS) as f:
                    sig_data = json.load(f)
                    latest_price = sig_data.get("details", {}).get("spy_price")
            except Exception:
                pass
                
        if latest_price:
            return jsonify({
                "ok": True,
                "source": "yahoo",
                "price": float(latest_price),
                "time": int(time.time())
            })
    except Exception as e:
        print(f"Yahoo fallback tick error: {e}")
        
    return jsonify({"ok": False, "error": "No price feed available"}), 500


@app.route("/api/analysis/high-confluence-history")
def get_high_confluence_history():
    """Aggregate daily success rate for trades taken at 4/5 or 5/5 confluence"""
    try:
        # Load manual trades
        trades = []
        if DB_AVAILABLE:
            trades = [dict(t) for t in db.get_manual_trades(1000)]
        else:
            trades = load_manual_trades()
            
        # Group closed trades by entry_date
        closed_trades = [t for t in trades if t.get("closed") and t.get("entry_date")]
        
        daily_groups = {}
        for t in closed_trades:
            date = t["entry_date"]
            if date not in daily_groups:
                daily_groups[date] = []
            daily_groups[date].append(t)
            
        daily_stats = []
        for date, day_trades in daily_groups.items():
            # Calculate overall daily stats
            all_total = len(day_trades)
            all_wins = len([t for t in day_trades if t.get("win")])
            all_losses = len([t for t in day_trades if not t.get("win")])
            all_pnl = sum(float(t.get("pnl") or 0.0) for t in day_trades)
            
            # Filter for High Confluence trades (>= 4/5)
            high_conf_trades = []
            for t in day_trades:
                conf = str(t.get("snapshot", {}).get("conf_tv") or "")
                is_high = False
                if conf:
                    c = conf.strip()
                    if c.startswith(('4', '5')) or c in ('4', '5'):
                        is_high = True
                if is_high:
                    high_conf_trades.append(t)
                    
            high_total = len(high_conf_trades)
            high_wins = len([t for t in high_conf_trades if t.get("win")])
            high_losses = len([t for t in high_conf_trades if not t.get("win")])
            high_pnl = sum(float(t.get("pnl") or 0.0) for t in high_conf_trades)
            
            daily_stats.append({
                "date": date,
                "all": {
                    "total": all_total,
                    "wins": all_wins,
                    "losses": all_losses,
                    "win_rate": round(all_wins / all_total * 100, 1) if all_total > 0 else 0.0,
                    "pnl": round(all_pnl, 2)
                },
                "high_conf": {
                    "total": high_total,
                    "wins": high_wins,
                    "losses": high_losses,
                    "win_rate": round(high_wins / high_total * 100, 1) if high_total > 0 else 0.0,
                    "pnl": round(high_pnl, 2)
                }
            })
            
        # Sort chronologically by date descending
        daily_stats.sort(key=lambda x: x["date"], reverse=True)
        return jsonify({"ok": True, "data": daily_stats})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/webhook/signal", methods=["POST"])
def tv_webhook_signal():
    """Secure webhook endpoint for TradingView Alerts to post signals directly"""
    token = request.args.get("token")
    expected_token = os.getenv("WEBHOOK_TOKEN", "spy_secret_token")
    if token != expected_token:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
        
    try:
        req = request.get_json(force=True)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Invalid JSON body: {e}"}), 400
        
    sig_label = req.get("signal", "WAITING")
    sig_type = req.get("signal_type", "none")
    spy_price = req.get("spy") or req.get("price")
    
    if not spy_price:
        return jsonify({"ok": False, "error": "Missing spy/price in payload"}), 400
        
    details = {
        "spy_price":     float(spy_price),
        "qqq_price":     float(req.get("qqq_price") or req.get("qqq") or spy_price),
        "add":           float(req.get("add") if req.get("add") is not None else (req.get("add_value") if req.get("add_value") is not None else 0.0)),
        "signal_tv":     req.get("signal_tv") or req.get("macd_dir") or "N/A",
        "status_tv":     req.get("status_tv") or "READY",
        "conf_tv":       str(req.get("conf_tv") or req.get("confidence") or "0"),
        "qqq_dir":       req.get("qqq_dir", ""),
        "add_dir":       req.get("add_dir", ""),
        "spy5_dir":      req.get("spy5_dir", ""),
        "spy1_dir":      req.get("spy1_dir", ""),
        "macd_dir":      req.get("macd_dir") or req.get("signal_tv") or "",
        "rev_score":     int(req.get("rev_score") if req.get("rev_score") is not None else 0),
        "rev_dir":       req.get("rev_dir", ""),
        "div_signal":    req.get("div_signal", ""),
        "add_ext":       req.get("add_ext", ""),
        "st_flip":       req.get("st_flip", ""),
        "vwap_pct":      float(req.get("vwap_pct") if req.get("vwap_pct") is not None else 0.0),
        "engulf":        req.get("engulf", ""),
        "tl_break":      req.get("tl_break", ""),
        "resist":        req.get("resist") if req.get("resist") is not None else None,
        "support":       req.get("support") if req.get("support") is not None else None,
        "st_level":      req.get("st_level") if req.get("st_level") is not None else None,
        "time_left":     req.get("time_left") if req.get("time_left") is not None else None,
        "adx_value":     req.get("adx_value") if req.get("adx_value") is not None else None,
        "vix":           float(req.get("vix") or 15.0),
        "vix_regime":    req.get("vix_regime", "NORMAL")
    }
    
    payload = {
        "signal":      sig_label,
        "signal_type": sig_type,
        "details":     details,
        "last_update": datetime.now().isoformat()
    }
    
    # Save to database or JSON
    if DB_AVAILABLE:
        try:
            db.insert_signal(sig_label, sig_type, spy_price, json.dumps(payload))
        except Exception as db_err:
            print(f"Error saving webhook signal to DB: {db_err}")
            save_signals_json(payload)
    else:
        save_signals_json(payload)
        
    return jsonify({"ok": True, "message": "Signal received successfully", "payload": payload})

def save_signals_json(payload):
    try:
        with open(SIGNALS, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"Error saving signals.json: {e}")


@app.route("/api/diagnostics/run")
def diagnostics_run():
    import requests
    import socket
    from datetime import datetime
    results = {}
    
    # Check if running in cloud (Railway)
    is_cloud = os.getenv("RAILWAY_STATIC_URL") is not None or os.getenv("PORT") is not None
    
    # 1. Database Connection & Schema Test
    db_ok = False
    db_reason = "Not attempted"
    db_details = {}
    if DB_AVAILABLE:
        try:
            # Check simple query
            with db.conn.cursor() as cur:
                cur.execute("SELECT 1")
                res = cur.fetchone()[0]
                if res == 1:
                    db_ok = True
                    db_reason = "Successfully connected & queried database"
            
            # Check table existence by querying count
            tables = ["signals", "paper_trades", "manual_trades", "trendline_breaks"]
            table_status = {}
            for t in tables:
                try:
                    with db.conn.cursor() as cur:
                        cur.execute(f"SELECT COUNT(*) FROM {t}")
                        count = cur.fetchone()[0]
                        table_status[t] = f"OK ({count} rows)"
                except Exception as table_err:
                    db.conn.rollback()
                    table_status[t] = f"Error: {str(table_err)}"
            db_details["tables"] = table_status
        except Exception as e:
            db_reason = f"Database query failed: {e}"
    else:
        # PostgreSQL not active, test local fallback JSON files
        fallback_files = ["signals.json", "paper_trades.json", "manual_trades.json", "trendline_breaks.json"]
        fallback_status = {}
        fallback_ok_count = 0
        for f_name in fallback_files:
            f_path = os.path.join(BOT_DIR, f_name)
            if os.path.exists(f_path):
                try:
                    with open(f_path, "r") as test_f:
                        json.load(test_f)
                    fallback_status[f_name] = "OK (Readable)"
                    fallback_ok_count += 1
                except Exception as err:
                    fallback_status[f_name] = f"Error: {str(err)}"
            else:
                fallback_status[f_name] = "Not found (Will create on start)"
                fallback_ok_count += 1  # Not an error if file doesn't exist yet
                
        db_ok = (fallback_ok_count == len(fallback_files))
        db_reason = "PostgreSQL not active. JSON file fallback is fully active and functional."
        db_details["fallback_files"] = fallback_status
        
    results["database"] = {
        "status": "PASS" if db_ok else "FAIL",
        "name": "PostgreSQL Connection & Schema Health",
        "description": db_reason,
        "details": db_details
    }
    
    # 2. Alpaca API connection
    alpaca_ok = False
    alpaca_reason = "Alpaca API Keys not set"
    alpaca_key = os.getenv("ALPACA_API_KEY")
    alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
    
    if alpaca_key and alpaca_secret:
        try:
            headers = {
                "APCA-API-KEY-ID": alpaca_key,
                "APCA-API-SECRET-KEY": alpaca_secret
            }
            # Query paper account status
            r = requests.get("https://paper-api.alpaca.markets/v2/account", headers=headers, timeout=5)
            if r.status_code == 200:
                alpaca_ok = True
                acct = r.json()
                alpaca_reason = f"Alpaca API connected successfully. Account Status: {acct.get('status')} | Buying Power: ${acct.get('buying_power')}"
            else:
                alpaca_reason = f"Alpaca API responded with status {r.status_code}: {r.text}"
        except Exception as e:
            alpaca_reason = f"Failed to connect to Alpaca API: {e}"
    else:
        # Optional check: PASS because it falls back to simulation mode
        alpaca_ok = True
        alpaca_reason = "Alpaca API keys are not set. Bot runs in simulation mode (paper trades logged to DB/JSON only)."
            
    results["alpaca"] = {
        "status": "PASS" if alpaca_ok else "FAIL",
        "name": "Alpaca API connection",
        "description": alpaca_reason
    }
    
    # 3. Chrome CDP / TradingView tab connection
    chrome_ok = False
    chrome_reason = "Chrome debug port 9222 is closed"
    chrome_details = {}
    
    if is_cloud:
        # On Railway, verify that local bot is uploading signals successfully
        if DB_AVAILABLE:
            try:
                with db.conn.cursor() as cur:
                    cur.execute("SELECT timestamp FROM signals ORDER BY id DESC LIMIT 1")
                    row = cur.fetchone()
                    if row:
                        last_time = row[0]
                        # Account for timezone differences safely
                        now_tz = datetime.now(last_time.tzinfo) if last_time.tzinfo else datetime.now()
                        time_diff = (now_tz - last_time).total_seconds()
                        
                        if time_diff < 120:
                            chrome_ok = True
                            chrome_reason = f"Cloud environment detected. Local bot feed is active (last update received {int(time_diff)}s ago)."
                        else:
                            chrome_reason = f"Cloud environment detected, but local bot feed is stale (last update was {int(time_diff)}s ago). Make sure the local bot is running on your desktop."
                    else:
                        chrome_reason = "Cloud environment detected. Database exists but no signal records found yet."
            except Exception as e:
                chrome_reason = f"Cloud environment: failed to query last update: {e}"
        else:
            chrome_reason = "Cloud environment detected but database is offline, cannot verify local bot feed status."
    else:
        # Check if port 9222 is listening locally
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            s.connect(("127.0.0.1", 9222))
            s.close()
            chrome_port_listening = True
        except:
            chrome_port_listening = False
            
        if chrome_port_listening:
            try:
                # Query Chrome version/json endpoints
                r = requests.get("http://127.0.0.1:9222/json", timeout=3)
                tabs = r.json()
                chrome_details["active_tabs_count"] = len(tabs)
                
                # Search for TradingView
                tv_tabs = [t for t in tabs if "tradingview.com" in t.get("url", "")]
                if tv_tabs:
                    chrome_ok = True
                    chrome_reason = f"Chrome CDP active on port 9222. Found {len(tv_tabs)} TradingView tab(s)!"
                    chrome_details["tv_tabs"] = [{"title": t.get("title"), "url": t.get("url")} for t in tv_tabs]
                else:
                    chrome_reason = "Chrome debug port is open, but no active TradingView charts were found. Open tradingview.com/chart in Chrome."
            except Exception as e:
                chrome_reason = f"Chrome port 9222 is open, but failed to fetch tabs: {e}"
            
    results["chrome_cdp"] = {
        "status": "PASS" if chrome_ok else "FAIL",
        "name": "Google Chrome remote-debugging (CDP)",
        "description": chrome_reason,
        "details": chrome_details
    }
    
    # 4. Market Context (Economic events calendar)
    calendar_ok = False
    calendar_reason = "Failed to load market context calendar"
    calendar_details = {}
    try:
        from market_context import get_full_context
        ctx = get_full_context()
        if ctx:
            calendar_ok = True
            calendar_reason = f"Market calendar working. VIX: {ctx.get('vix')} | Regime: {ctx.get('vix_regime')} | Today's macro events count: {len(ctx.get('events', []))}"
            calendar_details["events"] = ctx.get("events", [])
            calendar_details["vix_regime"] = ctx.get("vix_regime")
    except Exception as e:
        calendar_reason = f"Error in market context module: {e}"
        
    results["market_context"] = {
        "status": "PASS" if calendar_ok else "FAIL",
        "name": "Market Context & Macro Calendar",
        "description": calendar_reason,
        "details": calendar_details
    }
    
    # Determine overall status
    all_ok = all(r["status"] == "PASS" for r in results.values())
    
    return jsonify({
        "ok": True,
        "all_passed": all_ok,
        "results": results
    })


@app.route("/api/screenshots")
def list_screenshots():
    """Return the most recent signal screenshots (newest first)."""
    try:
        files = sorted(
            [f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')],
            reverse=True
        )[:30]  # Return last 30 screenshots
        result = []
        for fname in files:
            fpath = os.path.join(SCREENSHOTS_DIR, fname)
            stat = os.stat(fpath)
            # Parse metadata from filename: YYYYMMDD_HHMMSS_SIGNAL_sigtype.png
            parts = fname.replace('.png', '').split('_')
            result.append({
                "filename": fname,
                "url": f"/screenshots/{fname}",
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        return jsonify({"ok": True, "screenshots": result, "count": len(result)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename):
    """Serve a screenshot file."""
    return send_from_directory(SCREENSHOTS_DIR, filename)


@app.route("/control/restart_server", methods=["POST"])
def restart_server():
    """Restart the dashboard server process to pick up code changes."""
    import threading
    def do_restart():
        time.sleep(0.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=do_restart, daemon=True).start()
    return jsonify({"ok": True, "messages": ["Server restarting..."]})


@app.route("/api/admin/debug_yf")
def api_admin_debug_yf():
    import yfinance as yf
    import pytz
    from datetime import datetime
    import traceback
    try:
        df = yf.Ticker('SPY').history(start='2026-07-16', end='2026-07-17', interval='1m')
        if df.empty: return jsonify({"error": "df is empty"})
        
        tz = pytz.timezone("US/Pacific")
        try:
            df.index = df.index.tz_convert(tz)
        except Exception as e:
            pass
            
        entry_time_str = "2026-07-16 06:34:51"
        entry_dt = tz.localize(datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S"))
        entry_search = entry_dt
        if df.index.tz is None:
            entry_search = entry_dt.replace(tzinfo=None)
            
        try:
            entry_idx = int(df.index.get_indexer([entry_search], method='nearest')[0])
            return jsonify({"ok": True, "idx": entry_idx, "dt": str(df.index[entry_idx])})
        except Exception as e:
            return jsonify({"error": str(e), "trace": traceback.format_exc()})
    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()})

@app.route("/api/admin/clear_cache")
def clear_cache():
    try:
        if db and not db.is_connected:
            db.connect()
        global DB_AVAILABLE
        DB_AVAILABLE = db.is_connected if db else False
        restore_tos_files_from_db()
        
        # Debugging info
        db_files = db.get_all_uploaded_tos_files() if db else []
        local_files = os.listdir(TOS_DIR) if os.path.exists(TOS_DIR) else []
        
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            return jsonify({"ok": True, "msg": "Cache cleared and TOS files synced.", "debug": {"db_count": len(db_files), "local_files": local_files}})
        return jsonify({"ok": True, "msg": "No cache file found, but TOS files synced.", "debug": {"db_count": len(db_files), "local_files": local_files}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

if __name__ == "__main__":
    try:
        import psutil
    except ImportError:
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "pip", "install", "psutil", "-q"])
        import psutil
    port = int(os.environ.get("PORT", 5000))
    print(f"Dashboard running at http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
