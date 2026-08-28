import sys
import datetime
import logging
import pathlib
import winsound
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QScrollArea, QFrame, QStatusBar, QTabWidget,
)
from PySide6.QtCore import QTimer, Qt
from ui_components import (
    render_connection_badge, render_big_countdown,
    render_3_direction_confluence, render_top_hero_recommendation,
    render_conditions_and_last_rec, render_indicator_panel,
    render_status_block, render_ascii_ladder, render_bullet_points,
    render_bar_history,
)
from tradingview_client import fetch_latest_bar, get_bar_history
from signals import analyze_bar, analyze_with_indicators
from tv_scraper import fetch_indicators, fetch_live_prices
from journal_tab import JournalTab
from trade_analysis_tab import TradeAnalysisTab

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── Try to import plyer for Windows toast notifications ───────────────────────
try:
    from plyer import notification as _plyer_notification
    _PLYER_AVAILABLE = True
except ImportError:
    _PLYER_AVAILABLE = False

# ── Logging setup ─────────────────────────────────────────────────────────────
_LOG_FILE = pathlib.Path(__file__).parent / "spytrade.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("app")
log.info("=" * 60)
log.info("SPYTrade starting  –  log file: %s", _LOG_FILE)
log.info("=" * 60)

REFRESH_MS = 60_000  # poll every 60 seconds

# ── Alert beep frequencies ────────────────────────────────────────────────────
_BEEP_STRONG_BUY  = (880, 200)   # (Hz, ms) — high pitch
_BEEP_BUY         = (660, 150)
_BEEP_STRONG_SELL = (330, 200)   # low pitch
_BEEP_SELL        = (440, 150)
_BEEP_MAP = {
    "STRONG BUY":  _BEEP_STRONG_BUY,
    "BUY":         _BEEP_BUY,
    "STRONG SELL": _BEEP_STRONG_SELL,
    "SELL":        _BEEP_SELL,
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPYTrade – Scalper & 3‑Way Confluence Dashboard")
        self.setMinimumSize(980, 860)
        self._countdown = REFRESH_MS // 1000
        self._last_signal: str | None = None
        self._last_actionable_rec: dict | None = None
        self._is_fetching = False

        # ── Root container ──────────────────────────────────────────────────
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 12, 14, 8)
        root_layout.setSpacing(6)

        # ── Header row: Title + Connection Badge + BIG COUNTDOWN + Refresh ──
        header = QHBoxLayout()
        header.setSpacing(10)

        title_label = QLabel("📊 <b>SPYTrade</b>")
        title_label.setObjectName("title")
        header.addWidget(title_label)

        # Connection status badge
        self.conn_label = QLabel()
        self.conn_label.setTextFormat(Qt.RichText)
        self.conn_label.setText(render_connection_badge(False, "Checking..."))
        header.addWidget(self.conn_label)

        header.addStretch()

        # BIG countdown counter badge on top
        self.countdown_label = QLabel()
        self.countdown_label.setTextFormat(Qt.RichText)
        self.countdown_label.setText(render_big_countdown(self._countdown, False))
        header.addWidget(self.countdown_label)

        # Refresh button
        self.refresh_btn = QPushButton("⟳  Refresh Now")
        self.refresh_btn.setObjectName("refresh_btn")
        self.refresh_btn.setFixedWidth(135)
        self.refresh_btn.clicked.connect(self._manual_refresh)
        header.addWidget(self.refresh_btn)

        root_layout.addLayout(header)

        # ── Divider ─────────────────────────────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("divider")
        root_layout.addWidget(line)

        # ── Tab Widget ───────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setObjectName("main_tabs")

        # ── Tab 1: Live Dashboard ────────────────────────────────────────────
        dashboard_tab = QWidget()
        dash_layout = QVBoxLayout(dashboard_tab)
        dash_layout.setContentsMargins(0, 4, 0, 0)
        dash_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 2, 0, 4)
        content_layout.setSpacing(6)

        # ── 1. BIG 3-Way Direction Confluence (SPY, QQQ, ADD) on TOP ──
        self.confluence_label = QLabel()

        # ── 2. Top Big Colorful Hero Recommendation (Large Entry/Target/Stop) ──
        self.hero_rec_label = QLabel()

        # ── 3. Waiting for Conditions & Last Recommendation Box ──
        self.conditions_label = QLabel()

        # ── 4. Live Indicators & Market Stream Grid (with Exact Timestamps) ──
        self.indicator_label = QLabel()

        # ── 5. 1-Minute Candle Action & Ladder ──
        self.status_label  = QLabel()
        self.ladder_label  = QLabel()
        self.bullet_label  = QLabel()

        # ── 6. Recent Bar History Table ──
        self.history_label = QLabel()

        # ── 7. Last updated timestamp tag ──
        self.updated_label = QLabel()
        self.updated_label.setObjectName("updated_label")

        for lbl in (self.confluence_label, self.hero_rec_label, self.conditions_label,
                    self.indicator_label, self.status_label, self.ladder_label,
                    self.bullet_label, self.history_label, self.updated_label):
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.RichText)
            content_layout.addWidget(lbl)

        content_layout.addStretch()
        scroll.setWidget(content_widget)
        dash_layout.addWidget(scroll)

        self.tabs.addTab(dashboard_tab, "📊  Live Dashboard")

        # ── Tab 2: Trade Analysis ────────────────────────────────────────────
        self.trade_analysis_tab = TradeAnalysisTab(status_callback=self._status_msg)
        self.tabs.addTab(self.trade_analysis_tab, "📈  Trade Analysis")

        # ── Tab 3: Trade Journal ─────────────────────────────────────────────
        self.journal_tab = JournalTab(status_callback=self._status_msg)
        self.tabs.addTab(self.journal_tab, "📝  Trade Journal")

        root_layout.addWidget(self.tabs)

        # ── Status bar ───────────────────────────────────────────────────────
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._status_msg("Initialising connection to TradingView…")

        # ── Timers ───────────────────────────────────────────────────────────
        self._data_timer = QTimer(self)
        self._data_timer.timeout.connect(self._scheduled_refresh)
        self._data_timer.start(REFRESH_MS)

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(1_000)

        # First update immediately
        self.update_data()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _status_msg(self, msg: str):
        self.status_bar.showMessage(msg)

    def _tick(self):
        if self._countdown > 0:
            self._countdown -= 1
        # Update the big countdown timer badge every second
        self.countdown_label.setText(render_big_countdown(self._countdown, self._is_fetching))
        if not self._is_fetching:
            self._status_msg(f"Next auto-refresh in {self._countdown}s")

    def _scheduled_refresh(self):
        self._countdown = REFRESH_MS // 1000
        self.update_data()

    def _manual_refresh(self):
        """Reset the countdown and fetch immediately."""
        self._data_timer.start(REFRESH_MS)
        self._countdown = REFRESH_MS // 1000
        self.update_data()

    def _fire_alert(self, signal: str) -> None:
        """Play a beep and show a toast notification when signal changes."""
        if signal == self._last_signal:
            return

        self._last_signal = signal
        beep = _BEEP_MAP.get(signal)
        if beep:
            try:
                winsound.Beep(*beep)
            except Exception as e:
                log.warning("winsound.Beep failed: %s", e)

            if _PLYER_AVAILABLE:
                try:
                    _plyer_notification.notify(
                        title=f"SPYTrade — {signal}",
                        message=f"New trade recommendation: {signal}",
                        app_name="SPYTrade",
                        timeout=5,
                    )
                except Exception as e:
                    log.warning("plyer notification failed: %s", e)

    # ── Data update ──────────────────────────────────────────────────────────

    def update_data(self):
        if self._is_fetching:
            return
        self._is_fetching = True

        # Immediate visual feedback
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("⏳ Fetching...")
        self.countdown_label.setText(render_big_countdown(self._countdown, True))
        self._status_msg("Fetching live data & indicators from TradingView...")
        QApplication.processEvents()

        try:
            log.info("--- fetch cycle start ---")
            current_time_str = datetime.datetime.now().strftime("%H:%M:%S PT")

            # 1. Grab history before fetching new bar
            history = get_bar_history()

            # 2. Fetch latest candle bar from TV
            bar = fetch_latest_bar()

            # 3. Scrape live indicators (SPY, QQQ, ADX, ADD, MACD, TL break, ST, etc.)
            indicators = fetch_indicators()

            if indicators:
                log.info(
                    "fetch_indicators: spy=%s  qqq=%s  adx=%s  add=%s  signal=%s  conf=%s",
                    indicators.get("spy_price"),
                    indicators.get("qqq_price"),
                    indicators.get("adx_value"),
                    indicators.get("add_value"),
                    indicators.get("signal_tv"),
                    indicators.get("conf_tv"),
                )
            else:
                log.info("fetch_indicators: None")

            is_connected = bool(indicators or (bar and bar.get("close", 0) > 0))

            if not is_connected and not bar and not indicators:
                self.conn_label.setText(render_connection_badge(False, "No CDP listener on port 9222"))
                self.confluence_label.clear()
                self.hero_rec_label.setText(
                    "<div style='border:2px solid #f44336;border-radius:8px;padding:14px;background:rgba(244,67,54,0.1);'>"
                    "<span style='font-size:22px;font-weight:bold;color:#f44336;'>🔴 TRADINGVIEW DISCONNECTED</span><br>"
                    "<span style='color:#b0bec5;font-size:13px;'>Ensure Chrome is running with remote debugging port 9222 and TradingView is open.</span>"
                    "</div>"
                )
                self.conditions_label.clear()
                self.indicator_label.clear()
                self.status_label.clear()
                self.ladder_label.clear()
                self.bullet_label.clear()
                self.history_label.clear()
                self.updated_label.clear()
                self._status_msg("⚠ Not connected to TradingView.")
                return

            # Sanitize price: If bar price is negative/wrong (e.g. from ADD chart) or missing,
            # use real SPY OHLCV from TradingView Scanner API
            real_spy = indicators.get("spy_price") if indicators else None
            if (not bar or bar.get("close", 0) < 100) and (real_spy and real_spy > 100):
                bar = {
                    "open":   indicators.get("spy_open", real_spy),
                    "high":   indicators.get("spy_high", real_spy),
                    "low":    indicators.get("spy_low", real_spy),
                    "close":  real_spy,
                    "volume": indicators.get("spy_volume", 0),
                    "timestamp": indicators.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat()
                }

            # Update connection badge in header
            details_str = f"SPY: ${real_spy:.2f}" if real_spy else "Active"
            self.conn_label.setText(render_connection_badge(True, details_str))

            # ── Compute enhanced recommendation ──────────────────────────────
            rec = analyze_with_indicators(bar, history, indicators)

            # Store last actionable recommendation if not HOLD
            if rec.get("signal") in ("STRONG BUY", "BUY", "STRONG SELL", "SELL"):
                self._last_actionable_rec = dict(rec)
                self._last_actionable_rec["time_str"] = current_time_str

            # ── Render top-to-bottom panels ──────────────────────────────────
            # 1. Big 3-Way Direction Confluence (SPY, QQQ, ADD)
            self.confluence_label.setText(render_3_direction_confluence(rec, bar))

            # 2. Top Hero Recommendation Banner (with large Entry, Target, Stop levels)
            self.hero_rec_label.setText(render_top_hero_recommendation(rec))

            # 3. Conditions & Last Recommendation Box
            self.conditions_label.setText(render_conditions_and_last_rec(rec, self._last_actionable_rec))

            # 4. Live Indicators & Market Stream Grid (with Exact Timestamps)
            self.indicator_label.setText(render_indicator_panel(rec, current_time_str))

            # 5. 1-Minute Candle Action & Ladder
            self.status_label.setText(render_status_block(bar, actual_price=real_spy))
            self.ladder_label.setText(render_ascii_ladder(bar))
            self.bullet_label.setText(render_bullet_points(bar, rec=rec, time_str=current_time_str))

            # 6. Bar history table
            updated_history = get_bar_history()
            self.history_label.setText(render_bar_history(updated_history))

            # Fire alert on signal changes
            self._fire_alert(rec["signal"])

            now = current_time_str
            self.updated_label.setText(
                f"<span style='color:#8b949e;font-size:12px'>Last updated: <b>{now}</b>  "
                f"| Signal: <b>{rec['emoji']} {rec['signal']}</b> "
                f"({rec['confidence']}% confidence)</span>"
            )
            self._status_msg(
                f"Refreshed at {now} | SPY: ${rec.get('entry', 0):.2f} | Signal: {rec['signal']} ({rec['confidence']}%)"
            )

        except Exception as e:
            log.exception("Error during update_data: %s", e)
            self._status_msg(f"Error refreshing: {e}")
        finally:
            self._is_fetching = False
            self.refresh_btn.setText("⟳  Refresh Now")
            self.refresh_btn.setEnabled(True)
            self.countdown_label.setText(render_big_countdown(self._countdown, False))


# ── Application entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QMainWindow, QWidget {
            background: #0b0f17;
        }
        QLabel {
            color: #e6edf3;
            font-family: 'Segoe UI', 'Inter', sans-serif;
            font-size: 14px;
        }
        QLabel#title {
            font-size: 20px;
            font-weight: 800;
            color: #58a6ff;
        }
        QLabel#updated_label {
            color: #8b949e;
            font-size: 12px;
        }
        QPushButton#refresh_btn {
            background: #1f6feb;
            color: #ffffff;
            font-weight: bold;
            border: 1px solid #388bfd;
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 13px;
        }
        QPushButton#refresh_btn:hover {
            background: #388bfd;
        }
        QPushButton#refresh_btn:pressed {
            background: #1158c7;
        }
        QPushButton#refresh_btn:disabled {
            background: #21262d;
            color: #484f58;
            border: 1px solid #30363d;
        }
        QScrollArea {
            border: none;
            background: transparent;
        }
        QStatusBar {
            background: #111827;
            color: #94a3b8;
            font-size: 12px;
            border-top: 1px solid #1f2937;
            padding: 4px;
        }
        QFrame#divider {
            color: #1e293b;
        }

        /* ── Tab Bar ─────────────────────────────────────────────────── */
        QTabWidget::pane {
            border: 1px solid #1e3a5f;
            border-radius: 6px;
            background: #0b0f17;
        }
        QTabBar::tab {
            background: #111827;
            color: #8b949e;
            font-size: 14px;
            font-weight: bold;
            padding: 10px 24px;
            border: 1px solid #1e3a5f;
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background: #0b0f17;
            color: #58a6ff;
            border-bottom: 2px solid #58a6ff;
        }
        QTabBar::tab:hover:!selected {
            background: #161b22;
            color: #c9d1d9;
        }

        /* ── Journal Section Frames ──────────────────────────────────── */
        QFrame#journal_section {
            background: #0d1117;
            border: 1.5px solid #1e3a5f;
            border-radius: 10px;
        }
        QLabel#section_title {
            font-size: 16px;
            font-weight: 800;
            color: #90caf9;
        }
        QLabel#month_label {
            font-size: 15px;
            color: #90caf9;
        }

        /* ── Journal Form Inputs ─────────────────────────────────────── */
        QTextEdit#journal_text {
            background: #111827;
            color: #e6edf3;
            border: 1.5px solid #1e3a5f;
            border-radius: 6px;
            padding: 8px;
            font-size: 13px;
            font-family: 'Segoe UI', sans-serif;
        }
        QTextEdit#journal_text:focus {
            border: 1.5px solid #388bfd;
        }
        QDateEdit#journal_input, QTimeEdit#journal_input, QDoubleSpinBox#journal_input,
        QSpinBox#journal_input, QLineEdit#journal_input,
        QComboBox#journal_input {
            background: #111827;
            color: #e6edf3;
            border: 1px solid #30363d;
            border-radius: 5px;
            padding: 5px 8px;
            font-size: 13px;
        }
        QDateEdit#journal_input:focus, QTimeEdit#journal_input:focus,
        QDoubleSpinBox#journal_input:focus, QSpinBox#journal_input:focus,
        QLineEdit#journal_input:focus {
            border: 1px solid #388bfd;
        }
        QComboBox#journal_input::drop-down {
            border: none;
            padding-right: 6px;
        }
        QComboBox#journal_input QAbstractItemView {
            background: #161b22;
            color: #e6edf3;
            border: 1px solid #30363d;
            selection-background-color: #1f6feb;
        }

        /* ── Journal Buttons ─────────────────────────────────────────── */
        QPushButton#save_btn {
            background: #238636;
            color: #ffffff;
            font-weight: bold;
            border: 1px solid #2ea043;
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 14px;
        }
        QPushButton#save_btn:hover {
            background: #2ea043;
        }
        QPushButton#save_btn:pressed {
            background: #196c2e;
        }
        QPushButton#journal_btn, QPushButton#nav_btn {
            background: #21262d;
            color: #c9d1d9;
            font-weight: bold;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 5px 10px;
            font-size: 13px;
        }
        QPushButton#journal_btn:hover, QPushButton#nav_btn:hover {
            background: #30363d;
            color: #ffffff;
        }
    """)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
