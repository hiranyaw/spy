import asyncio
import json
import logging
import math
import re
import sys
import os
from datetime import datetime
from collections import deque
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

LA_TZ = ZoneInfo("America/Los_Angeles")

def la_now():
    """Current datetime in Los Angeles time."""
    return datetime.now(LA_TZ)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Database integration
DB_AVAILABLE = False
try:
    from database import db
    DB_AVAILABLE = db.connect()
except Exception as db_err:
    pass

# Market context (VIX, calendar, gap)
try:
    from market_context import get_full_context
    MARKET_CONTEXT_OK = True
except ImportError:
    MARKET_CONTEXT_OK = False

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BOT_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(BOT_DIR, "spy_trader.log"), encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

SIGNALS_FILE     = os.path.join(BOT_DIR, "signals.json")
PAPER_FILE       = os.path.join(BOT_DIR, "paper_trades.json")
TRENDLINE_BREAKS_FILE = os.path.join(BOT_DIR, "trendline_breaks.json")

# ── Windows Notification ──────────────────────────────────────
def send_notification(title, message):
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="SPY Trader", timeout=12)
    except Exception:
        try:
            import subprocess
            ps = (f'Add-Type -AssemblyName System.Windows.Forms;'
                  f'$n=New-Object System.Windows.Forms.NotifyIcon;'
                  f'$n.Icon=[System.Drawing.SystemIcons]::Information;'
                  f'$n.Visible=$true;'
                  f'$n.ShowBalloonTip(10000,"{title}","{message}",[System.Windows.Forms.ToolTipIcon]::Info);'
                  f'Start-Sleep -s 11;$n.Dispose()')
            subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", ps])
        except Exception as e:
            logger.warning(f"Notification failed: {e}")

# ── JS Scraper — reads AK MACD BB v2.0 table ─────────────────
SCRAPE_JS = r"""
() => {
    // ── Auto-expand legends if collapsed ───────────────────────
    document.querySelectorAll('[class*="toggler-"]').forEach(el => {
        const txt = (el.innerText || '').trim();
        if (/^\d+$/.test(txt) && parseInt(txt) > 2) {
            try {
                el.click();
            } catch(e) {}
        }
    });

    const title = document.title;
    const bodyInner = document.body.innerText;

    // Also gather text from HTML tables and chart overlay elements
    // Pine Script table.new() elements may not appear in body.innerText
    let extra = '';
    document.querySelectorAll('table, [class*="overlay"], [class*="markup"], [class*="pane-legend"]').forEach(el => {
        const t = el.innerText || el.textContent || '';
        if (t.length > 0 && t.length < 5000) extra += '\n' + t;
    });
    const body = bodyInner + '\n' + extra;

    // ── OHLC Close price helper (finds exchange, then "C\n<price>") ──
    function ohlcClose(exchange) {
        const idx = body.indexOf(exchange);
        if (idx === -1) return null;
        const chunk = body.substring(idx, idx + 150);
        const m = chunk.match(/\nC\n([+-]?[0-9,.]+)/);
        return m ? m[1].replace(/,/g,'') : null;
    }

    // ── SPY price ────────────────────────────────────────────
    let spy_price = ohlcClose("NYSE Arca") || ohlcClose("SPY\n1") || ohlcClose("SPY");
    if (!spy_price || spy_price === "N/A") {
        const tm = title.match(/SPY\s+([0-9,.]+)/);
        if (tm) spy_price = tm[1].replace(/,/g,'');
    }

    // ── QQQ price (from NASDAQ OHLC, NOT the tab bar) ───────
    let qqq_price = ohlcClose("NASDAQ") || ohlcClose("QQQ\n1") || ohlcClose("QQQ");
    if (!qqq_price) {
        const qm = title.match(/QQQ\s+([0-9,.]+)/);
        if (qm) qqq_price = qm[1].replace(/,/g,'');
    }

    // ── ADD value (NYSE A-D line, exchange = USI) ──────────
    // ADD is a breadth indicator: valid range roughly -3000 to +3000.
    // Only look for USI or $ADD — do NOT use generic "ADD" as it matches
    // other parts of the page and returns the SPY price by accident.
    let add_value = null;
    const addRaw = ohlcClose("USI") || ohlcClose("$ADD");
    if (addRaw !== null) {
        const addNum = parseFloat(addRaw);
        // Sanity check: ADD breadth values are never in stock-price territory
        if (!isNaN(addNum) && addNum >= -4000 && addNum <= 4000) {
            add_value = addRaw;
        }
    }

    // ── Read indicator plot values from legend ──────────────
    // The Pine Script outputs hidden plots (SIG_DIR, SIG_CONF, F_MACD, etc.)
    // with display=display.status_line. These appear in the indicator legend
    // as text that we can parse from the DOM.
    let legendText = '';
    document.querySelectorAll('[class*="legend"], [class*="pane-legend"], [data-name*="legend"]').forEach(el => {
        const t = el.innerText || el.textContent || '';
        if (t.includes('AK MACD') && t.includes('v2.0')) {
            legendText = t;
        }
    });

    let hasLegend = false;
    let leg_sig_dir = null, leg_sig_conf = null, leg_sig_ready = null;
    let leg_f_macd = null, leg_f_qqq = null, leg_f_add = null, leg_f_sp5 = null, leg_f_sp1 = null;
    let leg_r_score = null, leg_r_dir = null, leg_r_div = null, leg_r_addx = null, leg_r_stfl = null, leg_r_vwap = null, leg_r_engf = null;
    let leg_lvl_r = null, leg_lvl_s = null, leg_lvl_st = null, leg_time = null;

    if (legendText) {
        const parts = legendText.split(/v2\.0/i);
        if (parts.length > 1) {
            const afterTitle = parts[1];
            const matches = afterTitle.match(/[-+]?(?:[0-9]*\.[0-9]+|[0-9]+)/g);
            if (matches && matches.length >= 12) {
                const floatVals = matches.slice(0, 12).map(parseFloat);
                hasLegend = true;

                // Unpack trend factors from packed value
                const trendVal = Math.round(floatVals[0]);
                leg_f_macd = (trendVal & 16) ? 1.0 : -1.0;
                leg_f_qqq  = (trendVal & 8)  ? 1.0 : -1.0;
                leg_f_add  = (trendVal & 4)  ? 1.0 : -1.0;
                leg_f_sp5  = (trendVal & 2)  ? 1.0 : -1.0;
                leg_f_sp1  = (trendVal & 1)  ? 1.0 : -1.0;

                // Calculate confluence score, direction, and readiness
                const bullCount = ((leg_f_macd > 0) ? 1 : 0) +
                                  ((leg_f_qqq > 0) ? 1 : 0) +
                                  ((leg_f_add > 0) ? 1 : 0) +
                                  ((leg_f_sp5 > 0) ? 1 : 0) +
                                  ((leg_f_sp1 > 0) ? 1 : 0);
                const bearCount = 5 - bullCount;
                leg_sig_conf = Math.max(bullCount, bearCount);
                leg_sig_dir  = (bullCount > bearCount) ? 1.0 : -1.0;
                leg_sig_ready = (leg_sig_conf === 5) ? 1.0 : 0.0;

                // Reversal and levels
                leg_r_score = floatVals[1];
                leg_r_dir   = floatVals[2];
                leg_r_div   = floatVals[3];
                leg_r_addx  = floatVals[4];
                leg_r_stfl  = floatVals[5];
                leg_r_vwap  = floatVals[6];
                leg_r_engf  = floatVals[7];
                leg_lvl_r   = floatVals[8];
                leg_lvl_s   = floatVals[9];
                leg_lvl_st  = floatVals[10];
                leg_time    = floatVals[11];
            }
        }
    }

    // ── Helper functions ─────────────────────────────────────
    function findAfter(keyword, chars=60) {
        const idx = body.indexOf(keyword);
        if (idx === -1) return null;
        return body.substring(idx + keyword.length, idx + keyword.length + chars).trim();
    }
    function numAfter(keyword, chars=30) {
        const chunk = findAfter(keyword, chars);
        if (!chunk) return null;
        const m = chunk.match(/([+-]?[0-9]+\.?[0-9]*)/);
        return m ? m[1] : null;
    }

    // ── Trend signal from indicator table ────────────────────
    let signal_tv = "N/A", status_tv = "WAIT", conf_tv = "N/A";
    if (body.includes("SIGNALBUY") || body.includes("SIGNAL\nBUY"))   signal_tv = "BUY";
    if (body.includes("SIGNALSELL")|| body.includes("SIGNAL\nSELL"))  signal_tv = "SELL";
    if (body.includes("STATUSREADY")|| body.includes("STATUS\nREADY")) status_tv = "READY";
    const confM = body.match(/CONF[^0-9]*([0-9])\/5/);
    if (confM) conf_tv = confM[1] + "/5";

    // Individual factor directions
    function readDir(keyword) {
        const idx = body.indexOf(keyword);
        if (idx === -1) return null;
        const chunk = body.substring(idx, idx+40);
        if (chunk.includes("UP") || chunk.includes("\u2191")) return "UP";
        if (chunk.includes("DN") || chunk.includes("\u2193")) return "DN";
        return null;
    }

    let qqq_dir = readDir("QQQ 1m");
    let add_dir = readDir("ADD 1m");
    let spy5_dir = readDir("SPY 5m");
    let spy1_dir = readDir("SPY 1m");

    // ── Reversal signals from v2.0 table ─────────────────────
    let rev_score = null, rev_dir = null;
    const revIdx = body.indexOf("REV SCORE");
    if (revIdx !== -1) {
        const chunk = body.substring(revIdx, revIdx + 30);
        const m = chunk.match(/([0-9]+)\s*(BUY|SELL|--)/);
        if (m) { rev_score = parseInt(m[1]); rev_dir = m[2]; }
    }

    // Individual reversal factors
    let div_signal = "--", add_ext = null, st_flip = "--", vwap_pct = null, engulf = "--";
    const divIdx = body.indexOf("BULL DIV") !== -1 ? body.indexOf("BULL DIV") :
                   body.indexOf("BEAR DIV") !== -1 ? body.indexOf("BEAR DIV") :
                   body.indexOf("hBull") !== -1 ? body.indexOf("hBull") :
                   body.indexOf("hBear") !== -1 ? body.indexOf("hBear") : -1;
    if (divIdx !== -1) {
        const c = body.substring(divIdx, divIdx+20);
        if (c.includes("BULL DIV")) div_signal = "BULL DIV";
        else if (c.includes("BEAR DIV")) div_signal = "BEAR DIV";
        else if (c.includes("hBull")) div_signal = "hBull";
        else if (c.includes("hBear")) div_signal = "hBear";
    }
    const addExtIdx = body.indexOf("ADD EXT");
    if (addExtIdx !== -1) {
        const c = body.substring(addExtIdx, addExtIdx+30);
        if (c.includes("OVERSOLD")) add_ext = "OVERSOLD";
        else if (c.includes("OVERBOUGHT")) add_ext = "OVERBOUGHT";
        else { const m = c.match(/([+-]?[0-9]+)/); if (m) add_ext = m[1]; }
    }
    const stIdx = body.indexOf("ST FLIP");
    if (stIdx !== -1) {
        const c = body.substring(stIdx, stIdx+25);
        if (c.includes("FLIPPED UP"))  st_flip = "FLIPPED UP";
        else if (c.includes("FLIPPED DN")) st_flip = "FLIPPED DN";
        else if (c.includes("UP trend"))   st_flip = "UP trend";
        else if (c.includes("DN trend"))   st_flip = "DN trend";
    }
    const vwapIdx = body.indexOf("VWAP%");
    if (vwapIdx !== -1) {
        const c = body.substring(vwapIdx, vwapIdx+15);
        const m = c.match(/([+-]?[0-9]+\.[0-9]+)%/);
        if (m) vwap_pct = parseFloat(m[1]);
    }
    const engIdx = body.indexOf("ENGULF");
    if (engIdx !== -1) {
        const c = body.substring(engIdx, engIdx+20);
        if (c.includes("BULL ENG")) engulf = "BULL ENG";
        else if (c.includes("BEAR ENG")) engulf = "BEAR ENG";
    }

    // Levels
    let price_tv   = numAfter("PRICE", 15);
    let resist_tv  = numAfter("RESIST", 15) || numAfter("RESIST", 20);
    let support_tv = numAfter("SUPPORT", 15);
    let stlvl_tv   = numAfter("ST LVL", 15) || numAfter("ST FLIP", 20);
    let time_left  = null;
    const timeM = body.match(/TIME[^0-9]*([0-9]+)s/);
    if (timeM) time_left = timeM[1];

    // ── Override with legend data if available ────────────────
    if (hasLegend) {
        signal_tv = leg_sig_dir > 0 ? "BUY" : "SELL";
        status_tv = leg_sig_ready === 1 ? "READY" : "WAIT";
        conf_tv   = leg_sig_conf !== null ? leg_sig_conf + "/5" : "N/A";
        
        qqq_dir   = leg_f_qqq > 0 ? "UP" : "DN";
        add_dir   = leg_f_add > 0 ? "UP" : "DN";
        spy5_dir  = leg_f_sp5 > 0 ? "UP" : "DN";
        spy1_dir  = leg_f_sp1 > 0 ? "UP" : "DN";

        // Reversal score and direction
        rev_score = leg_r_score;
        rev_dir   = leg_r_dir > 0 ? "BUY" : (leg_r_dir < 0 ? "SELL" : "--");

        // Reversal factors
        if (leg_r_div === 1.0) div_signal = "BULL DIV";
        else if (leg_r_div === -1.0) div_signal = "BEAR DIV";
        else if (leg_r_div === 0.5) div_signal = "hBull";
        else if (leg_r_div === -0.5) div_signal = "hBear";
        else div_signal = "--";

        if (leg_r_addx === 1.0) add_ext = "OVERSOLD";
        else if (leg_r_addx === -1.0) add_ext = "OVERBOUGHT";
        else add_ext = add_value !== null ? String(Math.round(add_value)) : "--";

        if (leg_r_stfl === 1.0) st_flip = "FLIPPED UP";
        else if (leg_r_stfl === -1.0) st_flip = "FLIPPED DN";
        else if (leg_r_stfl === 0.1) st_flip = "UP trend";
        else if (leg_r_stfl === -0.1) st_flip = "DN trend";
        else st_flip = "--";

        vwap_pct  = leg_r_vwap;

        if (leg_r_engf === 1.0) engulf = "BULL ENG";
        else if (leg_r_engf === -1.0) engulf = "BEAR ENG";
        else engulf = "--";

        // Levels and prices
        price_tv   = spy_price;
        resist_tv  = leg_lvl_r !== null ? String(leg_lvl_r) : null;
        support_tv = leg_lvl_s !== null ? String(leg_lvl_s) : null;
        stlvl_tv   = leg_lvl_st !== null ? String(leg_lvl_st) : null;
        time_left  = leg_time !== null ? String(Math.round(leg_time)) : null;
    }

    // ── Debug: deep DOM scan for indicator data ───────────────
    // Search ALL divs for indicator keywords (Pine tables may render as positioned divs)
    let found_in_divs = [];
    const keywords_to_find = ["SIGNAL", "CONF", "REV SCORE", "SPY 5m", "QQQ 1m", "ADD 1m", "VWAP%"];
    document.querySelectorAll('div, span, td, th, p').forEach(el => {
        const t = el.textContent || '';
        if (t.length > 2 && t.length < 500) {
            for (const kw of keywords_to_find) {
                if (t.includes(kw) && !found_in_divs.some(f => f.text === t.substring(0, 80))) {
                    found_in_divs.push({kw, tag: el.tagName, cls: (el.className||'').substring(0,60), text: t.substring(0, 80)});
                }
            }
        }
    });

    const debug_keywords = {
        has_signal: body.includes("SIGNAL"),
        has_conf: body.includes("CONF"),
        has_rev_score: body.includes("REV SCORE"),
        has_qqq_1m: body.includes("QQQ 1m"),
        has_add_1m: body.includes("ADD 1m"),
        has_spy_5m: body.includes("SPY 5m"),
        has_spy_1m: body.includes("SPY 1m"),
        has_vwap_pct: body.includes("VWAP%"),
        has_engulf: body.includes("ENGULF"),
        html_tables: document.querySelectorAll('table').length,
        canvases: document.querySelectorAll('canvas').length,
        iframes: document.querySelectorAll('iframe').length,
        extra_len: extra.length,
        body_len: bodyInner.length,
        extra_sample: extra.substring(0, 300),
        divs_with_keywords: found_in_divs.slice(0, 10),
        all_legends: Array.from(document.querySelectorAll('[class*="legend"], [class*="pane-legend"], [data-name*="legend"]')).map(el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').substring(0, 150)).filter(t => t.includes('AK MACD') || t.includes('SIG_DIR')),
    };

    // ── LUXAlgo Trendline Break detection ─────────────────────
    // Looks for break signals from LUXAlgo Trendlines with Breaks indicator
    let tl_break = null;
    let tl_break_raw = '';

    // Scan legend/overlay elements for the LUXAlgo Trendlines indicator text
    document.querySelectorAll('[class*="legend"], [class*="pane-legend"], [class*="wrap"]').forEach(function(el) {
        var t = (el.innerText || el.textContent || '').replace(/\s+/g, ' ');
        // Look for either "TL_Break" or "B" with arrow (LuxAlgo format)
        if (/TL_Break|B\s*[\u2191\u2193\u25b2\u25bc]/.test(t)) {
            tl_break_raw += ' | ' + t.substring(0, 300);
        }
    });

    // Detect break direction from "B \u2191" or "B \u2193" (LuxAlgo format)
    if (tl_break_raw) {
        // Match "B" with up arrow for bullish break
        if (/B\s*[\u2191\u25b2]/i.test(tl_break_raw)) {
            tl_break = 'UP';
        }
        // Match "B" with down arrow for bearish break
        else if (/B\s*[\u2193\u25bc]/i.test(tl_break_raw)) {
            tl_break = 'DN';
        }
    }

    // ── Read ADX from standard indicator legend ─────────────────
    let adx_value = null;
    document.querySelectorAll('[class*="legend"], [class*="pane-legend"], [data-name*="legend"]').forEach(el => {
        const t = el.innerText || el.textContent || '';
        const m = t.match(/ADX\s*(?:\(\d+\))?\s*([0-9.]+)/i);
        if (m) {
            adx_value = parseFloat(m[1]);
        }
    });

    return JSON.stringify({
        signal_tv, status_tv, conf_tv,
        adx_value,
        qqq_dir,
        add_dir,
        spy5_dir,
        spy1_dir,
        // Reversal v2.0
        rev_score, rev_dir, div_signal, add_ext, st_flip, vwap_pct, engulf,
        // LUXAlgo Trendline Break
        tl_break, tl_break_raw: tl_break_raw.substring(0, 400),
        // Prices & levels
        spy_price, qqq_price, add_value,
        price_tv, resist: resist_tv, support: support_tv, st_level: stlvl_tv,
        time_left,
        timestamp: new Date().toISOString(),
        title, url: window.location.href,
        debug_keywords,
    });
}
"""

# ── Paper Trader (handles trend + reversal trades) ────────────
# ── ATR-Based Stop Loss Calculator ───────────────────────────
class ATRStopCalculator:
    """
    Tracks recent SPY high/low/close to compute ATR dynamically.
    ATR = average true range over last N bars.
    TP  = entry +/- (atr_mult_tp  * ATR)
    SL  = entry -/+ (atr_mult_sl  * ATR)
    Falls back to fixed pct if ATR not yet available.
    """
    def __init__(self, period=14, atr_mult_tp=1.5, atr_mult_sl=1.0):
        self.period    = period
        self.mult_tp   = atr_mult_tp
        self.mult_sl   = atr_mult_sl
        self.highs     = deque(maxlen=period + 1)
        self.lows      = deque(maxlen=period + 1)
        self.closes    = deque(maxlen=period + 1)

    def update(self, high, low, close):
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)

    @property
    def atr(self):
        if len(self.closes) < 2:
            return None
        trs = []
        for i in range(1, len(self.closes)):
            hl = self.highs[i] - self.lows[i]
            hc = abs(self.highs[i] - self.closes[i-1])
            lc = abs(self.lows[i]  - self.closes[i-1])
            trs.append(max(hl, hc, lc))
        return sum(trs) / len(trs)

    def get_levels(self, entry, direction, fallback_tp=0.12, fallback_sl=0.09):
        """Returns (tp_price, sl_price, atr_used)"""
        atr = self.atr
        if atr is None or entry <= 0:
            # fallback to fixed pct
            pct_tp = entry * (1 + fallback_tp/100) if direction=="BUY" else entry * (1 - fallback_tp/100)
            pct_sl = entry * (1 - fallback_sl/100) if direction=="BUY" else entry * (1 + fallback_sl/100)
            return round(pct_tp, 3), round(pct_sl, 3), None
        tp = (entry + self.mult_tp * atr) if direction=="BUY" else (entry - self.mult_tp * atr)
        sl = (entry - self.mult_sl * atr) if direction=="BUY" else (entry + self.mult_sl * atr)
        return round(tp, 3), round(sl, 3), round(atr, 4)


class PaperTrader:
    def __init__(self):
        self.position  = None
        self.trades    = self._load()
        self.atr_calc  = ATRStopCalculator(period=14, atr_mult_tp=1.5, atr_mult_sl=1.0)

    def _load(self):
        try:
            with open(PAPER_FILE) as f: return json.load(f)
        except: return []

    def _save(self):
        try:
            with open(PAPER_FILE, "w") as f:
                json.dump(self.trades, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"paper_trades.json write failed: {e}")

    def update_atr(self, high, low, close):
        """Call each tick to keep ATR fresh."""
        if high and low and close:
            self.atr_calc.update(high, low, close)

    def on_signal(self, signal, spy_price, qqq_price, signal_type="trend"):
        if not spy_price: return
        now = la_now().strftime("%H:%M:%S")
        direction = "BUY" if "BUY" in signal else "SELL" if "SELL" in signal else None
        if not direction: return

        # Close existing position if direction flips
        if self.position:
            pos_dir = self.position["direction"]
            opposite = (pos_dir == "LONG" and direction == "SELL") or \
                       (pos_dir == "SHORT" and direction == "BUY")
            if opposite:
                entry = self.position["entry_price"]
                pnl = (spy_price - entry) if pos_dir == "LONG" else (entry - spy_price)
                trade = {
                    "entry_time":  self.position["entry_time"],
                    "exit_time":   now,
                    "direction":   pos_dir,
                    "signal_type": self.position.get("signal_type","trend"),
                    "entry_price": round(entry, 2),
                    "exit_price":  round(spy_price, 2),
                    "pnl":         round(pnl, 3),
                    "win":         pnl > 0,
                }
                self.trades.append(trade)
                self._save()
                logger.info(f"[PAPER] CLOSED {pos_dir} @ {spy_price:.2f} | PnL: {pnl:+.3f} | {'WIN' if pnl>0 else 'LOSS'} [{self.position.get('signal_type','')}]")
                
                if DB_AVAILABLE and self.position.get("db_id"):
                    try:
                        db.close_paper_trade(self.position["db_id"], round(spy_price, 2))
                    except Exception as db_err:
                        logger.warning(f"Failed to close paper trade in database: {db_err}")
                self.position = None

        # Open new position
        if not self.position:
            new_dir = "LONG" if direction == "BUY" else "SHORT"
            tp, sl, atr = self.atr_calc.get_levels(spy_price, direction)
            self.position = {
                "direction":   new_dir,
                "entry_price": spy_price,
                "entry_time":  now,
                "entry_qqq":   round(qqq_price, 2) if qqq_price else None,
                "signal_type": signal_type,
                "tp_price":    tp,
                "sl_price":    sl,
                "atr":         atr,
            }
            db_trade = {
                "entry_time":  datetime.now(),
                "direction":   new_dir,
                "entry_price": spy_price,
                "signal_type": signal_type,
                "conf_score":  None
            }
            if DB_AVAILABLE:
                try:
                    trade_id = db.save_paper_trade(db_trade)
                    self.position["db_id"] = trade_id
                except Exception as db_err:
                    logger.warning(f"Failed to save paper trade to database: {db_err}")

            atr_str = f"ATR={atr:.4f}" if atr else "ATR=fallback"
            logger.info(f"[PAPER] OPENED {new_dir} @ {spy_price:.2f} | TP={tp} SL={sl} [{atr_str}] [{signal_type}]")

    def stats(self):
        if not self.trades:
            return {"total":0,"wins":0,"losses":0,"win_rate":0,"total_pnl":0,"avg_win":0,"avg_loss":0,
                    "trend_total":0,"trend_wr":0,"rev_total":0,"rev_wr":0,
                    "strong_total":0,"strong_wr":0}
        wins = [t for t in self.trades if t["win"]]
        losses = [t for t in self.trades if not t["win"]]
        wr = len(wins)/len(self.trades)*100 if self.trades else 0
        aw = sum(t["pnl"] for t in wins)/len(wins)     if wins   else 0
        al = sum(t["pnl"] for t in losses)/len(losses) if losses else 0
        trend_t  = [t for t in self.trades if t.get("signal_type","trend")=="trend"]
        rev_t    = [t for t in self.trades if t.get("signal_type")=="reversal"]
        strong_t = [t for t in self.trades if t.get("signal_type")=="strong"]
        return {
            "total":        len(self.trades),
            "wins":         len(wins),
            "losses":       len(losses),
            "win_rate":     round(wr, 1),
            "total_pnl":    round(sum(t["pnl"] for t in self.trades), 3),
            "avg_win":      round(aw, 3),
            "avg_loss":     round(al, 3),
            "trend_total":  len(trend_t),
            "trend_wr":     round(sum(1 for t in trend_t if t["win"])/len(trend_t)*100,1) if trend_t else 0,
            "rev_total":    len(rev_t),
            "rev_wr":       round(sum(1 for t in rev_t if t["win"])/len(rev_t)*100,1) if rev_t else 0,
            "strong_total": len(strong_t),
            "strong_wr":    round(sum(1 for t in strong_t if t["win"])/len(strong_t)*100,1) if strong_t else 0,
        }

    def open_position_info(self, spy_price):
        if not self.position or not spy_price: return None
        entry = self.position["entry_price"]
        unr = (spy_price - entry) if self.position["direction"]=="LONG" else (entry - spy_price)
        return {
            "direction":   self.position["direction"],
            "entry_price": round(entry, 2),
            "entry_time":  self.position["entry_time"],
            "signal_type": self.position.get("signal_type","trend"),
            "unrealized":  round(unr, 3),
            "tp_price":    self.position.get("tp_price"),
            "sl_price":    self.position.get("sl_price"),
            "atr":         self.position.get("atr"),
        }

# ── Signal Strategy — AK MACD BB v2.0 ────────────────────────
class AKMACDBBStrategy:
    """
    Reads both TREND (5/5 confluence) and REVERSAL (score>=3) signals
    from the AK MACD BB v2.0 TradingView table.
    """
    def evaluate(self, data):
        signal_tv = data.get("signal_tv", "N/A")
        status_tv = data.get("status_tv", "WAIT")
        conf_tv   = data.get("conf_tv", "N/A")
        rev_score = data.get("rev_score")
        rev_dir   = data.get("rev_dir")
        spy_price = data.get("spy_price")
        qqq_price = data.get("qqq_price")

        details = {
            "spy_price":  spy_price,
            "qqq_price":  qqq_price,
            "add":        data.get("add_value"),
            "signal_tv":  signal_tv,
            "status_tv":  status_tv,
            "conf_tv":    conf_tv,
            "qqq_dir":    data.get("qqq_dir"),
            "add_dir":    data.get("add_dir"),
            "spy5_dir":   data.get("spy5_dir"),
            "spy1_dir":   data.get("spy1_dir"),
            # Reversal fields
            "rev_score":  rev_score,
            "rev_dir":    rev_dir,
            "div_signal": data.get("div_signal"),
            "add_ext":    data.get("add_ext"),
            "st_flip":    data.get("st_flip"),
            "vwap_pct":   data.get("vwap_pct"),
            "engulf":     data.get("engulf"),
            # LUXAlgo Trendline Break
            "tl_break":   data.get("tl_break"),
            # Levels
            "resist":     data.get("resist"),
            "support":    data.get("support"),
            "st_level":   data.get("st_level"),
            "time_left":  data.get("time_left"),
            "adx_value":  data.get("adx_value"),
        }

        # 0. STRONG signal — Supertrend just FLIPPED + 4/5 or 5/5 confluence (HIGHEST priority)
        # Fires the moment Supertrend reverses direction while trend is already strong.
        # (LUXAlgo trendline breaks use canvas rendering and can't be scraped from DOM.)
        st_flip_v  = data.get("st_flip", "") or ""
        just_flipped = "FLIPPED" in st_flip_v        # "FLIPPED UP" or "FLIPPED DN"
        conf_num   = int(conf_tv[0]) if conf_tv and conf_tv[0].isdigit() else 0
        if just_flipped and conf_num >= 4:
            if "UP" in st_flip_v:
                return "STRONG-BUY", details, "strong"
            if "DN" in st_flip_v:
                return "STRONG-SELL", details, "strong"

        # 1. TREND signal (5/5 confluence)
        if status_tv == "READY" and signal_tv == "BUY":
            return "BUY", details, "trend"
        if status_tv == "READY" and signal_tv == "SELL":
            return "SELL", details, "trend"

        # 2. REVERSAL signal (score >= 3)
        if rev_score is not None and rev_score >= 3:
            if rev_dir == "BUY":
                return f"REV-BUY (score={rev_score})", details, "reversal"
            if rev_dir == "SELL":
                return f"REV-SELL (score={rev_score})", details, "reversal"

        # 3. Hold with info
        if conf_tv and conf_tv.startswith("4"):
            hold_msg = f"HOLD (4/5 — waiting for 5th, dir={signal_tv})"
        elif rev_score and rev_score == 2:
            hold_msg = f"HOLD (Rev score=2, watching for {rev_dir})"
        elif signal_tv in ("BUY","SELL"):
            hold_msg = f"HOLD ({conf_tv} conf, status={status_tv})"
        else:
            hold_msg = f"HOLD (signal={signal_tv} conf={conf_tv})"
        return hold_msg, details, "none"


# ── Trendline Break Recorder ──────────────────────────────────
def record_trendline_break(details):
    """Record trendline break events to trendline_breaks.json"""
    tl_break = details.get("tl_break")
    tl_break_raw = details.get("tl_break_raw", "")

    # Log detection attempts for debugging
    if not tl_break:
        if tl_break_raw:
            logger.debug(f"TrendlineBreak detection: no match. Raw text: {tl_break_raw[:200]}")
        return

    if tl_break == "?":
        logger.warning(f"TrendlineBreak detection returned '?'. Raw: {tl_break_raw[:200]}")
        return

    spy_price = details.get("spy_price")
    qqq_price = details.get("qqq_price")
    now = la_now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    try:
        # Load existing breaks
        if os.path.exists(TRENDLINE_BREAKS_FILE):
            with open(TRENDLINE_BREAKS_FILE, "r") as f:
                data = json.load(f)
        else:
            data = {"breaks": []}

        # Avoid duplicates within 60 seconds (prevents repeated false positives)
        recent = [b for b in data.get("breaks", [])
                  if b.get("date") == date_str]
        if recent:
            last_break = recent[-1]
            last_time_str = last_break.get("time", "")
            # Check if same direction within 60 seconds
            if last_break.get("symbol") == "SPY" and last_break.get("direction") == tl_break:
                try:
                    from datetime import datetime
                    last_dt = datetime.strptime(last_time_str, "%H:%M:%S")
                    curr_dt = datetime.strptime(time_str, "%H:%M:%S")
                    time_diff = (curr_dt.hour * 3600 + curr_dt.minute * 60 + curr_dt.second) - \
                               (last_dt.hour * 3600 + last_dt.minute * 60 + last_dt.second)
                    if time_diff < 60 and time_diff >= 0:
                        logger.debug(f"Skipping duplicate trendline break (same direction within 60s)")
                        return
                except:
                    pass

        # Record the break
        break_item = {
            "date": date_str,
            "time": time_str,
            "symbol": "SPY",
            "direction": tl_break,
            "price": str(spy_price) if spy_price else "?",
            "is_manual": False
        }
        data["breaks"].append(break_item)

        with open(TRENDLINE_BREAKS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"✓ RECORDED: SPY Trendline {tl_break} @ {spy_price} [{time_str}]")

        if DB_AVAILABLE:
            try:
                db.save_trendline_break(break_item)
            except Exception as db_err:
                logger.warning(f"Failed to save trendline break to database: {db_err}")
    except Exception as e:
        logger.warning(f"Failed to record trendline break: {e}")

# ── Signal Writer ─────────────────────────────────────────────────────────
def save_signal(signal, signal_type, details, history, paper):
    spy = details.get("spy_price")
    try:
        spy_f = float(spy) if spy else None
    except:
        spy_f = None

    # Record trendline breaks
    record_trendline_break(details)

    payload = {
        "last_update":   la_now().isoformat(),
        "signal":        signal,
        "signal_type":   signal_type,
        "details":       details,
        "history":       history[-60:],
        "paper_stats":   paper.stats(),
        "paper_trades":  paper.trades[-100:],
        "open_position": paper.open_position_info(spy_f),
    }
    def _clean(obj):
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        return obj
    try:
        with open(SIGNALS_FILE, "w") as f:
            json.dump(_clean(payload), f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"signals.json write failed: {e}")

    if DB_AVAILABLE:
        try:
            db_payload = {
                "signal":        signal,
                "signal_type":   signal_type,
                "status":        details.get("status_tv") or details.get("status") or "READY",
                "conf_tv":       details.get("conf_tv") or details.get("confidence") or "0",
                "spy_price":     spy_f,
                "qqq_price":     float(details.get("qqq_price") or details.get("qqq") or spy_f or 0.0),
                "add_value":     float(details.get("add") or details.get("add_value") or 0.0),
                "macd_dir":      details.get("signal_tv") or details.get("macd_dir") or "",
                "rev_score":     int(details.get("rev_score") or 0),
                "rev_dir":       details.get("rev_dir") or "",
                "st_flip":       details.get("st_flip") or "",
                "tl_break":      details.get("tl_break") or "",
            }
            db.save_signal(db_payload)
        except Exception as db_err:
            logger.warning(f"Failed to save signal to database: {db_err}")


# ── Main Bot ──────────────────────────────────────────────────
class SpyTradingBot:
    def __init__(self):
        self.session        = None
        self.strategy       = AKMACDBBStrategy()
        self.paper          = PaperTrader()
        self.signal_history = []
        self.last_signal    = None
        self.market_ctx     = {}
        self.ctx_tick       = 0   # refresh market context every 5 ticks
        self.server_params  = StdioServerParameters(
            command="npx",
            args=["-y", "chrome-devtools-mcp", "--browserUrl", "http://127.0.0.1:9222"]
        )

    async def connect(self):
        logger.info("Connecting to Chrome DevTools MCP...")
        try:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self.session = session
                    logger.info("Connected.")
                    await self.run_loop()
        except Exception as e:
            logger.error(f"Connection failed: {e}")

    async def run_loop(self):
        while True:
            try:
                logger.info(f"--- Tick {la_now().strftime('%H:%M:%S')} ---")

                # Refresh market context every 5 ticks (~5 min)
                self.ctx_tick += 1
                if MARKET_CONTEXT_OK and self.ctx_tick % 5 == 1:
                    try:
                        self.market_ctx = get_full_context()
                        vix = self.market_ctx.get('vix')
                        regime = self.market_ctx.get('vix_regime','')
                        blocked = self.market_ctx.get('is_blocked', False)
                        logger.info(f"Market context: VIX={vix} ({regime}) | Blocked={blocked} | "
                                    f"Events={len(self.market_ctx.get('events',[]))}")
                    except Exception as e:
                        logger.warning(f"Market context error: {e}")

                # Block trading around high-impact events
                if self.market_ctx.get('is_blocked'):
                    reason = self.market_ctx.get('block_reason','Economic event')
                    logger.info(f"TRADING PAUSED: {reason}")
                    save_signal(f"PAUSED: {reason}", "blocked", {
                        **self.market_ctx,
                        "spy_price": None
                    }, self.signal_history, self.paper)
                    await asyncio.sleep(60)
                    continue

                try:
                    pages = await self.session.call_tool("list_pages", {})
                    raw   = pages.content[0].text
                    if "tradingview" not in raw.lower():
                        logger.info("Waiting for TradingView tab...")
                        await asyncio.sleep(10)
                        continue
                except Exception as e:
                    logger.debug(f"Page check: {e}")

                data = await self.scrape()
                if not data:
                    await asyncio.sleep(30)
                    continue

                def clean(v):
                    if not v or v == "N/A": return None
                    try: return float(str(v).replace(',','').replace('+',''))
                    except: return None

                spy = clean(data.get("spy_price"))
                qqq = clean(data.get("qqq_price"))

                logger.info(f"SPY:{data.get('spy_price')}  QQQ:{data.get('qqq_price')}  "
                            f"ADD:{data.get('add_value')}  conf:{data.get('conf_tv')}  "
                            f"TV:{data.get('signal_tv')}/{data.get('status_tv')}  "
                            f"RevScore:{data.get('rev_score')}/{data.get('rev_dir')}")

                dbg = data.get("debug_keywords")
                if dbg:
                    logger.info(f"DEBUG: tables={dbg.get('html_tables')} canvas={dbg.get('canvases')} "
                                f"iframes={dbg.get('iframes')} extra={dbg.get('extra_len')} "
                                f"SIGNAL={dbg.get('has_signal')} CONF={dbg.get('has_conf')} "
                                f"QQQ1m={dbg.get('has_qqq_1m')} SPY5m={dbg.get('has_spy_5m')} "
                                f"REV={dbg.get('has_rev_score')}")
                    all_legs = dbg.get("all_legends", [])
                    if all_legs:
                        logger.info(f"DEBUG LEGENDS SCANNED: {all_legs}")
                    divs = dbg.get("divs_with_keywords", [])
                    if divs:
                        logger.info(f"DEBUG DIVS FOUND: {divs}")
                    else:
                        logger.info(f"DEBUG: No divs with indicator keywords found. extra_sample: {dbg.get('extra_sample','')[:200]}")

                if spy:
                    signal, details, sig_type = self.strategy.evaluate(data)
                    logger.info(f"SIGNAL [{sig_type.upper()}]: {signal}")

                    # ── Alerts ───────────────────────────────────
                    is_actionable = (
                        signal.startswith("BUY") or signal.startswith("SELL") or
                        signal.startswith("REV-BUY") or signal.startswith("REV-SELL") or
                        signal.startswith("STRONG-BUY") or signal.startswith("STRONG-SELL")
                    )

                    if is_actionable and signal != self.last_signal:
                        if sig_type == "strong":
                            tl_br  = details.get('tl_break', '?')
                            st_f   = details.get('st_flip', '?')
                            title  = f"SPY Trader: {signal}"
                            msg    = f"⭐ STRONG — LUX Break {tl_br} | ST={st_f} | SPY {spy}"
                        elif sig_type == "trend":
                            title = f"SPY Trader: {signal}"
                            msg   = f"5/5 TREND — SPY {spy}  QQQ {qqq}  Conf {details.get('conf_tv','?')}"
                        else:
                            rev_sc = details.get('rev_score','?')
                            st_f   = details.get('st_flip','')
                            div_s  = details.get('div_signal','')
                            title  = f"SPY Trader: {signal}"
                            msg    = f"REV score={rev_sc} | {st_f} | {div_s} | VWAP:{details.get('vwap_pct','?')}%"
                        send_notification(title, msg)
                        logger.info(f"*** ALERT SENT: {title} ***")
                        self.last_signal = signal

                        # Paper trade
                        self.paper.on_signal(signal, spy, qqq, sig_type)

                    elif signal.startswith("HOLD"):
                        self.last_signal = None  # reset so next real signal alerts

                    # Add VIX warning to signal if high vol
                    vix_warn = self.market_ctx.get('vix_adj', {}).get('warn')
                    if vix_warn and is_actionable:
                        logger.info(f"VIX WARNING: {vix_warn}")

                    # Block reversal trades in extreme VIX
                    if self.market_ctx.get('vix_adj', {}).get('skip_reversals') and sig_type == "reversal":
                        logger.info(f"REVERSAL SKIPPED — VIX too high ({self.market_ctx.get('vix')})")
                        signal = f"HOLD (reversal skipped — VIX {self.market_ctx.get('vix')} too high)"
                        sig_type = "none"

                    record = {
                        "time":        la_now().strftime("%H:%M:%S"),
                        "signal":      signal,
                        "signal_type": sig_type,
                        "spy":         spy,
                        "qqq":         clean(data.get("qqq_price")),
                        "add":         clean(data.get("add_value")),
                        "conf_tv":     data.get("conf_tv"),
                        "status_tv":   data.get("status_tv"),
                        "rev_score":   data.get("rev_score"),
                        "rev_dir":     data.get("rev_dir"),
                        "st_flip":     data.get("st_flip"),
                        "div_signal":  data.get("div_signal"),
                        "tl_break":    data.get("tl_break"),
                        "vix":         self.market_ctx.get('vix'),
                        "vix_regime":  self.market_ctx.get('vix_regime'),
                    }
                    self.signal_history.append(record)

                    # Merge market context into details for dashboard
                    details["vix"]         = self.market_ctx.get('vix')
                    details["vix_regime"]  = self.market_ctx.get('vix_regime')
                    details["vix_warn"]    = vix_warn
                    details["events"]      = self.market_ctx.get('events', [])
                    details["gap"]         = self.market_ctx.get('gap')
                    details["is_blocked"]  = self.market_ctx.get('is_blocked', False)

                    save_signal(signal, sig_type, details, self.signal_history, self.paper)

                # Update ATR every tick using resistance/support as high/low proxy
                resist  = clean(data.get("resist"))
                support = clean(data.get("support"))
                if spy and resist and support:
                    self.paper.update_atr(resist, support, spy)

                # Dynamic sleep interval from config file
                sleep_s = 60
                interval_file = os.path.join(BOT_DIR, "update_interval.txt")
                if os.path.exists(interval_file):
                    try:
                        with open(interval_file, "r") as f:
                            val = int(f.read().strip())
                            if val in (15, 30, 45, 60):
                                sleep_s = val
                    except:
                        pass
                await asyncio.sleep(sleep_s)

            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(10)

    async def scrape(self):
        if not self.session: return None
        try:
            result = await self.session.call_tool("evaluate_script", {"function": SCRAPE_JS})
            if result and result.content:
                raw = result.content[0].text
                m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
                if m:
                    s = m.group(1).strip()
                    if s.startswith('"'): s = json.loads(s)
                    return json.loads(s)
                try: return json.loads(raw)
                except: return None
        except Exception as e:
            logger.warning(f"Scrape failed: {e}")
            return None


async def main():
    bot = SpyTradingBot()
    await bot.connect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
