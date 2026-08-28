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
            
            # Auto-create uploaded_tos_files table if not exists
            try:
                with self.conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS uploaded_tos_files (
                            filename VARCHAR(255) PRIMARY KEY,
                            file_content TEXT NOT NULL,
                            uploaded_at TIMESTAMP DEFAULT NOW()
                        );
                    """)
            except Exception as e:
                log_db_event(f"Error creating uploaded_tos_files table: {e}", "WARNING")
                
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
            "qqq_price": details.get("qqq_price") if details.get("qqq_price") is not None else (details.get("qqq") if details.get("qqq") is not None else spy_price),
            "add_value": details.get("add") if details.get("add") is not None else (details.get("add_value") if details.get("add_value") is not None else 0.0),
            "conf_tv": details.get("conf_tv") if details.get("conf_tv") is not None else (details.get("confidence") if details.get("confidence") is not None else "0"),
            "status": details.get("status_tv") if details.get("status_tv") is not None else (details.get("status") if details.get("status") is not None else "READY"),
            "macd_dir": details.get("signal_tv") if details.get("signal_tv") is not None else (details.get("macd_dir") if details.get("macd_dir") is not None else ""),
            "rev_score": details.get("rev_score") if details.get("rev_score") is not None else 0,
            "rev_dir": details.get("rev_dir") if details.get("rev_dir") is not None else "",
            "st_flip": details.get("st_flip") if details.get("st_flip") is not None else "",
            "tl_break": details.get("tl_break") if details.get("tl_break") is not None else "",
            "details": details,
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

    def get_latest_trendline_break(self):
        """Get most recent trendline break"""
        self.ensure_connected()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM trendline_breaks
                    ORDER BY date DESC, time DESC, id DESC
                    LIMIT 1
                """)
                return cur.fetchone()
        except Exception as e:
            logger.error(f"Error fetching latest trendline break: {e}")
            return None


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
    # ── UPLOADED TOS CSV FILES ──
    def save_uploaded_tos_file(self, filename, content):
        """Save a TOS CSV file to the database to persist it across restarts"""
        self.ensure_connected()
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO uploaded_tos_files (filename, file_content, uploaded_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (filename) DO UPDATE
                    SET file_content = EXCLUDED.file_content, uploaded_at = NOW()
                """, (filename, content))
                self.conn.commit()
                return True
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error saving uploaded TOS file {filename}: {e}")
            return False

    def get_all_uploaded_tos_files(self):
        """Fetch all persistent TOS CSV files from database"""
        self.ensure_connected()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT filename, file_content FROM uploaded_tos_files
                """)
                return cur.fetchall() or []
        except Exception as e:
            logger.error(f"Error fetching uploaded TOS files: {e}")
            return []

    # ── CHECKLIST TABLE ──
    def _ensure_checklist_table(self):
        """Create checklist table if it doesn't exist yet."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trade_checklist (
                        id          BIGINT PRIMARY KEY,
                        trade_date  DATE NOT NULL,
                        trade_time  VARCHAR(5),
                        timestamp   VARCHAR(40),
                        trade_type  VARCHAR(10) DEFAULT 'PUTS',
                        checks      JSONB DEFAULT '{}',
                        score       INT DEFAULT 0,
                        total       INT DEFAULT 10,
                        earned_points INT,
                        total_points  INT,
                        note        TEXT DEFAULT '',
                        comment     TEXT DEFAULT '',
                        created_at  TIMESTAMP DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_checklist_date
                        ON trade_checklist(trade_date DESC);
                """)
        except Exception as e:
            logger.error(f"Error creating trade_checklist table: {e}")

    def save_checklist_record(self, record):
        """Insert one checklist record. Returns True on success."""
        self.ensure_connected()
        self._ensure_checklist_table()
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trade_checklist
                        (id, trade_date, trade_time, timestamp, trade_type,
                         checks, score, total, earned_points, total_points,
                         note, comment)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO NOTHING
                """, (
                    record["id"],
                    record.get("date"),
                    record.get("time"),
                    record.get("timestamp"),
                    record.get("trade_type", "PUTS"),
                    json.dumps(record.get("checks", {})),
                    record.get("score", 0),
                    record.get("total", 10),
                    record.get("earned_points"),
                    record.get("total_points"),
                    record.get("note", ""),
                    record.get("comment", ""),
                ))
            return True
        except Exception as e:
            logger.error(f"Error saving checklist record: {e}")
            return False

    def get_checklist_records(self):
        """Return all checklist records as list of dicts, newest first."""
        self.ensure_connected()
        self._ensure_checklist_table()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id,
                           trade_date  AS date,
                           trade_time  AS time,
                           timestamp,
                           trade_type,
                           checks,
                           score, total,
                           earned_points, total_points,
                           note, comment
                    FROM trade_checklist
                    ORDER BY trade_date DESC, trade_time DESC
                """)
                rows = cur.fetchall() or []
                result = []
                for row in rows:
                    r = dict(row)
                    r["date"] = str(r["date"]) if r["date"] else ""
                    # checks may be a dict already (RealDictCursor + jsonb)
                    if isinstance(r.get("checks"), str):
                        try:
                            r["checks"] = json.loads(r["checks"])
                        except Exception:
                            r["checks"] = {}
                    result.append(r)
                return result
        except Exception as e:
            logger.error(f"Error fetching checklist records: {e}")
            return []

    def delete_checklist_record(self, record_id):
        """Delete one checklist record by id."""
        self.ensure_connected()
        self._ensure_checklist_table()
        try:
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM trade_checklist WHERE id = %s", (record_id,))
            return True
        except Exception as e:
            logger.error(f"Error deleting checklist record: {e}")
            return False

    def update_checklist_comment(self, record_id, comment):
        """Update the comment on a checklist record."""
        self.ensure_connected()
        self._ensure_checklist_table()
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE trade_checklist SET comment = %s WHERE id = %s",
                    (comment, record_id)
                )
            return True
        except Exception as e:
            logger.error(f"Error updating checklist comment: {e}")
            return False

    # ── ANALYSIS RECORDS TABLE ──
    def _ensure_analysis_table(self):
        """Create analysis_records table if it doesn't exist yet."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS analysis_records (
                        id          BIGINT PRIMARY KEY,
                        timestamp   VARCHAR(40),
                        image_path  TEXT,
                        analysis    TEXT,
                        created_at  TIMESTAMP DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_analysis_timestamp
                        ON analysis_records(timestamp DESC);
                """)
        except Exception as e:
            logger.error(f"Error creating analysis_records table: {e}")

    def save_analysis_record(self, record):
        """Insert an analysis record (id, timestamp, image_path, analysis)."""
        self.ensure_connected()
        self._ensure_analysis_table()
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO analysis_records (id, timestamp, image_path, analysis)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, (
                    record["id"],
                    record.get("timestamp"),
                    record.get("image_path"),
                    record.get("analysis"),
                ))
            return True
        except Exception as e:
            logger.error(f"Error saving analysis record: {e}")
            return False

    def get_analysis_records(self, limit=20):
        """Return recent analysis records, newest first, up to limit."""
        self.ensure_connected()
        self._ensure_analysis_table()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, timestamp, image_path, analysis, created_at
                    FROM analysis_records
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (limit,))
                rows = cur.fetchall() or []
                result = []
                for row in rows:
                    r = dict(row)
                    result.append(r)
                return result
        except Exception as e:
            logger.error(f"Error fetching analysis records: {e}")
            return []

    # ── CHECKLIST SUMMARY TABLE ──
    def _ensure_checklist_summary_table(self):
        """Create checklist summary table if it doesn't exist yet."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trade_checklist_summary (
                        id          BIGINT PRIMARY KEY,
                        summary_date DATE NOT NULL,
                        summary_time VARCHAR(5),
                        timestamp   VARCHAR(40),
                        summary     TEXT DEFAULT '',
                        created_at  TIMESTAMP DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_checklist_summary_date
                        ON trade_checklist_summary(summary_date DESC);
                """)
        except Exception as e:
            logger.error(f"Error creating trade_checklist_summary table: {e}")

    def save_checklist_summary(self, record):
        """Insert one checklist summary record. Returns True on success."""
        self.ensure_connected()
        self._ensure_checklist_summary_table()
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trade_checklist_summary
                        (id, summary_date, summary_time, timestamp, summary)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO NOTHING
                """, (
                    record["id"],
                    record.get("date"),
                    record.get("time"),
                    record.get("timestamp"),
                    record.get("summary", ""),
                ))
            return True
        except Exception as e:
            logger.error(f"Error saving checklist summary: {e}")
            return False

    def get_checklist_summaries(self):
        """Return all checklist summaries as list of dicts, newest first."""
        self.ensure_connected()
        self._ensure_checklist_summary_table()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id,
                           summary_date  AS date,
                           summary_time  AS time,
                           timestamp,
                           summary,
                           created_at
                    FROM trade_checklist_summary
                    ORDER BY timestamp DESC
                """)
                rows = cur.fetchall() or []
                result = []
                for row in rows:
                    r = dict(row)
                    r["date"] = str(r["date"]) if r["date"] else ""
                    result.append(r)
                return result
        except Exception as e:
            logger.error(f"Error fetching checklist summaries: {e}")
            return []


    # ── TRADE JOURNAL TABLE ──
    def _ensure_journal_table(self):
        """Create trade_journal table if it doesn't exist yet."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trade_journal (
                        date        VARCHAR(20) PRIMARY KEY,
                        content     TEXT DEFAULT '',
                        pnl         DECIMAL(10,2),
                        created_at  TIMESTAMP DEFAULT NOW(),
                        updated_at  TIMESTAMP DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_trade_journal_date
                        ON trade_journal(date DESC);
                """)
        except Exception as e:
            logger.error(f"Error creating trade_journal table: {e}")

    def save_journal_entry(self, date_str, content, pnl=None):
        """Insert or update one journal entry."""
        self.ensure_connected()
        self._ensure_journal_table()
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trade_journal (date, content, pnl, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (date) DO UPDATE
                    SET content = EXCLUDED.content,
                        pnl = COALESCE(EXCLUDED.pnl, trade_journal.pnl),
                        updated_at = NOW()
                """, (date_str, content, pnl))
            return True
        except Exception as e:
            logger.error(f"Error saving journal entry: {e}")
            return False

    def get_journal_entries(self, date_str=None):
        """Return list of journal entries, optionally filtered by date."""
        self.ensure_connected()
        self._ensure_journal_table()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                if date_str:
                    cur.execute("SELECT date, content, pnl, created_at, updated_at FROM trade_journal WHERE date = %s", (date_str,))
                else:
                    cur.execute("SELECT date, content, pnl, created_at, updated_at FROM trade_journal ORDER BY date DESC")
                rows = cur.fetchall() or []
                result = []
                for row in rows:
                    r = dict(row)
                    if r.get("pnl") is not None:
                        r["pnl"] = float(r["pnl"])
                    if r.get("created_at"):
                        r["created_at"] = r["created_at"].isoformat()
                    if r.get("updated_at"):
                        r["updated_at"] = r["updated_at"].isoformat()
                    result.append(r)
                return result
        except Exception as e:
            logger.error(f"Error fetching journal entries: {e}")
            return []

    def delete_journal_entry(self, date_str):
        """Delete one journal entry by date."""
        self.ensure_connected()
        self._ensure_journal_table()
        try:
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM trade_journal WHERE date = %s", (date_str,))
            return True
        except Exception as e:
            logger.error(f"Error deleting journal entry: {e}")
            return False

    def _ensure_trade_classifications_table(self):
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trade_classifications (
                        trade_key VARCHAR(255) PRIMARY KEY,
                        filename VARCHAR(255),
                        trade_index INT,
                        is_b_trade BOOLEAN DEFAULT FALSE,
                        is_9_21_cross BOOLEAN DEFAULT FALSE,
                        early_exit BOOLEAN DEFAULT FALSE,
                        direction_right BOOLEAN DEFAULT TRUE,
                        notes TEXT,
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                """)
        except Exception as e:
            logger.error(f"Error ensuring trade_classifications table: {e}")

    def save_trade_classification(self, trade_key, filename, trade_index, is_b_trade, is_9_21_cross, early_exit, direction_right, notes=""):
        self.ensure_connected()
        self._ensure_trade_classifications_table()
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trade_classifications (trade_key, filename, trade_index, is_b_trade, is_9_21_cross, early_exit, direction_right, notes, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (trade_key) DO UPDATE SET
                        filename = EXCLUDED.filename,
                        trade_index = EXCLUDED.trade_index,
                        is_b_trade = EXCLUDED.is_b_trade,
                        is_9_21_cross = EXCLUDED.is_9_21_cross,
                        early_exit = EXCLUDED.early_exit,
                        direction_right = EXCLUDED.direction_right,
                        notes = EXCLUDED.notes,
                        updated_at = NOW();
                """, (trade_key, filename, trade_index, is_b_trade, is_9_21_cross, early_exit, direction_right, notes))
            return True
        except Exception as e:
            logger.error(f"Error saving trade classification: {e}")
            return False

    def get_all_trade_classifications(self):
        self.ensure_connected()
        self._ensure_trade_classifications_table()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT trade_key, filename, trade_index, is_b_trade, is_9_21_cross, early_exit, direction_right, notes FROM trade_classifications")
                rows = cur.fetchall() or []
                return {r["trade_key"]: dict(r) for r in rows}
        except Exception as e:
            logger.error(f"Error fetching trade classifications: {e}")
            return {}


# Global database instance
db = Database()

# Auto-connect on import
if DATABASE_URL:
    db.connect()

