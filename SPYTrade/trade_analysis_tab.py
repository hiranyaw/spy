"""trade_analysis_tab.py — Trade Analysis, Condition Tagging & Performance Charts.

Provides:
  • Left Panel: Filterable list/table of trades with CSV Upload / Export / Add buttons.
  • Right Panel: Detailed trade classification editor (B-Trade, 9/21 Cross, Early Exit, Direction Right/Wrong).
  • Bottom / Summary Section: Condition Win Rate % graph (Matplotlib dark theme) and metric summary cards.
"""

from __future__ import annotations

import calendar
import csv
import datetime
import logging
from typing import Any

from PySide6.QtCore import Qt, QDate, QTime, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QDoubleSpinBox, QLineEdit, QComboBox,
    QDateEdit, QTimeEdit, QScrollArea, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QCheckBox, QRadioButton, QButtonGroup, QSplitter, QGroupBox,
    QSizePolicy,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import trade_store

log = logging.getLogger(__name__)


class TradeConditionCanvas(FigureCanvas):
    """Dark-themed Matplotlib canvas for rendering condition win-rate bar charts."""

    def __init__(self, parent=None, width=8, height=3.2, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor="#0d1117")
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.22)

    def render_stats(self, stats: dict[str, Any], title_suffix: str = "", view_mode: str = "All Conditions & Rules"):
        self.ax.clear()
        self.ax.set_facecolor("#0d1117")

        zero_stat = {"win_rate": 0.0, "count": 0, "total_pnl": 0.0, "wins": 0, "losses": 0}

        if view_mode == "Core Setups Only":
            categories = [
                ("All Trades", stats["all"]),
                ("Jimmy Rec", stats.get("jimmy_recommended", zero_stat)),
                ("B-Trade", stats["b_trade"]),
                ("9/21 Cross", stats["cross_9_21"]),
                ("Follow 9 Up", stats.get("followed_9_up", zero_stat)),
                ("Follow 9 Dn", stats.get("followed_9_down", zero_stat)),
                ("Other", stats.get("other", zero_stat)),
            ]
        elif view_mode == "Checklist Confluences Only":
            categories = [
                ("All Trades", stats["all"]),
                ("AK MACD", stats.get("ak_macd_bb", zero_stat)),
                ("RSI Trend", stats.get("rsi_trendline", zero_stat)),
                ("HSM Buy", stats.get("hiranya_buy", zero_stat)),
                ("HSM Sell", stats.get("hiranya_sell", zero_stat)),
                ("VWAP Align", stats.get("vwap_aligned", zero_stat)),
                ("QQQ Confl", stats.get("qqq_confluence", zero_stat)),
                ("ADD Breadth", stats.get("add_confluence", zero_stat)),
                ("High Confl", stats.get("high_confluence", zero_stat)),
            ]
        elif view_mode == "Execution & Direction Only":
            categories = [
                ("All Trades", stats["all"]),
                ("VWAP Exit", stats.get("vwap_touch_exit", zero_stat)),
                ("Early Exit", stats["early_exit"]),
                ("Normal Exit", stats["normal_exit"]),
                ("Dir Right", stats["direction_right"]),
                ("Dir Wrong", stats["direction_wrong"]),
            ]
        else:  # All Conditions & Rules
            categories = [
                ("All Trades", stats["all"]),
                ("Jimmy Rec", stats.get("jimmy_recommended", zero_stat)),
                ("B-Trade", stats["b_trade"]),
                ("9/21 Cross", stats["cross_9_21"]),
                ("Follow 9 Up", stats.get("followed_9_up", zero_stat)),
                ("Follow 9 Dn", stats.get("followed_9_down", zero_stat)),
                ("AK MACD", stats.get("ak_macd_bb", zero_stat)),
                ("RSI Cross", stats.get("rsi_trendline", zero_stat)),
                ("HSM Buy", stats.get("hiranya_buy", zero_stat)),
                ("HSM Sell", stats.get("hiranya_sell", zero_stat)),
                ("VWAP Align", stats.get("vwap_aligned", zero_stat)),
                ("QQQ Confl", stats.get("qqq_confluence", zero_stat)),
                ("ADD Breadth", stats.get("add_confluence", zero_stat)),
                ("High Confl", stats.get("high_confluence", zero_stat)),
                ("VWAP Exit", stats.get("vwap_touch_exit", zero_stat)),
                ("Early Exit", stats["early_exit"]),
                ("Dir Right", stats["direction_right"]),
            ]

        labels = [c[0] for c in categories]
        win_rates = [c[1]["win_rate"] for c in categories]
        counts = [c[1]["count"] for c in categories]
        pnls = [c[1]["total_pnl"] for c in categories]
        wins = [c[1]["wins"] for c in categories]
        losses = [c[1]["losses"] for c in categories]

        x = range(len(labels))
        
        # Color bars based on condition and win rate
        bar_colors = []
        for label, wr, count in zip(labels, win_rates, counts):
            if count == 0:
                bar_colors.append("#21262d")
            elif any(w in label for w in ("Right", "Jimmy", "B-Trade", "9/21 Cross", "Follow 9 Up", "High Confl", "HSM Buy")):
                bar_colors.append("#00e676" if wr >= 50 else "#ff9800")
            elif any(w in label for w in ("Wrong", "Early Exit", "Follow 9 Dn", "HSM Sell")):
                bar_colors.append("#f44336" if wr < 50 else "#ff9800")
            elif any(w in label for w in ("VWAP Exit", "VWAP Align", "AK MACD", "RSI", "QQQ", "ADD")):
                bar_colors.append("#00e5ff" if wr >= 50 else "#ff9800")
            elif "Other" in label:
                bar_colors.append("#b388ff" if wr >= 50 else "#ff9800")
            else:
                bar_colors.append("#58a6ff" if wr >= 50 else "#ff9800")

        bars = self.ax.bar(x, win_rates, color=bar_colors, width=0.6, edgecolor="#30363d", linewidth=1.2)

        # Baseline at 50%
        self.ax.axhline(50, color="#8b949e", linestyle="--", linewidth=0.8, alpha=0.6, label="50% Win Rate")

        # Configure axis styles
        self.ax.set_ylim(0, 115)
        self.ax.set_ylabel("Win Rate (%)", color="#c9d1d9", fontsize=10, fontweight="bold")
        self.ax.set_title(
            f"Win Rate % by Trade Condition {title_suffix}",
            color="#90caf9",
            fontsize=12,
            fontweight="bold",
            pad=10,
        )
        self.ax.set_xticks(list(x))
        self.ax.set_xticklabels(labels, color="#c9d1d9", fontsize=9, fontweight="bold", rotation=15, ha="right")
        self.ax.tick_params(colors="#8b949e", which="both")
        self.ax.grid(axis="y", color="#21262d", linestyle=":", linewidth=0.8)

        for spine in self.ax.spines.values():
            spine.set_color("#30363d")

        # Value annotations on top of each bar
        for idx, bar in enumerate(bars):
            h = bar.get_height()
            cnt = counts[idx]
            pnl_val = pnls[idx]
            w = wins[idx]
            l = losses[idx]

            if cnt == 0:
                self.ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    5,
                    "No Data",
                    ha="center",
                    va="bottom",
                    color="#6e7681",
                    fontsize=8,
                    fontweight="bold",
                )
            else:
                pnl_str = f"+${pnl_val:,.0f}" if pnl_val >= 0 else f"-${abs(pnl_val):,.0f}"
                pnl_col = "#00e676" if pnl_val >= 0 else "#f44336"
                
                # Main win rate text
                self.ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    h + 2,
                    f"{h:.1f}%",
                    ha="center",
                    va="bottom",
                    color="#ffffff",
                    fontsize=9,
                    fontweight="bold",
                )
                # Subtext with count and PnL
                self.ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    min(h / 2.0, 30),
                    f"{w}W / {l}L\n{pnl_str}",
                    ha="center",
                    va="center",
                    color="#ffffff",
                    fontsize=7.5,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#0a0e14", edgecolor="#30363d", alpha=0.85),
                )

        self.fig.tight_layout()
        self.draw()


class TradeAnalysisTab(QWidget):
    """Main tab for uploading, classifying, and analyzing individual trades."""

    trade_updated = Signal()

    def __init__(self, status_callback=None, parent=None):
        super().__init__(parent)
        self._status_cb = status_callback
        self._current_trade_id: str | None = None
        self._show_all_months = False

        today = datetime.date.today()
        self._cur_year = today.year
        self._cur_month = today.month

        self._build_ui()
        self._load_and_refresh()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 8, 10, 8)
        root_layout.setSpacing(8)

        # ── 1. Top Control Bar ────────────────────────────────────────────────
        top_bar = QFrame()
        top_bar.setObjectName("journal_section")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 8, 12, 8)
        top_layout.setSpacing(10)

        # Month Navigation
        self.prev_btn = QPushButton("◄")
        self.prev_btn.setObjectName("nav_btn")
        self.prev_btn.setFixedSize(34, 28)
        self.prev_btn.clicked.connect(self._prev_month)
        top_layout.addWidget(self.prev_btn)

        self.month_lbl = QLabel()
        self.month_lbl.setObjectName("month_label")
        self.month_lbl.setFixedWidth(160)
        self.month_lbl.setAlignment(Qt.AlignCenter)
        top_layout.addWidget(self.month_lbl)

        self.next_btn = QPushButton("►")
        self.next_btn.setObjectName("nav_btn")
        self.next_btn.setFixedSize(34, 28)
        self.next_btn.clicked.connect(self._next_month)
        top_layout.addWidget(self.next_btn)

        # All Months toggle
        self.all_months_cb = QCheckBox("Show All History")
        self.all_months_cb.setStyleSheet("color:#90caf9;font-weight:bold;font-size:12px;")
        self.all_months_cb.toggled.connect(self._on_all_months_toggled)
        top_layout.addWidget(self.all_months_cb)

        top_layout.addStretch()

        # Action Buttons
        self.upload_btn = QPushButton("📁 Upload Trades (CSV)")
        self.upload_btn.setObjectName("journal_btn")
        self.upload_btn.setToolTip("Import trades from a CSV file (e.g. broker export)")
        self.upload_btn.clicked.connect(self._on_upload_csv)
        top_layout.addWidget(self.upload_btn)

        self.add_new_btn = QPushButton("➕ Add Trade")
        self.add_new_btn.setObjectName("journal_btn")
        self.add_new_btn.clicked.connect(self._on_add_new_clicked)
        top_layout.addWidget(self.add_new_btn)

        self.export_btn = QPushButton("💾 Export CSV")
        self.export_btn.setObjectName("journal_btn")
        self.export_btn.clicked.connect(self._on_export_csv)
        top_layout.addWidget(self.export_btn)

        root_layout.addWidget(top_bar)

        # ── 2. Splitter for Trades Table (Left) and Editor (Right) ───────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Left Panel: Trade List & Filters ──────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(6)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("journal_input")
        self.search_edit.setPlaceholderText("🔍 Search Symbol, Notes, Tag...")
        self.search_edit.textChanged.connect(self._load_table_data)
        filter_row.addWidget(self.search_edit)

        self.filter_combo = QComboBox()
        self.filter_combo.setObjectName("journal_input")
        self.filter_combo.addItems([
            "All Setups & Confluences",
            "Jimmy Recommended Only",
            "B-Trades Only",
            "9/21 Cross Only",
            "B-Trade + 9/21 Only",
            "Followed 9 EMA (Up)",
            "Followed 9 EMA (Down)",
            "Hiranya Signal: BUY Only",
            "Hiranya Signal: SELL Only",
            "AK MACD Confirmed",
            "RSI Trendline Cross",
            "VWAP Aligned",
            "QQQ Confluence",
            "ADD Breadth Confluence",
            "ADD Positive (+ Breadth)",
            "ADD Negative (- Breadth)",
            "High Confluence (4+ Rules)",
            "Exit: VWAP Touch Only",
            "Early Exits Only",
            "Other Setup Only",
            "Direction Right Only",
            "Direction Wrong Only",
            "Wins Only (+$)",
            "Losses Only (-$)",
        ])
        self.filter_combo.currentIndexChanged.connect(self._load_table_data)
        filter_row.addWidget(self.filter_combo)

        left_layout.addLayout(filter_row)

        # Trades Table
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "Time Window", "Symbol", "Direction / Side", "Gross ($)", "Cost ($)", "Net Realized P&L ($)", "Core Setup", "Confluences", "Early", "Direction", "Outcome"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget {
                background: #0d1117;
                border: 1.5px solid #1e3a5f;
                border-radius: 8px;
                gridline-color: #1e293b;
                color: #e6edf3;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 4px 6px;
                border-bottom: 1px solid #162032;
            }
            QTableWidget::item:selected {
                background: #1f6feb;
                color: #ffffff;
            }
            QHeaderView::section {
                background: #111d2e;
                color: #90caf9;
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-bottom: 2px solid #1e3a5f;
                padding: 6px 4px;
            }
        """)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        left_layout.addWidget(self.table)

        splitter.addWidget(left_widget)

        # ── Right Panel: Trade Classification & Details Editor ────────────────
        right_frame = QFrame()
        right_frame.setObjectName("journal_section")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(14, 12, 14, 12)
        right_layout.setSpacing(10)

        editor_title = QLabel("🎯 <b>Trade Classification & Details</b>")
        editor_title.setObjectName("section_title")
        right_layout.addWidget(editor_title)

        # Date & Time Row
        dt_row = QHBoxLayout()
        dt_row.setSpacing(8)

        dt_row.addWidget(QLabel("<b>Date:</b>"))
        self.edit_date = QDateEdit()
        self.edit_date.setCalendarPopup(True)
        self.edit_date.setDisplayFormat("yyyy-MM-dd")
        self.edit_date.setDate(QDate.currentDate())
        self.edit_date.setObjectName("journal_input")
        dt_row.addWidget(self.edit_date)

        dt_row.addWidget(QLabel("<b>Time:</b>"))
        self.edit_time = QTimeEdit()
        self.edit_time.setDisplayFormat("HH:mm:ss")
        self.edit_time.setTime(QTime(9, 30, 0))
        self.edit_time.setObjectName("journal_input")
        dt_row.addWidget(self.edit_time)

        right_layout.addLayout(dt_row)

        # Symbol, Side, Qty
        sym_row = QHBoxLayout()
        sym_row.setSpacing(8)

        sym_row.addWidget(QLabel("<b>Symbol:</b>"))
        self.edit_symbol = QLineEdit("SPY")
        self.edit_symbol.setObjectName("journal_input")
        self.edit_symbol.setFixedWidth(90)
        sym_row.addWidget(self.edit_symbol)

        sym_row.addWidget(QLabel("<b>Side:</b>"))
        self.edit_side = QComboBox()
        self.edit_side.setObjectName("journal_input")
        self.edit_side.addItems(["BUY / CALL", "SELL / PUT", "LONG", "SHORT"])
        sym_row.addWidget(self.edit_side)

        sym_row.addWidget(QLabel("<b>Qty:</b>"))
        self.edit_qty = QDoubleSpinBox()
        self.edit_qty.setObjectName("journal_input")
        self.edit_qty.setRange(0.01, 100000.0)
        self.edit_qty.setValue(1.0)
        self.edit_qty.setFixedWidth(75)
        self.edit_qty.valueChanged.connect(self._on_qty_changed)
        sym_row.addWidget(self.edit_qty)

        right_layout.addLayout(sym_row)

        # Entry Price, Exit Price
        price_row = QHBoxLayout()
        price_row.setSpacing(8)

        price_row.addWidget(QLabel("<b>Entry:</b>"))
        self.edit_entry = QDoubleSpinBox()
        self.edit_entry.setObjectName("journal_input")
        self.edit_entry.setRange(0.0, 999999.0)
        self.edit_entry.setDecimals(2)
        self.edit_entry.setPrefix("$ ")
        price_row.addWidget(self.edit_entry)

        price_row.addWidget(QLabel("<b>Exit:</b>"))
        self.edit_exit = QDoubleSpinBox()
        self.edit_exit.setObjectName("journal_input")
        self.edit_exit.setRange(0.0, 999999.0)
        self.edit_exit.setDecimals(2)
        self.edit_exit.setPrefix("$ ")
        price_row.addWidget(self.edit_exit)

        right_layout.addLayout(price_row)

        # Gross P&L, Trade Cost ($1.00 * qty), and Net P&L
        pnl_row = QHBoxLayout()
        pnl_row.setSpacing(8)

        pnl_row.addWidget(QLabel("<b>Gross P&L:</b>"))
        self.edit_pnl = QDoubleSpinBox()
        self.edit_pnl.setObjectName("journal_input")
        self.edit_pnl.setRange(-999999.0, 999999.0)
        self.edit_pnl.setDecimals(2)
        self.edit_pnl.setPrefix("$ ")
        self.edit_pnl.valueChanged.connect(self._update_net_pnl_preview)
        pnl_row.addWidget(self.edit_pnl)

        pnl_row.addWidget(QLabel("<b>Cost:</b>"))
        self.edit_cost = QDoubleSpinBox()
        self.edit_cost.setObjectName("journal_input")
        self.edit_cost.setRange(0.0, 9999.0)
        self.edit_cost.setDecimals(2)
        self.edit_cost.setPrefix("$ ")
        self.edit_cost.setValue(1.0)
        self.edit_cost.setFixedWidth(80)
        self.edit_cost.setToolTip("Trade commission / exchange cost ($1.00 per contract/qty)")
        self.edit_cost.valueChanged.connect(self._update_net_pnl_preview)
        pnl_row.addWidget(self.edit_cost)

        self.lbl_net_pnl = QLabel("<b>Net:</b> $ -1.00")
        self.lbl_net_pnl.setStyleSheet("color:#ff9800;font-size:12px;font-weight:bold;")
        pnl_row.addWidget(self.lbl_net_pnl)

        right_layout.addLayout(pnl_row)

        # ── PROMINENT TRADE CONDITIONS SELECTION ─────────────────────────────
        cond_box = QGroupBox("🏷️ Trade Conditions & Strategy Rules")
        cond_box.setStyleSheet("""
            QGroupBox {
                border: 1.5px solid #238636;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
                font-weight: bold;
                color: #58a6ff;
                background: #091320;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
            }
            QCheckBox {
                color: #e6edf3;
                font-size: 13px;
                font-weight: bold;
                padding: 3px;
            }
            QCheckBox:hover {
                color: #58a6ff;
            }
            QRadioButton {
                color: #e6edf3;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        cond_layout = QVBoxLayout(cond_box)
        cond_layout.setSpacing(8)

        # Two-column layout: Core Setup Triggers (Left) and Checklist Indicator Confluences (Right)
        cond_cols = QHBoxLayout()
        cond_cols.setSpacing(12)

        # ── Left Column: Core Setup Triggers ──
        left_col = QVBoxLayout()
        left_col.setSpacing(5)
        lbl_setups = QLabel("<b>📌 Core Setup Triggers:</b>")
        lbl_setups.setStyleSheet("color:#58a6ff;font-size:11px;")
        left_col.addWidget(lbl_setups)

        self.cb_jimmy_rec = QCheckBox("🌟  Jimmy Recommended")
        self.cb_b_trade = QCheckBox("🏷️  Is B-Trade Setup")
        self.cb_9_21 = QCheckBox("⚡  9 / 21 EMA Cross")
        self.cb_followed_9_up = QCheckBox("📈  Followed 9 EMA (Up)")
        self.cb_followed_9_down = QCheckBox("📉  Followed 9 EMA (Down)")

        left_col.addWidget(self.cb_jimmy_rec)
        left_col.addWidget(self.cb_b_trade)
        left_col.addWidget(self.cb_9_21)
        left_col.addWidget(self.cb_followed_9_up)
        left_col.addWidget(self.cb_followed_9_down)

        # Other Setup row with checkbox and specify text input
        other_row = QHBoxLayout()
        other_row.setSpacing(6)
        self.cb_other = QCheckBox("📦 Other:")
        self.cb_other.toggled.connect(self._on_other_cb_toggled)
        self.edit_other = QLineEdit()
        self.edit_other.setObjectName("journal_input")
        self.edit_other.setPlaceholderText("Specify other setup...")
        self.edit_other.textChanged.connect(self._on_other_text_changed)
        other_row.addWidget(self.cb_other)
        other_row.addWidget(self.edit_other)
        left_col.addLayout(other_row)
        cond_cols.addLayout(left_col, stretch=1)

        # ── Right Column: Checklist Indicator Confluences ──
        right_col = QVBoxLayout()
        right_col.setSpacing(5)
        lbl_confl = QLabel("<b>🎯 Checklist Confluences:</b>")
        lbl_confl.setStyleSheet("color:#7ee787;font-size:11px;")
        right_col.addWidget(lbl_confl)

        self.cb_ak_macd = QCheckBox("📊  AK MACD BB (Zone)")
        self.cb_rsi_trendline = QCheckBox("📉  RSI Cross Trendline")

        # Hiranya Signal Monitor: Buy or Sell selector
        hsm_row = QHBoxLayout()
        hsm_row.setSpacing(6)
        hsm_lbl = QLabel("🎯 <b>HSM Signal:</b>")
        hsm_lbl.setStyleSheet("color:#e6edf3;font-size:11px;")
        self.combo_hiranya = QComboBox()
        self.combo_hiranya.setObjectName("journal_input")
        self.combo_hiranya.addItems(["— None / Off —", "🟢 BUY (Bullish Signal)", "🔴 SELL (Bearish Signal)"])
        self.combo_hiranya.currentIndexChanged.connect(self._update_confluence_score_display)
        hsm_row.addWidget(hsm_lbl)
        hsm_row.addWidget(self.combo_hiranya)
        right_col.addLayout(hsm_row)

        self.cb_vwap = QCheckBox("🌊  VWAP Aligned / Cross")
        self.cb_qqq = QCheckBox("🧭  QQQ Direction Confl")

        # NYSE $ADD Breadth with numeric level input
        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.cb_add = QCheckBox("📶  NYSE $ADD:")
        self.cb_add.toggled.connect(self._on_add_cb_toggled)
        self.edit_add_val = QLineEdit()
        self.edit_add_val.setObjectName("journal_input")
        self.edit_add_val.setPlaceholderText("e.g. +1250, -850")
        self.edit_add_val.setFixedWidth(115)
        self.edit_add_val.textChanged.connect(self._on_add_text_changed)
        add_row.addWidget(self.cb_add)
        add_row.addWidget(self.edit_add_val)
        add_row.addStretch()

        right_col.addWidget(self.cb_ak_macd)
        right_col.addWidget(self.cb_rsi_trendline)
        right_col.addWidget(self.cb_vwap)
        right_col.addWidget(self.cb_qqq)
        right_col.addLayout(add_row)

        for cb in [self.cb_jimmy_rec, self.cb_b_trade, self.cb_9_21, self.cb_followed_9_up, self.cb_followed_9_down, self.cb_ak_macd, self.cb_rsi_trendline, self.cb_vwap, self.cb_qqq, self.cb_add]:
            cb.toggled.connect(self._update_confluence_score_display)

        cond_cols.addLayout(right_col, stretch=1)
        cond_layout.addLayout(cond_cols)

        # Confluence Score Badge
        self.confluence_badge = QLabel("✨ <b>Confluence Score:</b> 0 / 6 Rules Aligned")
        self.confluence_badge.setStyleSheet(
            "background:#0d1b2a;border:1px solid #1e3a5f;border-radius:4px;padding:4px 8px;color:#8b949e;font-size:11px;"
        )
        cond_layout.addWidget(self.confluence_badge)

        self.cb_early_exit = QCheckBox("⏱️  Early Exit (Cut before Target / Stop)")
        cond_layout.addWidget(self.cb_early_exit)

        # Early Exit Amount Option Buttons ($20, $50, $100, $200)
        early_amt_row = QHBoxLayout()
        early_amt_row.setSpacing(6)
        early_amt_lbl = QLabel("⏱️ <b>Amount Made:</b>")
        early_amt_lbl.setStyleSheet("color:#f85149;font-size:11px;")
        early_amt_row.addWidget(early_amt_lbl)

        self.btn_early_20 = QPushButton("$20")
        self.btn_early_50 = QPushButton("$50")
        self.btn_early_100 = QPushButton("$100")
        self.btn_early_200 = QPushButton("$200")
        
        for btn in [self.btn_early_20, self.btn_early_50, self.btn_early_100, self.btn_early_200]:
            btn.setFixedHeight(24)
            btn.setStyleSheet("background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:4px;font-weight:bold;font-size:11px;")
            early_amt_row.addWidget(btn)

        self.btn_early_20.clicked.connect(lambda: self._set_early_amount(20))
        self.btn_early_50.clicked.connect(lambda: self._set_early_amount(50))
        self.btn_early_100.clicked.connect(lambda: self._set_early_amount(100))
        self.btn_early_200.clicked.connect(lambda: self._set_early_amount(200))

        self.edit_early_amt = QDoubleSpinBox()
        self.edit_early_amt.setRange(0.0, 99999.0)
        self.edit_early_amt.setPrefix("$ ")
        self.edit_early_amt.setDecimals(2)
        self.edit_early_amt.setFixedWidth(75)
        self.edit_early_amt.setObjectName("journal_input")
        early_amt_row.addWidget(self.edit_early_amt)
        early_amt_row.addStretch()
        cond_layout.addLayout(early_amt_row)

        # Direction Selection (Radio buttons)
        dir_label = QLabel("🧭 <b>Trade Direction:</b>")
        dir_label.setStyleSheet("color:#90caf9;font-size:12px;margin-top:4px;")
        cond_layout.addWidget(dir_label)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(16)
        self.radio_dir_right = QRadioButton("✅ Right Direction (Followed Plan)")
        self.radio_dir_wrong = QRadioButton("❌ Wrong Direction (Opposite / Against Plan)")
        self.radio_dir_right.setChecked(True)

        self.dir_group = QButtonGroup(self)
        self.dir_group.addButton(self.radio_dir_right)
        self.dir_group.addButton(self.radio_dir_wrong)

        dir_row.addWidget(self.radio_dir_right)
        dir_row.addWidget(self.radio_dir_wrong)
        dir_row.addStretch()
        cond_layout.addLayout(dir_row)

        # Outcome / Exit Reason Selection (Radio buttons)
        exit_label = QLabel("🏁 <b>How Trade Ended:</b>")
        exit_label.setStyleSheet("color:#ffb74d;font-size:12px;margin-top:4px;")
        cond_layout.addWidget(exit_label)

        exit_row = QHBoxLayout()
        exit_row.setSpacing(12)
        self.radio_exit_target = QRadioButton("🎯 Hit Target")
        self.radio_exit_stop = QRadioButton("🛑 Hit Stop Loss")
        self.radio_exit_vwap = QRadioButton("🌊 Exit: VWAP Touch")
        self.radio_exit_early = QRadioButton("⏱️ Early Exit")
        self.radio_exit_be = QRadioButton("⚡ Breakeven")
        self.radio_exit_target.setChecked(True)

        self.exit_group = QButtonGroup(self)
        self.exit_group.addButton(self.radio_exit_target)
        self.exit_group.addButton(self.radio_exit_stop)
        self.exit_group.addButton(self.radio_exit_vwap)
        self.exit_group.addButton(self.radio_exit_early)
        self.exit_group.addButton(self.radio_exit_be)

        exit_row.addWidget(self.radio_exit_target)
        exit_row.addWidget(self.radio_exit_stop)
        exit_row.addWidget(self.radio_exit_vwap)
        exit_row.addWidget(self.radio_exit_early)
        exit_row.addWidget(self.radio_exit_be)
        exit_row.addStretch()
        cond_layout.addLayout(exit_row)

        right_layout.addWidget(cond_box)

        # Notes / Commentary
        right_layout.addWidget(QLabel("<b>Trade Notes / Rationale:</b>"))
        self.edit_notes = QTextEdit()
        self.edit_notes.setObjectName("journal_text")
        self.edit_notes.setPlaceholderText("Execution notes, setup confluence, emotion, lessons...")
        self.edit_notes.setMaximumHeight(90)
        right_layout.addWidget(self.edit_notes)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.save_trade_btn = QPushButton("💾  Save Trade Classification")
        self.save_trade_btn.setObjectName("save_btn")
        self.save_trade_btn.clicked.connect(self._on_save_trade)
        btn_row.addWidget(self.save_trade_btn)

        self.del_trade_btn = QPushButton("🗑 Delete")
        self.del_trade_btn.setObjectName("journal_btn")
        self.del_trade_btn.setStyleSheet("background:#381313;color:#ff8b8b;border-color:#632323;")
        self.del_trade_btn.clicked.connect(self._on_delete_trade)
        btn_row.addWidget(self.del_trade_btn)

        self.clear_trade_btn = QPushButton("🔄 Reset")
        self.clear_trade_btn.setObjectName("journal_btn")
        self.clear_trade_btn.clicked.connect(self._clear_editor)
        btn_row.addWidget(self.clear_trade_btn)

        right_layout.addLayout(btn_row)
        splitter.addWidget(right_frame)

        # Set initial splitter proportions (55% left table, 45% right editor)
        splitter.setSizes([550, 430])
        root_layout.addWidget(splitter, stretch=2)

        # ── 3. Bottom Performance Graph & Condition Cards ────────────────────
        bottom_frame = QFrame()
        bottom_frame.setObjectName("journal_section")
        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(12, 10, 12, 10)
        bottom_layout.setSpacing(8)

        # Metric summary cards banner
        self.cards_label = QLabel()
        self.cards_label.setTextFormat(Qt.RichText)
        self.cards_label.setWordWrap(True)
        bottom_layout.addWidget(self.cards_label)

        # Chart filter row
        chart_hdr = QHBoxLayout()
        chart_hdr.setSpacing(8)
        chart_title = QLabel("📊 <b>Condition Win Rate % & Performance Breakdown</b>")
        chart_title.setStyleSheet("color:#90caf9;font-size:12px;font-weight:bold;")
        chart_hdr.addWidget(chart_title)
        chart_hdr.addStretch()

        chart_hdr.addWidget(QLabel("<span style='color:#8b949e;font-size:11px;font-weight:bold;'>Chart Focus:</span>"))
        self.chart_filter_combo = QComboBox()
        self.chart_filter_combo.setObjectName("journal_input")
        self.chart_filter_combo.addItems([
            "All Conditions & Rules",
            "Core Setups Only",
            "Checklist Confluences Only",
            "Execution & Direction Only",
        ])
        self.chart_filter_combo.currentIndexChanged.connect(self._on_chart_filter_changed)
        chart_hdr.addWidget(self.chart_filter_combo)
        bottom_layout.addLayout(chart_hdr)

        # Matplotlib Win Rate Graph
        self.chart_canvas = TradeConditionCanvas(self, width=8, height=3.0)
        bottom_layout.addWidget(self.chart_canvas)

        root_layout.addWidget(bottom_frame, stretch=1)

    # ── Month Navigation ──────────────────────────────────────────────────────

    def _prev_month(self):
        if self._cur_month == 1:
            self._cur_month = 12
            self._cur_year -= 1
        else:
            self._cur_month -= 1
        self._load_and_refresh()

    def _next_month(self):
        if self._cur_month == 12:
            self._cur_month = 1
            self._cur_year += 1
        else:
            self._cur_month += 1
        self._load_and_refresh()

    def _on_all_months_toggled(self, checked: bool):
        self._show_all_months = checked
        self.prev_btn.setEnabled(not checked)
        self.next_btn.setEnabled(not checked)
        self._load_and_refresh()

    # ── Data Loading & Refresh ────────────────────────────────────────────────

    def _load_and_refresh(self):
        if self._show_all_months:
            self.month_lbl.setText("<b style='color:#58a6ff;font-size:14px'>🌐 Entire History</b>")
            stats_title = "(All History)"
            year_filter = None
            month_filter = None
        else:
            m_name = calendar.month_name[self._cur_month]
            self.month_lbl.setText(f"<b style='color:#58a6ff;font-size:14px'>{m_name} {self._cur_year}</b>")
            stats_title = f"({m_name} {self._cur_year})"
            year_filter = self._cur_year
            month_filter = self._cur_month

        self._load_table_data()

        # Compute & Render Stats and Graph
        stats = trade_store.get_condition_stats(year=year_filter, month=month_filter)
        self._render_metric_cards(stats)
        view_mode = self.chart_filter_combo.currentText() if hasattr(self, "chart_filter_combo") else "All Conditions & Rules"
        self.chart_canvas.render_stats(stats, title_suffix=stats_title, view_mode=view_mode)

    def _on_qty_changed(self, val: float):
        if not self._current_trade_id:
            self.edit_cost.setValue(round(val * 1.0, 2))

    def _update_net_pnl_preview(self):
        gross = self.edit_pnl.value()
        cost = self.edit_cost.value()
        net = gross - cost
        sign = "+" if net >= 0 else ""
        col = "#00e676" if net >= 0 else "#f44336"
        self.lbl_net_pnl.setText(f"<b>Net:</b> <span style='color:{col};font-weight:bold;'>{sign}${net:,.2f}</span>")

    def _load_table_data(self):
        year_filter = None if self._show_all_months else self._cur_year
        month_filter = None if self._show_all_months else self._cur_month
        search = self.search_edit.text().strip()
        filter_mode = self.filter_combo.currentText()

        trades = trade_store.get_trades(
            year=year_filter,
            month=month_filter,
            search_query=search,
        )

        # Apply dropdown filter
        if filter_mode == "Jimmy Recommended Only":
            trades = [t for t in trades if t.get("is_jimmy_recommended", False)]
        elif filter_mode == "B-Trades Only":
            trades = [t for t in trades if t.get("is_b_trade", False)]
        elif filter_mode == "9/21 Cross Only":
            trades = [t for t in trades if t.get("is_9_21_cross", False)]
        elif filter_mode == "B-Trade + 9/21 Only":
            trades = [t for t in trades if t.get("is_b_trade", False) and t.get("is_9_21_cross", False)]
        elif filter_mode in ("Followed 9 EMA (Up)", "Full back 9 (Uptrend)"):
            trades = [t for t in trades if t.get("is_followed_9_up", False) or t.get("is_fullback_uptrend", False)]
        elif filter_mode in ("Followed 9 EMA (Down)", "Full back 9 (Downtrend)"):
            trades = [t for t in trades if t.get("is_followed_9_down", False) or t.get("is_fullback_downtrend", False)]
        elif filter_mode == "Hiranya Signal: BUY Only":
            trades = [t for t in trades if t.get("is_hiranya_buy", False) or str(t.get("hiranya_signal_dir", "")).upper() == "BUY"]
        elif filter_mode == "Hiranya Signal: SELL Only":
            trades = [t for t in trades if t.get("is_hiranya_sell", False) or str(t.get("hiranya_signal_dir", "")).upper() == "SELL"]
        elif filter_mode == "AK MACD Confirmed":
            trades = [t for t in trades if t.get("is_ak_macd_bb", False)]
        elif filter_mode == "RSI Trendline Cross":
            trades = [t for t in trades if t.get("is_rsi_trendline", False)]
        elif filter_mode == "Hiranya Signal Confirmed":
            trades = [t for t in trades if t.get("is_hiranya_signal", False)]
        elif filter_mode == "VWAP Aligned":
            trades = [t for t in trades if t.get("is_vwap_aligned", False)]
        elif filter_mode == "QQQ Confluence":
            trades = [t for t in trades if t.get("is_qqq_confluence", False)]
        elif filter_mode == "ADD Breadth Confluence":
            trades = [t for t in trades if t.get("is_add_confluence", False) or t.get("add_value") is not None]
        elif filter_mode == "ADD Positive (+ Breadth)":
            trades = [t for t in trades if t.get("add_value") is not None and float(t["add_value"]) > 0]
        elif filter_mode == "ADD Negative (- Breadth)":
            trades = [t for t in trades if t.get("add_value") is not None and float(t["add_value"]) < 0]
        elif filter_mode == "High Confluence (4+ Rules)":
            def _score(tr):
                keys = ("is_ak_macd_bb", "is_rsi_trendline", "is_hiranya_signal", "is_vwap_aligned", "is_qqq_confluence", "is_add_confluence")
                return sum(1 for k in keys if tr.get(k, False))
            trades = [t for t in trades if _score(tr) >= 4]
        elif filter_mode == "Exit: VWAP Touch Only":
            trades = [t for t in trades if str(t.get("exit_reason", "")).upper() == "VWAP_TOUCH" or t.get("is_vwap_touch_exit", False)]
        elif filter_mode == "Early Exits Only":
            trades = [t for t in trades if t.get("early_exit", False)]
        elif filter_mode == "Other Setup Only":
            trades = [t for t in trades if t.get("is_other", False)]
        elif filter_mode == "Direction Right Only":
            trades = [t for t in trades if t.get("direction_right", True)]
        elif filter_mode == "Direction Wrong Only":
            trades = [t for t in trades if not t.get("direction_right", True)]
        elif filter_mode == "Wins Only (+$)":
            trades = [t for t in trades if (float(t.get("pnl", 0.0)) - float(t.get("trade_cost", float(t.get("qty", 1.0)) * 1.0))) > 0]
        elif filter_mode == "Losses Only (-$)":
            trades = [t for t in trades if (float(t.get("pnl", 0.0)) - float(t.get("trade_cost", float(t.get("qty", 1.0)) * 1.0))) < 0]

        self.table.blockSignals(True)
        self.table.setRowCount(len(trades))

        selected_row_idx = -1

        for r, t in enumerate(trades):
            t_id = t.get("id", "")
            if t_id == self._current_trade_id:
                selected_row_idx = r

            # Col 0: Time Window
            exit_val = t.get("exit_time")
            if exit_val:
                exit_str = str(exit_val)
                exit_t = exit_str.split(" ")[1][:5] if " " in exit_str else exit_str[:5]
                dt_str = f"{t.get('date', '')} {t.get('time', '')[:5]}-{exit_t}"
            else:
                dt_str = f"{t.get('date', '')} {t.get('time', '')[:5]}"
            item_dt = QTableWidgetItem(dt_str)
            item_dt.setData(Qt.UserRole, t_id)
            self.table.setItem(r, 0, item_dt)

            # Col 1: Symbol
            item_sym = QTableWidgetItem(t.get("symbol", "SPY"))
            item_sym.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.table.setItem(r, 1, item_sym)

            # Col 2: Direction / Side
            dir_str = t.get("direction") or ("SHORT" if "PUT" in str(t.get("option_type", "")).upper() else "LONG")
            opt_type = t.get("option_type", "")
            side_str = f"{dir_str} ({opt_type})" if opt_type else dir_str
            item_side = QTableWidgetItem(side_str)
            if "BUY" in side_str or "CALL" in side_str or "LONG" in side_str:
                item_side.setForeground(QColor("#00e676"))
            else:
                item_side.setForeground(QColor("#f44336"))
            self.table.setItem(r, 2, item_side)

            # Col 3, 4, 5: Gross P&L, Cost, Net P&L
            gross_pnl = float(t.get("pnl", 0.0))
            qty_val = float(t.get("qty", 1.0))
            cost = float(t.get("trade_cost", qty_val * 1.0))
            net_pnl = gross_pnl - cost

            # Gross ($)
            gross_str = f"+${gross_pnl:,.2f}" if gross_pnl >= 0 else f"-${abs(gross_pnl):,.2f}"
            item_gross = QTableWidgetItem(gross_str)
            item_gross.setFont(QFont("Courier New", 9))
            item_gross.setForeground(QColor("#8b949e"))
            self.table.setItem(r, 3, item_gross)

            # Cost ($)
            item_cost = QTableWidgetItem(f"${cost:,.2f}")
            item_cost.setFont(QFont("Courier New", 9))
            item_cost.setForeground(QColor("#ffb74d"))
            self.table.setItem(r, 4, item_cost)

            # Net P&L ($)
            net_str = f"+${net_pnl:,.2f}" if net_pnl >= 0 else f"-${abs(net_pnl):,.2f}"
            item_net = QTableWidgetItem(net_str)
            item_net.setFont(QFont("Courier New", 9, QFont.Bold))
            item_net.setForeground(QColor("#00e676" if net_pnl >= 0 else "#f44336"))
            self.table.setItem(r, 5, item_net)

            # Col 6: Core Setup
            setup_badges = []
            if t.get("is_jimmy_recommended"):
                setup_badges.append("🌟 Jimmy")
            if t.get("is_b_trade"):
                setup_badges.append("🏷️ B-Trade")
            if t.get("is_9_21_cross"):
                setup_badges.append("⚡ 9/21")
            if t.get("is_followed_9_up") or t.get("is_fullback_uptrend"):
                setup_badges.append("📈 9 EMA Up")
            if t.get("is_followed_9_down") or t.get("is_fullback_downtrend"):
                setup_badges.append("📉 9 EMA Down")
            if t.get("is_other"):
                o_txt = t.get("other_setup") or "Other"
                setup_badges.append(f"📦 {o_txt[:8]}")
            setup_str = " | ".join(setup_badges) if setup_badges else "—"
            item_setup = QTableWidgetItem(setup_str)
            if "Jimmy" in setup_str:
                item_setup.setForeground(QColor("#ffd700"))
            elif "B-Trade" in setup_str:
                item_setup.setForeground(QColor("#58a6ff"))
            elif "9/21" in setup_str:
                item_setup.setForeground(QColor("#ffeb3b"))
            elif "9 EMA Up" in setup_str:
                item_setup.setForeground(QColor("#00e676"))
            elif "9 EMA Down" in setup_str:
                item_setup.setForeground(QColor("#f44336"))
            elif "Other" in setup_str:
                item_setup.setForeground(QColor("#b388ff"))
            self.table.setItem(r, 6, item_setup)

            # Col 7: Confluences
            confl_badges = []
            if t.get("is_ak_macd_bb"):
                confl_badges.append("📊 MACD")
            if t.get("is_rsi_trendline"):
                confl_badges.append("📉 RSI")
            if t.get("is_hiranya_buy") or str(t.get("hiranya_signal_dir", "")).upper() == "BUY":
                confl_badges.append("🎯 HSM BUY")
            elif t.get("is_hiranya_sell") or str(t.get("hiranya_signal_dir", "")).upper() == "SELL":
                confl_badges.append("🎯 HSM SELL")
            elif t.get("is_hiranya_signal"):
                confl_badges.append("🎯 HSM")
            if t.get("is_vwap_aligned"):
                confl_badges.append("🌊 VWAP")
            if t.get("is_qqq_confluence"):
                confl_badges.append("🧭 QQQ")
            if t.get("is_add_confluence") or t.get("add_value") is not None:
                av = t.get("add_value")
                if av is not None:
                    try:
                        fav = float(av)
                        sign = "+" if fav > 0 else ""
                        confl_badges.append(f"📶 ADD {sign}{int(fav) if fav.is_integer() else fav}")
                    except (ValueError, TypeError):
                        confl_badges.append(f"📶 ADD {av}")
                else:
                    confl_badges.append("📶 ADD")

            confl_count = len(confl_badges)
            if confl_badges:
                confl_str = f"[{confl_count}/6] " + " ".join(confl_badges)
            else:
                confl_str = "—"
            item_confl = QTableWidgetItem(confl_str)
            if confl_count >= 4:
                item_confl.setForeground(QColor("#00e676"))
                item_confl.setFont(QFont("Segoe UI", 9, QFont.Bold))
            elif confl_count >= 2:
                item_confl.setForeground(QColor("#58a6ff"))
            else:
                item_confl.setForeground(QColor("#8b949e"))
            item_confl.setToolTip(f"{confl_count}/6 Checklist Confluences Confirmed:\n" + ("\n".join(confl_badges) if confl_badges else "None"))
            self.table.setItem(r, 7, item_confl)

            # Col 8: Early Exit
            is_early = t.get("early_exit", False)
            early_amt = t.get("early_exit_amount")
            early_str = f"⏱️ ${early_amt:,.0f}" if (is_early and early_amt) else ("⏱️ Early" if is_early else "—")
            item_early = QTableWidgetItem(early_str)
            if is_early:
                item_early.setForeground(QColor("#ff9800"))
            self.table.setItem(r, 8, item_early)

            # Col 9: Direction
            dir_right = t.get("direction_right", True)
            item_dir = QTableWidgetItem("✅ Right" if dir_right else "❌ Wrong")
            item_dir.setForeground(QColor("#00e676" if dir_right else "#f44336"))
            self.table.setItem(r, 9, item_dir)

            # Col 10: Outcome
            exit_r = str(t.get("exit_reason", "")).upper()
            if exit_r == "VWAP_TOUCH" or t.get("is_vwap_touch_exit", False):
                outcome_str = "🌊 VWAP Touch"
                out_color = "#00e5ff"
            elif exit_r == "STOP_LOSS":
                outcome_str = "🛑 Stop"
                out_color = "#f44336"
            elif exit_r == "EARLY_EXIT":
                outcome_str = "⏱️ Early"
                out_color = "#ff9800"
            elif exit_r == "BREAKEVEN":
                outcome_str = "⚡ BE"
                out_color = "#e6edf3"
            else:
                outcome_str = "🎯 Target"
                out_color = "#00e676"
            item_outcome = QTableWidgetItem(outcome_str)
            item_outcome.setForeground(QColor(out_color))
            self.table.setItem(r, 10, item_outcome)

        self.table.blockSignals(False)

        if selected_row_idx >= 0:
            self.table.selectRow(selected_row_idx)

    def _render_metric_cards(self, stats: dict[str, Any]):
        """Render top summary HTML cards."""
        def _card(title: str, winrate: float, net_pnl: float, gross_pnl: float, cost: float, wins: int, losses: int, count: int, color: str) -> str:
            pnl_sign = "+" if net_pnl >= 0 else ""
            pnl_col = "#00e676" if net_pnl >= 0 else "#f44336"
            return (
                f"<div style='flex:1;min-width:130px;background:#111d2e;border:1px solid #1e3a5f;"
                f"border-top:3px solid {color};border-radius:6px;padding:8px 10px;margin:2px;'>"
                f"<div style='font-size:11px;color:#78909c;font-weight:bold;text-transform:uppercase;'>{title}</div>"
                f"<div style='font-size:16px;font-weight:bold;color:{color};font-family:\"Segoe UI\",sans-serif;margin-top:2px;'>"
                f"{winrate:.1f}% WR <span style='font-size:11px;color:#8b949e;'>({count} trades)</span></div>"
                f"<div style='font-size:12px;color:{pnl_col};font-weight:bold;font-family:\"Courier New\",monospace;'>"
                f"{pnl_sign}${net_pnl:,.0f} Net &nbsp;<span style='color:#ffb74d;font-size:10px;'>(${cost:,.0f} cost)</span></div>"
                f"<div style='font-size:10px;color:#78909c;margin-top:2px;'>Gross: ${gross_pnl:,.0f} &nbsp;|&nbsp; {wins}W / {losses}L</div>"
                f"</div>"
            )

        zero_stat = {"win_rate": 0.0, "total_pnl": 0.0, "gross_pnl": 0.0, "total_cost": 0.0, "wins": 0, "losses": 0, "count": 0}
        all_s = stats.get("all", zero_stat)
        jimmy_s = stats.get("jimmy_recommended", zero_stat)
        b_s = stats.get("b_trade", zero_stat)
        cross_s = stats.get("cross_9_21", zero_stat)
        b_cross_s = stats.get("b_and_cross", zero_stat)
        fb_up_s = stats.get("followed_9_up", stats.get("fullback_uptrend", zero_stat))
        fb_down_s = stats.get("followed_9_down", stats.get("fullback_downtrend", zero_stat))
        other_s = stats.get("other", zero_stat)
        early_s = stats.get("early_exit", zero_stat)
        vwap_touch_s = stats.get("vwap_touch_exit", zero_stat)
        dir_s = stats.get("direction_right", zero_stat)

        ak_s = stats.get("ak_macd_bb", zero_stat)
        rsi_s = stats.get("rsi_trendline", zero_stat)
        hir_s = stats.get("hiranya_signal", zero_stat)
        hir_buy_s = stats.get("hiranya_buy", zero_stat)
        hir_sell_s = stats.get("hiranya_sell", zero_stat)
        vwap_s = stats.get("vwap_aligned", zero_stat)
        qqq_s = stats.get("qqq_confluence", zero_stat)
        add_s = stats.get("add_confluence", zero_stat)
        high_s = stats.get("high_confluence", zero_stat)

        cards_html = (
            f"<div style='display:flex;flex-wrap:wrap;gap:4px;'>"
            f"{_card('All Trades', all_s['win_rate'], all_s['total_pnl'], all_s.get('gross_pnl', 0.0), all_s.get('total_cost', 0.0), all_s['wins'], all_s['losses'], all_s['count'], '#58a6ff')}"
            f"{_card('Jimmy Rec', jimmy_s['win_rate'], jimmy_s['total_pnl'], jimmy_s.get('gross_pnl', 0.0), jimmy_s.get('total_cost', 0.0), jimmy_s['wins'], jimmy_s['losses'], jimmy_s['count'], '#ffd700')}"
            f"{_card('B-Trade Setup', b_s['win_rate'], b_s['total_pnl'], b_s.get('gross_pnl', 0.0), b_s.get('total_cost', 0.0), b_s['wins'], b_s['losses'], b_s['count'], '#00e676')}"
            f"{_card('9/21 Cross', cross_s['win_rate'], cross_s['total_pnl'], cross_s.get('gross_pnl', 0.0), cross_s.get('total_cost', 0.0), cross_s['wins'], cross_s['losses'], cross_s['count'], '#ffeb3b')}"
            f"{_card('B-Trade + 9/21', b_cross_s['win_rate'], b_cross_s['total_pnl'], b_cross_s.get('gross_pnl', 0.0), b_cross_s.get('total_cost', 0.0), b_cross_s['wins'], b_cross_s['losses'], b_cross_s['count'], '#00e5ff')}"
            f"{_card('Follow 9 Up', fb_up_s['win_rate'], fb_up_s['total_pnl'], fb_up_s.get('gross_pnl', 0.0), fb_up_s.get('total_cost', 0.0), fb_up_s['wins'], fb_up_s['losses'], fb_up_s['count'], '#00e676')}"
            f"{_card('Follow 9 Down', fb_down_s['win_rate'], fb_down_s['total_pnl'], fb_down_s.get('gross_pnl', 0.0), fb_down_s.get('total_cost', 0.0), fb_down_s['wins'], fb_down_s['losses'], fb_down_s['count'], '#f44336')}"
            f"{_card('HSM Buy', hir_buy_s['win_rate'], hir_buy_s['total_pnl'], hir_buy_s.get('gross_pnl', 0.0), hir_buy_s.get('total_cost', 0.0), hir_buy_s['wins'], hir_buy_s['losses'], hir_buy_s['count'], '#00e676')}"
            f"{_card('HSM Sell', hir_sell_s['win_rate'], hir_sell_s['total_pnl'], hir_sell_s.get('gross_pnl', 0.0), hir_sell_s.get('total_cost', 0.0), hir_sell_s['wins'], hir_sell_s['losses'], hir_sell_s['count'], '#f44336')}"
            f"{_card('AK MACD BB', ak_s['win_rate'], ak_s['total_pnl'], ak_s.get('gross_pnl', 0.0), ak_s.get('total_cost', 0.0), ak_s['wins'], ak_s['losses'], ak_s['count'], '#00e5ff')}"
            f"{_card('RSI Trendline', rsi_s['win_rate'], rsi_s['total_pnl'], rsi_s.get('gross_pnl', 0.0), rsi_s.get('total_cost', 0.0), rsi_s['wins'], rsi_s['losses'], rsi_s['count'], '#00e5ff')}"
            f"{_card('VWAP Aligned', vwap_s['win_rate'], vwap_s['total_pnl'], vwap_s.get('gross_pnl', 0.0), vwap_s.get('total_cost', 0.0), vwap_s['wins'], vwap_s['losses'], vwap_s['count'], '#00e5ff')}"
            f"{_card('QQQ Confluence', qqq_s['win_rate'], qqq_s['total_pnl'], qqq_s.get('gross_pnl', 0.0), qqq_s.get('total_cost', 0.0), qqq_s['wins'], qqq_s['losses'], qqq_s['count'], '#00e5ff')}"
            f"{_card('ADD Breadth', add_s['win_rate'], add_s['total_pnl'], add_s.get('gross_pnl', 0.0), add_s.get('total_cost', 0.0), add_s['wins'], add_s['losses'], add_s['count'], '#00e5ff')}"
            f"{_card('High Confl (4+)', high_s['win_rate'], high_s['total_pnl'], high_s.get('gross_pnl', 0.0), high_s.get('total_cost', 0.0), high_s['wins'], high_s['losses'], high_s['count'], '#00e676')}"
            f"{_card('VWAP Exit', vwap_touch_s['win_rate'], vwap_touch_s['total_pnl'], vwap_touch_s.get('gross_pnl', 0.0), vwap_touch_s.get('total_cost', 0.0), vwap_touch_s['wins'], vwap_touch_s['losses'], vwap_touch_s['count'], '#00e5ff')}"
            f"{_card('Early Exit', early_s['win_rate'], early_s['total_pnl'], early_s.get('gross_pnl', 0.0), early_s.get('total_cost', 0.0), early_s['wins'], early_s['losses'], early_s['count'], '#ff9800')}"
            f"{_card('Direction Right', dir_s['win_rate'], dir_s['total_pnl'], dir_s.get('gross_pnl', 0.0), dir_s.get('total_cost', 0.0), dir_s['wins'], dir_s['losses'], dir_s['count'], '#00e676')}"
            f"{_card('Other Setup', other_s['win_rate'], other_s['total_pnl'], other_s.get('gross_pnl', 0.0), other_s.get('total_cost', 0.0), other_s['wins'], other_s['losses'], other_s['count'], '#b388ff')}"
            f"</div>"
        )
        self.cards_label.setText(cards_html)

    # ── Table Selection & Editor Interaction ──────────────────────────────────

    def _on_table_selection_changed(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            return

        row = selected_items[0].row()
        item_dt = self.table.item(row, 0)
        if not item_dt:
            return

        trade_id = item_dt.data(Qt.UserRole)
        self._load_trade_to_editor(trade_id)

    def _load_trade_to_editor(self, trade_id: str):
        trades = trade_store.load_all_trades()
        target = next((t for t in trades if t.get("id") == trade_id), None)
        if not target:
            return

        self._current_trade_id = trade_id

        # Date & Time
        d_str = target.get("date", "")
        if d_str:
            qd = QDate.fromString(d_str, "yyyy-MM-dd")
            if qd.isValid():
                self.edit_date.setDate(qd)

        t_str = target.get("time", "09:30:00")
        if t_str:
            qt = QTime.fromString(t_str, "HH:mm:ss")
            if not qt.isValid():
                qt = QTime.fromString(t_str, "HH:mm")
            if qt.isValid():
                self.edit_time.setTime(qt)

        # Symbol, Side, Qty
        self.edit_symbol.setText(target.get("symbol", "SPY"))
        side_idx = self.edit_side.findText(target.get("side", "BUY"), Qt.MatchContains)
        self.edit_side.setCurrentIndex(max(0, side_idx))
        self.edit_qty.setValue(float(target.get("qty", 1.0)))

        # Prices, Cost & PnL
        self.edit_entry.setValue(float(target.get("entry_price", 0.0)))
        self.edit_exit.setValue(float(target.get("exit_price", 0.0)))
        self.edit_pnl.setValue(float(target.get("pnl", 0.0)))
        qty_val = float(target.get("qty", 1.0))
        self.edit_cost.setValue(float(target.get("trade_cost", qty_val * 1.0)))
        self._update_net_pnl_preview()

        # Conditions
        # Conditions
        self.cb_jimmy_rec.setChecked(bool(target.get("is_jimmy_recommended", False)))
        self.cb_b_trade.setChecked(bool(target.get("is_b_trade", False)))
        self.cb_9_21.setChecked(bool(target.get("is_9_21_cross", False)))
        self.cb_followed_9_up.setChecked(bool(target.get("is_followed_9_up", False) or target.get("is_fullback_uptrend", False)))
        self.cb_followed_9_down.setChecked(bool(target.get("is_followed_9_down", False) or target.get("is_fullback_downtrend", False)))
        self.cb_ak_macd.setChecked(bool(target.get("is_ak_macd_bb", False)))
        self.cb_rsi_trendline.setChecked(bool(target.get("is_rsi_trendline", False)))

        # Hiranya Buy / Sell
        h_dir = str(target.get("hiranya_signal_dir", "")).upper()
        if target.get("is_hiranya_buy") or h_dir == "BUY":
            self.combo_hiranya.setCurrentIndex(1)
        elif target.get("is_hiranya_sell") or h_dir == "SELL":
            self.combo_hiranya.setCurrentIndex(2)
        else:
            self.combo_hiranya.setCurrentIndex(0)

        self.cb_vwap.setChecked(bool(target.get("is_vwap_aligned", False)))
        self.cb_qqq.setChecked(bool(target.get("is_qqq_confluence", False)))

        # Load ADD Value
        add_v = target.get("add_value")
        if add_v is not None:
            sign = "+" if add_v > 0 else ""
            self.edit_add_val.setText(f"{sign}{int(add_v) if isinstance(add_v, (int, float)) and float(add_v).is_integer() else add_v}")
        else:
            self.edit_add_val.clear()
        self.cb_add.setChecked(bool(target.get("is_add_confluence", False) or add_v is not None))

        self.cb_other.setChecked(bool(target.get("is_other", False)))
        self.edit_other.setText(str(target.get("other_setup", "")))
        self.cb_early_exit.setChecked(bool(target.get("early_exit", False)))
        self.edit_early_amt.setValue(float(target.get("early_exit_amount", 0.0) or 0.0))
        self._update_confluence_score_display()

        if target.get("direction_right", True):
            self.radio_dir_right.setChecked(True)
        else:
            self.radio_dir_wrong.setChecked(True)

        exit_reason = target.get("exit_reason")
        if not exit_reason:
            pnl_val = float(target.get("pnl", 0.0) or 0.0)
            exit_reason = "TARGET" if pnl_val > 0 else ("STOP_LOSS" if pnl_val < 0 else "BREAKEVEN")
        
        exit_reason = str(exit_reason).upper()
        if exit_reason == "VWAP_TOUCH":
            self.radio_exit_vwap.setChecked(True)
        elif exit_reason == "STOP_LOSS":
            self.radio_exit_stop.setChecked(True)
        elif exit_reason == "EARLY_EXIT":
            self.radio_exit_early.setChecked(True)
        elif exit_reason == "BREAKEVEN":
            self.radio_exit_be.setChecked(True)
        else:
            self.radio_exit_target.setChecked(True)

        self.edit_notes.setPlainText(target.get("notes", ""))
        self.save_trade_btn.setText("💾  Update Trade Classification")

        if self._status_cb:
            self._status_cb(f"Selected trade {trade_id} ({target.get('symbol')} {target.get('date')})")

    def _on_chart_filter_changed(self):
        self._load_and_refresh()

    def _update_confluence_score_display(self):
        if not hasattr(self, "cb_ak_macd") or not hasattr(self, "confluence_badge"):
            return
        cbs = [
            self.cb_ak_macd,
            self.cb_rsi_trendline,
            self.cb_vwap,
            self.cb_qqq,
            self.cb_add,
        ]
        score = sum(1 for cb in cbs if cb.isChecked())
        if hasattr(self, "combo_hiranya") and self.combo_hiranya.currentIndex() > 0:
            score += 1

        if score >= 5:
            quality = "<span style='color:#00e676;font-weight:bold;'>A+ Highest Probability Setup</span>"
        elif score >= 3:
            quality = "<span style='color:#58a6ff;font-weight:bold;'>Solid Quality Setup</span>"
        elif score >= 1:
            quality = "<span style='color:#ff9800;font-weight:bold;'>Moderate Confluence</span>"
        else:
            quality = "<span style='color:#8b949e;'>No Confluence Checked</span>"

        self.confluence_badge.setText(f"✨ <b>Confluence Score:</b> {score} / 6 Rules Aligned — {quality}")

    def _set_early_amount(self, amt: float):
        self.cb_early_exit.setChecked(True)
        self.edit_early_amt.setValue(amt)

    def _on_other_text_changed(self, text: str):
        if text.strip() and not self.cb_other.isChecked():
            self.cb_other.setChecked(True)

    def _on_other_cb_toggled(self, checked: bool):
        if checked and not self.edit_other.text().strip():
            self.edit_other.setFocus()

    def _on_add_text_changed(self, text: str):
        if text.strip() and not self.cb_add.isChecked():
            self.cb_add.setChecked(True)
        self._update_confluence_score_display()

    def _on_add_cb_toggled(self, checked: bool):
        if checked and not self.edit_add_val.text().strip():
            self.edit_add_val.setFocus()
        self._update_confluence_score_display()

    def _clear_editor(self):
        self._current_trade_id = None
        self.edit_date.setDate(QDate.currentDate())
        self.edit_time.setTime(QTime(9, 30, 0))
        self.edit_symbol.setText("SPY")
        self.edit_side.setCurrentIndex(0)
        self.edit_qty.setValue(1.0)
        self.edit_entry.setValue(0.0)
        self.edit_exit.setValue(0.0)
        self.edit_pnl.setValue(0.0)
        self.edit_cost.setValue(1.0)
        self._update_net_pnl_preview()
        self.cb_jimmy_rec.setChecked(False)
        self.cb_b_trade.setChecked(False)
        self.cb_9_21.setChecked(False)
        self.cb_followed_9_up.setChecked(False)
        self.cb_followed_9_down.setChecked(False)
        self.cb_ak_macd.setChecked(False)
        self.cb_rsi_trendline.setChecked(False)
        self.combo_hiranya.setCurrentIndex(0)
        self.cb_vwap.setChecked(False)
        self.cb_qqq.setChecked(False)
        self.cb_add.setChecked(False)
        self.edit_add_val.clear()
        self._update_confluence_score_display()
        self.cb_other.setChecked(False)
        self.edit_other.clear()
        self.cb_early_exit.setChecked(False)
        self.edit_early_amt.setValue(0.0)
        self.radio_dir_right.setChecked(True)
        self.radio_exit_target.setChecked(True)
        self.edit_notes.clear()
        self.save_trade_btn.setText("💾  Save Trade Classification")
        self.table.clearSelection()

    def _on_add_new_clicked(self):
        self._clear_editor()
        self.edit_symbol.setFocus()
        if self._status_cb:
            self._status_cb("Ready to create a new trade entry.")

    def _on_save_trade(self):
        date_str = self.edit_date.date().toString("yyyy-MM-dd")
        time_str = self.edit_time.time().toString("HH:mm:ss")
        symbol = self.edit_symbol.text().strip().upper() or "SPY"
        side = self.edit_side.currentText()
        qty = self.edit_qty.value()
        entry_price = self.edit_entry.value()
        exit_price = self.edit_exit.value()
        pnl = self.edit_pnl.value()
        cost = self.edit_cost.value()
        is_jimmy = self.cb_jimmy_rec.isChecked()
        is_b = self.cb_b_trade.isChecked()
        is_cross = self.cb_9_21.isChecked()
        is_f9_up = self.cb_followed_9_up.isChecked()
        is_f9_down = self.cb_followed_9_down.isChecked()
        is_ak_macd = self.cb_ak_macd.isChecked()
        is_rsi = self.cb_rsi_trendline.isChecked()
        
        h_idx = self.combo_hiranya.currentIndex()
        is_h_buy = (h_idx == 1)
        is_h_sell = (h_idx == 2)
        h_dir = "BUY" if is_h_buy else ("SELL" if is_h_sell else "")
        is_hiranya = (h_idx > 0)

        is_vwap = self.cb_vwap.isChecked()
        is_qqq = self.cb_qqq.isChecked()
        is_add = self.cb_add.isChecked()
        raw_add_str = self.edit_add_val.text().strip()
        add_val_num = None
        if raw_add_str:
            try:
                add_val_num = float(raw_add_str.replace("+", "").replace(",", ""))
                is_add = True
            except ValueError:
                add_val_num = None

        is_other = self.cb_other.isChecked()
        other_setup = self.edit_other.text().strip()
        early = self.cb_early_exit.isChecked()
        early_amt = self.edit_early_amt.value() if early else None
        dir_right = self.radio_dir_right.isChecked()
        
        if self.radio_exit_vwap.isChecked():
            exit_reason = "VWAP_TOUCH"
        elif self.radio_exit_stop.isChecked():
            exit_reason = "STOP_LOSS"
        elif self.radio_exit_early.isChecked():
            exit_reason = "EARLY_EXIT"
        elif self.radio_exit_be.isChecked():
            exit_reason = "BREAKEVEN"
        else:
            exit_reason = "TARGET"

        notes = self.edit_notes.toPlainText().strip()

        trade_dict = {
            "id": self._current_trade_id,
            "date": date_str,
            "time": time_str,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "trade_cost": cost,
            "is_jimmy_recommended": is_jimmy,
            "is_b_trade": is_b,
            "is_9_21_cross": is_cross,
            "is_followed_9_up": is_f9_up,
            "is_followed_9_down": is_f9_down,
            "is_fullback_uptrend": is_f9_up,
            "is_fullback_downtrend": is_f9_down,
            "is_ak_macd_bb": is_ak_macd,
            "is_rsi_trendline": is_rsi,
            "is_hiranya_signal": is_hiranya,
            "is_hiranya_buy": is_h_buy,
            "is_hiranya_sell": is_h_sell,
            "hiranya_signal_dir": h_dir,
            "is_vwap_aligned": is_vwap,
            "is_qqq_confluence": is_qqq,
            "is_add_confluence": is_add,
            "add_value": add_val_num,
            "is_other": is_other,
            "other_setup": other_setup,
            "early_exit": early or (exit_reason == "EARLY_EXIT"),
            "early_exit_amount": early_amt,
            "exit_reason": exit_reason,
            "is_vwap_touch_exit": (exit_reason == "VWAP_TOUCH"),
            "direction_right": dir_right,
            "notes": notes,
        }

        saved = trade_store.save_or_update_trade(trade_dict)
        self._current_trade_id = saved["id"]

        net_val = pnl - cost
        if self._status_cb:
            self._status_cb(f"✅ Saved trade {symbol} on {date_str} (Gross: ${pnl:.2f}, Cost: ${cost:.2f}, Net: ${net_val:.2f})")

        self._load_and_refresh()
        self.trade_updated.emit()

    def _on_delete_trade(self):
        if not self._current_trade_id:
            QMessageBox.information(self, "Delete", "No trade selected to delete.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this trade record?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            trade_store.delete_trade(self._current_trade_id)
            if self._status_cb:
                self._status_cb(f"Deleted trade {self._current_trade_id}")
            self._clear_editor()
            self._load_and_refresh()
            self.trade_updated.emit()

    # ── CSV Import & Export ───────────────────────────────────────────────────

    def _on_upload_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Trade CSV",
            "",
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if not file_path:
            return

        imported, skipped, errors = trade_store.import_trades_from_csv(file_path)

        if errors:
            QMessageBox.warning(self, "CSV Import Notice", "\n".join(errors))
        else:
            QMessageBox.information(
                self,
                "CSV Import Success",
                f"Successfully imported {imported} trades from CSV!\n\n"
                f"You can now select any trade from the left list to tag conditions "
                f"(B-Trade, 9/21 Cross, Early Exit, Direction).",
            )

        if self._status_cb:
            self._status_cb(f"Imported {imported} trades from {file_path}")

        self._load_and_refresh()
        self.trade_updated.emit()

    def _on_export_csv(self):
        trades = trade_store.load_all_trades()
        if not trades:
            QMessageBox.information(self, "Export", "No trades available to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Trades to CSV",
            f"SPYTrade_Export_{datetime.date.today().isoformat()}.csv",
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Date", "Time", "Symbol", "Side", "Qty", "Entry Price", "Exit Price",
                    "Gross P&L", "Trade Cost", "Net P&L",
                    "Is Jimmy Recommended", "Is B-Trade", "Is 9/21 Cross",
                    "Followed 9 EMA Up", "Followed 9 EMA Down",
                    "Is AK MACD BB", "Is RSI Trendline",
                    "Hiranya Signal Dir", "Is Hiranya Signal",
                    "Is VWAP Aligned", "Is QQQ Confluence", "Is ADD Confluence", "ADD Value",
                    "Is Other", "Other Setup",
                    "Exit Reason", "Early Exit", "Direction Right", "Notes"
                ])
                for t in trades:
                    pnl_val = float(t.get("pnl", 0))
                    qty_val = float(t.get("qty", 1.0))
                    cost_val = float(t.get("trade_cost", qty_val * 1.0))
                    net_val = pnl_val - cost_val
                    writer.writerow([
                        t.get("date", ""),
                        t.get("time", ""),
                        t.get("symbol", ""),
                        t.get("side", ""),
                        t.get("qty", 1),
                        t.get("entry_price", 0),
                        t.get("exit_price", 0),
                        pnl_val,
                        cost_val,
                        net_val,
                        1 if t.get("is_jimmy_recommended") else 0,
                        1 if t.get("is_b_trade") else 0,
                        1 if t.get("is_9_21_cross") else 0,
                        1 if (t.get("is_followed_9_up") or t.get("is_fullback_uptrend")) else 0,
                        1 if (t.get("is_followed_9_down") or t.get("is_fullback_downtrend")) else 0,
                        1 if t.get("is_ak_macd_bb") else 0,
                        1 if t.get("is_rsi_trendline") else 0,
                        t.get("hiranya_signal_dir") or ("BUY" if t.get("is_hiranya_buy") else ("SELL" if t.get("is_hiranya_sell") else "")),
                        1 if (t.get("is_hiranya_signal") or t.get("is_hiranya_buy") or t.get("is_hiranya_sell")) else 0,
                        1 if t.get("is_vwap_aligned") else 0,
                        1 if t.get("is_qqq_confluence") else 0,
                        1 if t.get("is_add_confluence") else 0,
                        t.get("add_value", "") if t.get("add_value") is not None else "",
                        1 if t.get("is_other") else 0,
                        t.get("other_setup", ""),
                        t.get("exit_reason", "TARGET"),
                        1 if t.get("early_exit") else 0,
                        1 if t.get("direction_right", True) else 0,
                        t.get("notes", ""),
                    ])

            QMessageBox.information(self, "Export Success", f"Successfully exported {len(trades)} trades to:\n{file_path}")
            if self._status_cb:
                self._status_cb(f"Exported {len(trades)} trades to CSV")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export CSV: {e}")
