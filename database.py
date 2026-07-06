"""
PostgreSQL Database Module for SPY Trader
Handles all database operations for signals, trades, trendline breaks
"""
import os
import json
import logging
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except:
    pass

load_dotenv()

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")

# Log file for control output
LOG_FILE = os.path.join(os.path.dirname(__file__), "database_log.txt")

def log_db_event(message, level="INFO"):
    """Log database events to both console and file"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_msg = f"[{timestamp}] [{level}] {message}"
    print(log_msg)

    # Also write to log file for dashboard to read
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")
    except:
        pass

def clean_int(val):
    if val is None:
        return 0
    val_str = str(val).strip()
    if "/" in val_str:
        val_str = val_str.split("/")[0]
    try:
        return int(val_str)
    except:
        return 0


class Database:
    def __init__(self):
        self.conn = None
        self.is_connected = False

    def connect(self):
        """Establish database connection"""
        try:
            log_db_event("Attempting to connect to PostgreSQL...")
            if not DATABASE_URL:
                log_db_event("❌ DATABASE_URL not set in environment", "ERROR")
                self.is_connected = False
                return False

            log_db_event(f"DATABASE_URL: {DATABASE_URL[:50]}...", "DEBUG")
            self.conn = psycopg2.connect(DATABASE_URL)
            self.conn.autocommit = True
            self.is_connected = True
            log_db_event("✓ Successfully connected to PostgreSQL database!", "SUCCESS")
            return True
        except psycopg2.OperationalError as e:
            log_db_event(f"❌ Cannot connect to database: {str(e)[:100]}", "ERROR")
            self.is_connected = False
            return False
        except Exception as e:
            log_db_event(f"❌ Database connection error: {str(e)[:100]}", "ERROR")
            self.is_connected = False
            return False

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.is_connected = False
            logger.info("Database disconnected")

    def ensure_connected(self):
        """Reconnect if connection lost or dropped by server."""
        # psycopg2: conn.closed == 0 means open, > 0 means closed
        if not self.is_connected or self.conn is None or self.conn.closed != 0:
            logger.info("DB connection lost — reconnecting...")
            self.connect()

    # ── SIGNALS TABLE ──
    def insert_signal(self, signal, signal_type, spy_price, raw_data_json):
        """Insert a signal directly (called by webhook in dashboard_server)"""
        self.ensure_connected()
        try:
            raw_data = json.loads(raw_data_json)
            details = raw_data.get("details", {})
        except:
            details = {}
            
        signal_data = {
            "signal": signal,
            "signal_type": signal_type,
            "spy_price": spy_price,
            "qqq_price": details.get("qqq_price") or details.get("qqq") or spy_price,
            "add_value": details.get("add") or details.get("add_value") or 0.0,
            "conf_tv": details.get("conf_tv") or details.get("confidence") or "0",
            "status": details.get("status_tv") or details.get("status") or "READY",
            "macd_dir": details.get("signal_tv") or details.get("macd_dir") or "",
            "rev_score": details.get("rev_score") or 0,
            "rev_dir": details.get("rev_dir") or "",
            "st_flip": details.get("st_flip") or "",
            "tl_break": details.get("tl_break") or "",
        }
        return self.save_signal(signal_data)

    def save_signal(self, signal_data):
        """Save trading signal to database"""
        self.ensure_connected()
        try:
            signal = signal_data.get("signal", "UNKNOWN")
            spy_price = signal_data.get("spy_price", "?")
            log_db_event(f"📊 Saving signal: {signal} @ SPY ${spy_price}")

            # Safely convert st_flip to boolean
            st_flip_raw = signal_data.get("st_flip")
            st_flip_bool = False
            if st_flip_raw:
                if isinstance(st_flip_raw, str):
                    st_flip_bool = "FLIPPED" in st_flip_raw.upper()
                else:
                    st_flip_bool = bool(st_flip_raw)

            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO signals
                    (signal, signal_type, status, confidence, spy_price, qqq_price,
                     add_value, macd_dir, rev_score, rev_dir, st_flip, tl_break, raw_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    signal_data.get("signal"),
                    signal_data.get("signal_type"),
                    signal_data.get("status"),
                    clean_int(signal_data.get("conf_tv")),
                    signal_data.get("spy_price"),
                    signal_data.get("qqq_price"),
                    signal_data.get("add_value"),
                    signal_data.get("macd_dir"),
                    signal_data.get("rev_score"),
                    signal_data.get("rev_dir"),
                    st_flip_bool,
                    signal_data.get("tl_break"),
                    json.dumps(signal_data.get("details", signal_data), default=str)
                ))
                signal_id = cur.fetchone()[0]
                self.conn.commit()
                log_db_event(f"✓ Signal saved to DB (ID: {signal_id})", "SUCCESS")
                return signal_id
        except Exception as e:
            self.conn.rollback()
            log_db_event(f"❌ Error saving signal: {str(e)[:80]}", "ERROR")
            return None

    def get_latest_signal(self):
        """Get most recent signal"""
        self.ensure_connected()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM signals
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                return cur.fetchone()
        except Exception as e:
            logger.error(f"Error fetching latest signal: {e}")
            return None

    def get_signal_history(self, limit=60):
        """Get signal history"""
        self.ensure_connected()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT *
                    FROM signals
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (limit,))
                return cur.fetchall() or []
        except Exception as e:
            logger.error(f"Error fetching signal history: {e}")
            return []

    # ── PAPER TRADES TABLE ──
    def save_paper_trade(self, trade_data):
        """Open new paper trade"""
        self.ensure_connected()
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO paper_trades
                    (entry_time, direction, entry_price, signal_type, conf_score, closed)
                    VALUES (%s, %s, %s, %s, %s, FALSE)
                    RETURNING id
                """, (
                    trade_data.get("entry_time") or datetime.now(),
                    trade_data.get("direction"),
                    trade_data.get("entry_price"),
                    trade_data.get("signal_type"),
                    clean_int(trade_data.get("conf_score"))
                ))
                trade_id = cur.fetchone()[0]
                self.conn.commit()
                logger.info(f"Paper trade opened (ID: {trade_id})")
                return trade_id
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error saving paper trade: {e}")
            return None

    def close_paper_trade(self, trade_id, exit_price):
        """Close paper trade and calculate P&L"""
        self.ensure_connected()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get trade details
                cur.execute("""
                    SELECT entry_price, direction FROM paper_trades
                    WHERE id = %s
                """, (trade_id,))
                trade = cur.fetchone()

                if not trade:
                    logger.warning(f"Trade {trade_id} not found")
                    return False

                # Calculate P&L
                entry = float(trade['entry_price'])
                if trade['direction'] == 'CALL':
                    pnl = round(exit_price - entry, 3)
                else:  # PUT
                    pnl = round(entry - exit_price, 3)

                pnl_pct = round(pnl / entry * 100, 3) if entry else 0

                # Update trade
                cur.execute("""
                    UPDATE paper_trades
                    SET exit_time = %s, exit_price = %s, pnl = %s,
                        pnl_percent = %s, is_win = %s, closed = TRUE
                    WHERE id = %s
                """, (datetime.now(), exit_price, pnl, pnl_pct, pnl > 0, trade_id))
                self.conn.commit()
                logger.info(f"Trade closed (ID: {trade_id}, P&L: {pnl})")
                return True
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error closing trade: {e}")
            return False

    def get_paper_trades(self, limit=100):
        """Get paper trades"""
        self.ensure_connected()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM paper_trades
                    WHERE closed = TRUE
                    ORDER BY entry_time DESC
                    LIMIT %s
                """, (limit,))
                return cur.fetchall() or []
        except Exception as e:
            logger.error(f"Error fetching paper trades: {e}")
            return []

    def get_paper_stats(self):
        """Get paper trading statistics"""
        self.ensure_connected()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN is_win THEN 1 ELSE 0 END) as wins,
                        AVG(pnl) as avg_pnl,
                        SUM(pnl) as total_pnl,
                        SUM(CASE WHEN direction = 'CALL' THEN 1 ELSE 0 END) as calls,
                        SUM(CASE WHEN direction = 'PUT' THEN 1 ELSE 0 END) as puts
                    FROM paper_trades
                    WHERE closed = TRUE
                """)
                stats = cur.fetchone()
                return stats or {
                    "total": 0, "wins": 0, "avg_pnl": 0,
                    "total_pnl": 0, "calls": 0, "puts": 0
                }
        except Exception as e:
            logger.error(f"Error fetching paper stats: {e}")
            return {}

    # ── MANUAL TRADES TABLE ──
    def save_manual_trade(self, trade_data):
        """Save manual paper trade"""
        self.ensure_connected()
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO manual_trades
                    (id, entry_date, entry_time, entry_price, direction, signal,
                     conf_score, snapshot, closed)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE)
                """, (
                    trade_data.get("id"),
                    trade_data.get("entry_date"),
                    trade_data.get("entry_time"),
                    trade_data.get("entry_price"),
                    trade_data.get("direction"),
                    trade_data.get("signal"),
                    clean_int(trade_data.get("conf_score")),
                    json.dumps(trade_data.get("snapshot", {}), default=str)
                ))
                self.conn.commit()
                logger.info(f"Manual trade saved")
                return True
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error saving manual trade: {e}")
            return False

    def close_manual_trade(self, trade_id, exit_price):
        """Close manual trade"""
        self.ensure_connected()
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT entry_price, direction FROM manual_trades
                    WHERE id = %s
                """, (trade_id,))
                trade = cur.fetchone()

                if not trade:
                    return False

                entry = float(trade[0])
                direction = trade[1]
                pnl = round(exit_price - entry, 3) if direction == "CALL" else round(entry - exit_price, 3)
                pnl_pct = round(pnl / entry * 100, 3) if entry else 0

                cur.execute("""
                    UPDATE manual_trades
                    SET exit_price = %s, pnl = %s, pnl_percent = %s,
                        is_win = %s, closed = TRUE
                    WHERE id = %s
                """, (exit_price, pnl, pnl_pct, pnl > 0, trade_id))
                self.conn.commit()
                return True
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error closing manual trade: {e}")
            return False

    def get_manual_trades(self, limit=100):
        """Get manual trades"""
        self.ensure_connected()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM manual_trades
                    ORDER BY entry_date DESC, entry_time DESC
                    LIMIT %s
                """, (limit,))
                return cur.fetchall() or []
        except Exception as e:
            logger.error(f"Error fetching manual trades: {e}")
            return []

    # ── TRENDLINE BREAKS TABLE ──
    def save_trendline_break(self, break_data):
        """Record trendline break"""
        self.ensure_connected()
        try:
            symbol = break_data.get("symbol", "SPY")
            direction = break_data.get("direction", "?")
            price = break_data.get("price", "?")
            is_manual = break_data.get("is_manual", False)
            manual_tag = "🔧 (MANUAL)" if is_manual else "🤖 (AUTO)"

            log_db_event(f"📈 Recording trendline break: {symbol} {direction} @ ${price} {manual_tag}")

            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trendline_breaks
                    (date, time, symbol, direction, price, is_manual)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    break_data.get("date"),
                    break_data.get("time"),
                    symbol,
                    direction,
                    price,
                    is_manual
                ))
                self.conn.commit()
                log_db_event(f"✓ Trendline break saved: {symbol} {direction}", "SUCCESS")
                return True
        except Exception as e:
            self.conn.rollback()
            log_db_event(f"❌ Error saving trendline break: {str(e)[:80]}", "ERROR")
            return False

    def get_trendline_breaks(self, days=1):
        """Get trendline breaks"""
        self.ensure_connected()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM trendline_breaks
                    WHERE date >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY date DESC, time DESC
                """, (days,))
                return cur.fetchall() or []
        except Exception as e:
            logger.error(f"Error fetching trendline breaks: {e}")
            return []

    def check_duplicate_break(self, symbol, direction, seconds=60):
        """Check if same break was recorded recently"""
        self.ensure_connected()
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM trendline_breaks
                    WHERE symbol = %s AND direction = %s
                    AND created_at > NOW() - INTERVAL '%s seconds'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (symbol, direction, seconds))
                return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking duplicate break: {e}")
            return False

# Global database instance
db = Database()

# Auto-connect on import
if DATABASE_URL:
    db.connect()
