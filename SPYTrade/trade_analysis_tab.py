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

    def render_stats(self, stats: dict[str, Any], title_suffix: str = ""):
        self.ax.clear()
        self.ax.set_facecolor("#0d1117")

        categories = [
            ("All Trades", stats["all"]),
            ("B-Trade", stats["b_trade"]),
            ("Non B-Trade", stats["non_b_trade"]),
            ("9/21 Cross", stats["cross_9_21"]),
            ("Non 9/21 Cross", stats["non_cross_9_21"]),
            ("Early Exit", stats["early_exit"]),
            ("Normal Exit", stats["normal_exit"]),
            ("Dir Right", stats["direction_right"]),
            ("Dir Wrong", stats["direction_wrong"]),
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
            elif "Right" in label or "B-Trade" in label or "9/21 Cross" in label:
                bar_colors.append("#00e676" if wr >= 50 else "#ff9800")
            elif "Wrong" in label or "Early Exit" in label:
                bar_colors.append("#f44336" if wr < 50 else "#ff9800")
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
            "All Setups",
            "B-Trades Only",
            "9/21 Cross Only",
            "Early Exits Only",
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
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Date / Time", "Symbol", "Side", "Gross ($)", "Cost ($)", "Net P&L ($)", "B-Trade", "9/21", "Early", "Direction"
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

        # Gross P&L, Trade Cost ($1.00 per trade), and Net P&L
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
        self.edit_cost.setToolTip("Trade commission / exchange cost (defaults to $1.00 per trade)")
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

        # Condition Checkboxes
        self.cb_b_trade = QCheckBox("🏷️  Is B-Trade Setup")
        self.cb_9_21 = QCheckBox("⚡  9 / 21 EMA Cross")
        self.cb_early_exit = QCheckBox("⏱️  Early Exit (Cut before Target / Stop)")

        cond_layout.addWidget(self.cb_b_trade)
        cond_layout.addWidget(self.cb_9_21)
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
        self.chart_canvas.render_stats(stats, title_suffix=stats_title)

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
        if filter_mode == "B-Trades Only":
            trades = [t for t in trades if t.get("is_b_trade", False)]
        elif filter_mode == "9/21 Cross Only":
            trades = [t for t in trades if t.get("is_9_21_cross", False)]
        elif filter_mode == "Early Exits Only":
            trades = [t for t in trades if t.get("early_exit", False)]
        elif filter_mode == "Direction Right Only":
            trades = [t for t in trades if t.get("direction_right", True)]
        elif filter_mode == "Direction Wrong Only":
            trades = [t for t in trades if not t.get("direction_right", True)]
        elif filter_mode == "Wins Only (+$)":
            trades = [t for t in trades if (float(t.get("pnl", 0.0)) - float(t.get("trade_cost", 1.0))) > 0]
        elif filter_mode == "Losses Only (-$)":
            trades = [t for t in trades if (float(t.get("pnl", 0.0)) - float(t.get("trade_cost", 1.0))) < 0]

        self.table.blockSignals(True)
        self.table.setRowCount(len(trades))

        selected_row_idx = -1

        for r, t in enumerate(trades):
            t_id = t.get("id", "")
            if t_id == self._current_trade_id:
                selected_row_idx = r

            # Date / Time
            dt_str = f"{t.get('date', '')} {t.get('time', '')[:5]}"
            item_dt = QTableWidgetItem(dt_str)
            item_dt.setData(Qt.UserRole, t_id)
            self.table.setItem(r, 0, item_dt)

            # Symbol
            item_sym = QTableWidgetItem(t.get("symbol", "SPY"))
            item_sym.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.table.setItem(r, 1, item_sym)

            # Side
            side_str = t.get("side", "BUY")
            item_side = QTableWidgetItem(side_str)
            if "BUY" in side_str or "CALL" in side_str or "LONG" in side_str:
                item_side.setForeground(QColor("#00e676"))
            else:
                item_side.setForeground(QColor("#f44336"))
            self.table.setItem(r, 2, item_side)

            # Gross P&L, Cost, Net P&L
            gross_pnl = float(t.get("pnl", 0.0))
            cost = float(t.get("trade_cost", 1.0))
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

            # B-Trade badge
            is_b = t.get("is_b_trade", False)
            item_b = QTableWidgetItem("🏷️ Yes" if is_b else "—")
            if is_b:
                item_b.setForeground(QColor("#58a6ff"))
            self.table.setItem(r, 6, item_b)

            # 9/21 Cross badge
            is_cross = t.get("is_9_21_cross", False)
            item_cross = QTableWidgetItem("⚡ Yes" if is_cross else "—")
            if is_cross:
                item_cross.setForeground(QColor("#ffeb3b"))
            self.table.setItem(r, 7, item_cross)

            # Early Exit badge
            is_early = t.get("early_exit", False)
            item_early = QTableWidgetItem("⏱️ Early" if is_early else "—")
            if is_early:
                item_early.setForeground(QColor("#ff9800"))
            self.table.setItem(r, 8, item_early)

            # Direction badge
            dir_right = t.get("direction_right", True)
            item_dir = QTableWidgetItem("✅ Right" if dir_right else "❌ Wrong")
            item_dir.setForeground(QColor("#00e676" if dir_right else "#f44336"))
            self.table.setItem(r, 9, item_dir)

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

        all_s = stats["all"]
        b_s = stats["b_trade"]
        cross_s = stats["cross_9_21"]
        early_s = stats["early_exit"]
        dir_s = stats["direction_right"]

        cards_html = (
            f"<div style='display:flex;flex-wrap:wrap;gap:4px;'>"
            f"{_card('All Trades', all_s['win_rate'], all_s['total_pnl'], all_s.get('gross_pnl', 0.0), all_s.get('total_cost', 0.0), all_s['wins'], all_s['losses'], all_s['count'], '#58a6ff')}"
            f"{_card('B-Trade Setup', b_s['win_rate'], b_s['total_pnl'], b_s.get('gross_pnl', 0.0), b_s.get('total_cost', 0.0), b_s['wins'], b_s['losses'], b_s['count'], '#00e676')}"
            f"{_card('9/21 Cross', cross_s['win_rate'], cross_s['total_pnl'], cross_s.get('gross_pnl', 0.0), cross_s.get('total_cost', 0.0), cross_s['wins'], cross_s['losses'], cross_s['count'], '#ffeb3b')}"
            f"{_card('Early Exit', early_s['win_rate'], early_s['total_pnl'], early_s.get('gross_pnl', 0.0), early_s.get('total_cost', 0.0), early_s['wins'], early_s['losses'], early_s['count'], '#ff9800')}"
            f"{_card('Direction Right', dir_s['win_rate'], dir_s['total_pnl'], dir_s.get('gross_pnl', 0.0), dir_s.get('total_cost', 0.0), dir_s['wins'], dir_s['losses'], dir_s['count'], '#00e676')}"
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
        self.edit_cost.setValue(float(target.get("trade_cost", 1.0)))
        self._update_net_pnl_preview()

        # Conditions
        self.cb_b_trade.setChecked(bool(target.get("is_b_trade", False)))
        self.cb_9_21.setChecked(bool(target.get("is_9_21_cross", False)))
        self.cb_early_exit.setChecked(bool(target.get("early_exit", False)))
        self.edit_early_amt.setValue(float(target.get("early_exit_amount", 0.0) or 0.0))

        if target.get("direction_right", True):
            self.radio_dir_right.setChecked(True)
        else:
            self.radio_dir_wrong.setChecked(True)

        self.edit_notes.setPlainText(target.get("notes", ""))
        self.save_trade_btn.setText("💾  Update Trade Classification")

        if self._status_cb:
            self._status_cb(f"Selected trade {trade_id} ({target.get('symbol')} {target.get('date')})")

    def _set_early_amount(self, amt: float):
        self.cb_early_exit.setChecked(True)
        self.edit_early_amt.setValue(amt)

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
        self.cb_b_trade.setChecked(False)
        self.cb_9_21.setChecked(False)
        self.cb_early_exit.setChecked(False)
        self.edit_early_amt.setValue(0.0)
        self.radio_dir_right.setChecked(True)
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
        is_b = self.cb_b_trade.isChecked()
        is_cross = self.cb_9_21.isChecked()
        early = self.cb_early_exit.isChecked()
        early_amt = self.edit_early_amt.value() if early else None
        dir_right = self.radio_dir_right.isChecked()
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
            "is_b_trade": is_b,
            "is_9_21_cross": is_cross,
            "early_exit": early,
            "early_exit_amount": early_amt,
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
                    "Gross P&L", "Trade Cost", "Net P&L", "Is B-Trade", "Is 9/21 Cross", "Early Exit", "Direction Right", "Notes"
                ])
                for t in trades:
                    pnl_val = float(t.get("pnl", 0))
                    cost_val = float(t.get("trade_cost", 1.0))
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
                        1 if t.get("is_b_trade") else 0,
                        1 if t.get("is_9_21_cross") else 0,
                        1 if t.get("early_exit") else 0,
                        1 if t.get("direction_right") else 0,
                        t.get("notes", ""),
                    ])

            QMessageBox.information(self, "Export Success", f"Successfully exported {len(trades)} trades to:\n{file_path}")
            if self._status_cb:
                self._status_cb(f"Exported {len(trades)} trades to CSV")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export CSV: {e}")
