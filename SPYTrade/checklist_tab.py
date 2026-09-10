"""checklist_tab.py — Trade Checklist Tab widget for SPYTrade desktop app.

Provides:
  • Interactive 7-rule checklist with point weighting (100 pts total)
  • PUTS / CALLS mode toggle with state badges ([RED] / [GREEN], etc.)
  • Quick Check All / Clear All controls
  • Real-time score meter and threshold status feedback
  • Trade note entry and persistence to trade_checklist.json
  • Saved checklist history table
"""

from __future__ import annotations

import datetime
import json
import logging
import pathlib
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QScrollArea, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QProgressBar,
    QSizePolicy, QMessageBox,
)

log = logging.getLogger(__name__)

_DATA_DIR = pathlib.Path(__file__).parent.parent
_CHECKLIST_FILE = _DATA_DIR / "trade_checklist.json"

CL_CONDITIONS = {
    "PUTS": [
        {"key": "ak_macd_bb",             "label": "1. AK MACD BB",             "state": "RED",            "sub": "AK MACD BB is RED (Bearish momentum / sell zone)",             "pts": 15},
        {"key": "rsi_cross_trendline",    "label": "2. RSI Cross Trend Line",   "state": "CROSS DOWN",     "sub": "RSI crosses / breaks down below the trendline",                 "pts": 15},
        {"key": "hiranya_signal_monitor", "label": "3. Hiranya Signal Monitor", "state": "RED",            "sub": "Hiranya Signal Monitor is RED (Bearish confirmation)",          "pts": 15},
        {"key": "cross_9_21_vwap",        "label": "4. 9 21 Cross & VWAP",      "state": "9<21 & <VWAP",   "sub": "9 EMA crossed below 21 EMA & price is below VWAP",              "pts": 15},
        {"key": "b_trade",                "label": "5. B-Trade Setup",          "state": "CONFIRMED",      "sub": "Valid B-Trade setup / pullback continuation confirmed",         "pts": 15},
        {"key": "qqq_direction",          "label": "6. QQQ Direction",          "state": "DOWN / BEARISH", "sub": "QQQ moving downward in confluence with SPY",                    "pts": 15},
        {"key": "add_direction",          "label": "7. ADD Direction",          "state": "DECLINING",      "sub": "NYSE $ADD breadth declining / in negative territory",           "pts": 10},
    ],
    "CALLS": [
        {"key": "ak_macd_bb",             "label": "1. AK MACD BB",             "state": "GREEN",          "sub": "AK MACD BB is GREEN (Bullish momentum / buy zone)",            "pts": 15},
        {"key": "rsi_cross_trendline",    "label": "2. RSI Cross Trend Line",   "state": "CROSS UP",       "sub": "RSI crosses / breaks up above the trendline",                  "pts": 15},
        {"key": "hiranya_signal_monitor", "label": "3. Hiranya Signal Monitor", "state": "GREEN",          "sub": "Hiranya Signal Monitor is GREEN (Bullish confirmation)",        "pts": 15},
        {"key": "cross_9_21_vwap",        "label": "4. 9 21 Cross & VWAP",      "state": "9>21 & >VWAP",   "sub": "9 EMA crossed above 21 EMA & price is above VWAP",              "pts": 15},
        {"key": "b_trade",                "label": "5. B-Trade Setup",          "state": "CONFIRMED",      "sub": "Valid B-Trade setup / pullback continuation confirmed",         "pts": 15},
        {"key": "qqq_direction",          "label": "6. QQQ Direction",          "state": "UP / BULLISH",   "sub": "QQQ moving upward in confluence with SPY",                      "pts": 15},
        {"key": "add_direction",          "label": "7. ADD Direction",          "state": "ADVANCING",      "sub": "NYSE $ADD breadth advancing / in positive territory",           "pts": 10},
    ]
}

CL_EMOJIS = {
    "ak_macd_bb": "📊",
    "rsi_cross_trendline": "📉",
    "hiranya_signal_monitor": "🎯",
    "cross_9_21_vwap": "⚡",
    "b_trade": "🏷️",
    "qqq_direction": "🧭",
    "add_direction": "📶",
}


def load_checklist_records() -> list[dict[str, Any]]:
    if not _CHECKLIST_FILE.exists():
        return []
    try:
        with open(_CHECKLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        log.error("Failed to read %s: %s", _CHECKLIST_FILE, e)
        return []


def save_checklist_records(records: list[dict[str, Any]]) -> None:
    try:
        with open(_CHECKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.error("Failed to write %s: %s", _CHECKLIST_FILE, e)


class ChecklistTab(QWidget):
    """Trade Conditions Checklist tab with live scoring and record history."""

    def __init__(self, status_callback=None, parent=None):
        super().__init__(parent)
        self._status_cb = status_callback
        self._trade_type = "PUTS"
        self._checks: dict[str, bool] = {}
        self._checkbox_widgets: dict[str, QCheckBox] = {}
        self._build_ui()
        self._load_records_table()

    def _status_msg(self, msg: str):
        if self._status_cb:
            self._status_cb(msg)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ── Header bar: Title + Trade Type buttons ──
        hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("✅ <b>Trade Conditions Checklist (7 Rules)</b>")
        title.setStyleSheet("font-size: 17px; color: #58a6ff;")
        sub = QLabel("Verify ALL 7 conditions before entering a trade — 100 points total")
        sub.setStyleSheet("font-size: 11px; color: #8b949e;")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        hdr.addLayout(title_box)

        hdr.addStretch()

        type_lbl = QLabel("<b>Trade Type:</b>")
        type_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        hdr.addWidget(type_lbl)

        self.btn_puts = QPushButton("📉 PUTS")
        self.btn_puts.setFixedWidth(90)
        self.btn_puts.setStyleSheet("padding: 6px 14px; font-weight: bold; border-radius: 6px; background: #2d0e0e; border: 2px solid #f85149; color: #f85149;")
        self.btn_puts.clicked.connect(lambda: self._set_type("PUTS"))
        hdr.addWidget(self.btn_puts)

        self.btn_calls = QPushButton("📈 CALLS")
        self.btn_calls.setFixedWidth(90)
        self.btn_calls.setStyleSheet("padding: 6px 14px; font-weight: bold; border-radius: 6px; background: #161b22; border: 1.5px solid #30363d; color: #8b949e;")
        self.btn_calls.clicked.connect(lambda: self._set_type("CALLS"))
        hdr.addWidget(self.btn_calls)

        layout.addLayout(hdr)

        # ── Score Banner ──
        score_card = QFrame()
        score_card.setStyleSheet("background: #161b22; border: 1.5px solid #30363d; border-radius: 10px; padding: 10px 14px;")
        score_layout = QHBoxLayout(score_card)
        score_layout.setSpacing(16)

        ring_box = QVBoxLayout()
        ring_box.setSpacing(0)
        self.lbl_score_num = QLabel("0")
        self.lbl_score_num.setStyleSheet("font-size: 32px; font-weight: 900; color: #8b949e;")
        self.lbl_score_num.setAlignment(Qt.AlignCenter)
        self.lbl_score_denom = QLabel("/ 100 pts")
        self.lbl_score_denom.setStyleSheet("font-size: 11px; color: #8b949e;")
        self.lbl_score_denom.setAlignment(Qt.AlignCenter)
        self.lbl_score_count = QLabel("0 / 7 met")
        self.lbl_score_count.setStyleSheet("font-size: 10px; color: #8b949e; font-weight: bold;")
        self.lbl_score_count.setAlignment(Qt.AlignCenter)
        ring_box.addWidget(self.lbl_score_num)
        ring_box.addWidget(self.lbl_score_denom)
        ring_box.addWidget(self.lbl_score_count)
        score_layout.addLayout(ring_box)

        bar_box = QVBoxLayout()
        bar_box.setSpacing(6)
        self.lbl_score_status = QLabel("Waiting for your checklist...")
        self.lbl_score_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #e6edf3;")
        self.score_bar = QProgressBar()
        self.score_bar.setRange(0, 100)
        self.score_bar.setValue(0)
        self.score_bar.setFixedHeight(12)
        self.score_bar.setTextVisible(False)
        self.score_bar.setStyleSheet("""
            QProgressBar {
                background: #21262d;
                border-radius: 6px;
                border: none;
            }
            QProgressBar::chunk {
                background: #f85149;
                border-radius: 6px;
            }
        """)
        bar_box.addWidget(self.lbl_score_status)
        bar_box.addWidget(self.score_bar)
        score_layout.addLayout(bar_box, 1)

        self.lbl_score_icon = QLabel("⬜")
        self.lbl_score_icon.setStyleSheet("font-size: 30px;")
        score_layout.addWidget(self.lbl_score_icon)

        layout.addWidget(score_card)

        # ── Conditions Checklist Group ──
        cond_frame = QFrame()
        cond_frame.setStyleSheet("background: #0d1117; border: 1.5px solid #21262d; border-radius: 10px; padding: 12px;")
        cond_layout = QVBoxLayout(cond_frame)
        cond_layout.setSpacing(8)

        cond_hdr = QHBoxLayout()
        self.lbl_cond_title = QLabel("📉 <b>PUTS — Setup Conditions (7 Rules)</b>")
        self.lbl_cond_title.setStyleSheet("font-size: 13px; color: #f85149;")
        cond_hdr.addWidget(self.lbl_cond_title)
        cond_hdr.addStretch()

        btn_check_all = QPushButton("✓ Check All")
        btn_check_all.setFixedHeight(26)
        btn_check_all.setStyleSheet("padding: 2px 10px; background: #21262d; border: 1px solid #30363d; border-radius: 5px; color: #3fb950; font-weight: bold; font-size: 11px;")
        btn_check_all.clicked.connect(self._check_all)
        cond_hdr.addWidget(btn_check_all)

        btn_clear_all = QPushButton("✕ Clear All")
        btn_clear_all.setFixedHeight(26)
        btn_clear_all.setStyleSheet("padding: 2px 10px; background: #21262d; border: 1px solid #30363d; border-radius: 5px; color: #8b949e; font-weight: bold; font-size: 11px;")
        btn_clear_all.clicked.connect(self._clear_all)
        cond_hdr.addWidget(btn_clear_all)

        cond_layout.addLayout(cond_hdr)

        self.items_container = QVBoxLayout()
        self.items_container.setSpacing(6)
        cond_layout.addLayout(self.items_container)

        self._render_condition_items()

        layout.addWidget(cond_frame)

        # ── Notes & Save Row ──
        notes_box = QVBoxLayout()
        notes_box.setSpacing(6)
        lbl_notes = QLabel("✏️ <b>Trade Note (optional):</b>")
        lbl_notes.setStyleSheet("font-size: 12px; color: #8b949e;")
        notes_box.addWidget(lbl_notes)

        self.edit_note = QTextEdit()
        self.edit_note.setPlaceholderText("e.g. Clean bounce off 9 EMA, QQQ selling off, solid risk/reward...")
        self.edit_note.setMaximumHeight(65)
        self.edit_note.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 6px; color: #e6edf3; font-size: 12px; padding: 6px;")
        notes_box.addWidget(self.edit_note)

        self.btn_save = QPushButton("💾 Save Trade Checklist")
        self.btn_save.setFixedHeight(40)
        self.btn_save.setStyleSheet("background: #8b2020; border: 2px solid #f85149; border-radius: 8px; color: #ffffff; font-size: 14px; font-weight: bold; cursor: pointer;")
        self.btn_save.clicked.connect(self._save_checklist)
        notes_box.addWidget(self.btn_save)

        self.lbl_feedback = QLabel("")
        self.lbl_feedback.setStyleSheet("font-size: 12px; color: #3fb950; font-weight: bold;")
        self.lbl_feedback.setAlignment(Qt.AlignCenter)
        self.lbl_feedback.hide()
        notes_box.addWidget(self.lbl_feedback)

        layout.addLayout(notes_box)

        # ── Saved History Section ──
        hist_title = QLabel("📋 <b>Saved Trade Checklists</b>")
        hist_title.setStyleSheet("font-size: 14px; color: #e6edf3; margin-top: 6px;")
        layout.addWidget(hist_title)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Date", "Time", "Type", "Score / Pts", "Checks Met", "Trade Note"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(180)
        self.table.setStyleSheet("""
            QTableWidget {
                background: #0d1117;
                alternate-background-color: #161b22;
                gridline-color: #21262d;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 8px;
            }
            QHeaderView::section {
                background: #161b22;
                color: #90caf9;
                font-weight: bold;
                padding: 6px;
                border: none;
                border-bottom: 1.5px solid #30363d;
            }
        """)
        layout.addWidget(self.table)

        scroll.setWidget(container)
        root.addWidget(scroll)

    def _set_type(self, t_type: str):
        self._trade_type = t_type
        self._checks.clear()
        if t_type == "PUTS":
            self.btn_puts.setStyleSheet("padding: 6px 14px; font-weight: bold; border-radius: 6px; background: #2d0e0e; border: 2px solid #f85149; color: #f85149;")
            self.btn_calls.setStyleSheet("padding: 6px 14px; font-weight: bold; border-radius: 6px; background: #161b22; border: 1.5px solid #30363d; color: #8b949e;")
            self.btn_save.setStyleSheet("background: #8b2020; border: 2px solid #f85149; border-radius: 8px; color: #ffffff; font-size: 14px; font-weight: bold;")
            self.lbl_cond_title.setText("📉 <b>PUTS — Setup Conditions (7 Rules)</b>")
            self.lbl_cond_title.setStyleSheet("font-size: 13px; color: #f85149;")
        else:
            self.btn_calls.setStyleSheet("padding: 6px 14px; font-weight: bold; border-radius: 6px; background: #0d2918; border: 2px solid #3fb950; color: #3fb950;")
            self.btn_puts.setStyleSheet("padding: 6px 14px; font-weight: bold; border-radius: 6px; background: #161b22; border: 1.5px solid #30363d; color: #8b949e;")
            self.btn_save.setStyleSheet("background: #196c2e; border: 2px solid #3fb950; border-radius: 8px; color: #ffffff; font-size: 14px; font-weight: bold;")
            self.lbl_cond_title.setText("📈 <b>CALLS — Setup Conditions (7 Rules)</b>")
            self.lbl_cond_title.setStyleSheet("font-size: 13px; color: #3fb950;")
        self._render_condition_items()
        self._update_score()

    def _render_condition_items(self):
        while self.items_container.count():
            item = self.items_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._checkbox_widgets.clear()
        conds = CL_CONDITIONS.get(self._trade_type, CL_CONDITIONS["PUTS"])
        is_put = self._trade_type == "PUTS"

        for c in conds:
            row_frame = QFrame()
            row_frame.setStyleSheet("""
                QFrame {
                    background: #161b22;
                    border: 1px solid #21262d;
                    border-radius: 6px;
                    padding: 4px 8px;
                }
                QFrame:hover {
                    border-color: #388bfd;
                }
            """)
            r_lay = QHBoxLayout(row_frame)
            r_lay.setContentsMargins(6, 4, 6, 4)
            r_lay.setSpacing(10)

            emoji = CL_EMOJIS.get(c["key"], "•")
            cb = QCheckBox(f"{emoji}  {c['label']}")
            cb.setStyleSheet("font-size: 13px; font-weight: bold; color: #e6edf3;")
            cb.setChecked(self._checks.get(c["key"], False))
            key = c["key"]
            cb.stateChanged.connect(lambda state, k=key: self._on_check_changed(k, state == Qt.Checked.value))
            self._checkbox_widgets[key] = cb
            r_lay.addWidget(cb)

            state_badge = QLabel(f" {c['state']} ")
            if is_put:
                state_badge.setStyleSheet("background: rgba(248,81,73,0.18); border: 1px solid rgba(248,81,73,0.45); color: #ff7b72; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 1px 5px;")
            else:
                state_badge.setStyleSheet("background: rgba(63,185,80,0.18); border: 1px solid rgba(63,185,80,0.45); color: #7ee787; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 1px 5px;")
            r_lay.addWidget(state_badge)

            sub_lbl = QLabel(c["sub"])
            sub_lbl.setStyleSheet("font-size: 11px; color: #8b949e;")
            r_lay.addWidget(sub_lbl, 1)

            pts_lbl = QLabel(f"+{c['pts']} pt")
            pts_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #58a6ff;")
            r_lay.addWidget(pts_lbl)

            self.items_container.addWidget(row_frame)

    def _on_check_changed(self, key: str, is_checked: bool):
        self._checks[key] = is_checked
        self._update_score()

    def _check_all(self):
        conds = CL_CONDITIONS.get(self._trade_type, CL_CONDITIONS["PUTS"])
        for c in conds:
            self._checks[c["key"]] = True
            if c["key"] in self._checkbox_widgets:
                self._checkbox_widgets[c["key"]].setChecked(True)
        self._update_score()

    def _clear_all(self):
        self._checks.clear()
        for cb in self._checkbox_widgets.values():
            cb.setChecked(False)
        self._update_score()

    def _update_score(self):
        conds = CL_CONDITIONS.get(self._trade_type, CL_CONDITIONS["PUTS"])
        earned = sum(c["pts"] for c in conds if self._checks.get(c["key"], False))
        count = sum(1 for c in conds if self._checks.get(c["key"], False))
        total_pts = 100
        pct = int((earned / total_pts) * 100)

        self.lbl_score_num.setText(str(earned))
        self.lbl_score_count.setText(f"{count} / {len(conds)} met")
        self.score_bar.setValue(pct)

        if pct >= 90:
            color = "#3fb950"
            label = f"🎯 Perfect! {earned} pts — all {len(conds)} conditions met (A+ Setup)"
            icon = "🚀"
        elif pct >= 70:
            color = "#ff9800"
            label = f"💪 Strong setup — {earned} pts ({count}/{len(conds)} met)"
            icon = "💪"
        elif pct >= 45:
            color = "#ffeb3b"
            label = f"⚠️ Partial setup — {earned} pts ({count}/{len(conds)} met)"
            icon = "⚠️"
        elif earned == 0:
            color = "#8b949e"
            label = f"Waiting for your checklist... (0/{len(conds)} met)"
            icon = "⬜"
        else:
            color = "#f85149"
            label = f"❌ Weak setup — only {earned} pts ({count}/{len(conds)} met)"
            icon = "❌"

        self.lbl_score_num.setStyleSheet(f"font-size: 32px; font-weight: 900; color: {color};")
        self.lbl_score_status.setText(label)
        self.lbl_score_icon.setText(icon)
        self.score_bar.setStyleSheet(f"""
            QProgressBar {{
                background: #21262d;
                border-radius: 6px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 6px;
            }}
        """)

    def _save_checklist(self):
        conds = CL_CONDITIONS.get(self._trade_type, CL_CONDITIONS["PUTS"])
        score = sum(1 for c in conds if self._checks.get(c["key"], False))
        total = len(conds)
        earned_pts = sum(c["pts"] for c in conds if self._checks.get(c["key"], False))
        total_pts = 100
        note = self.edit_note.toPlainText().strip()

        now = datetime.datetime.now()
        record = {
            "id": int(now.timestamp() * 1000),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "timestamp": now.isoformat(),
            "trade_type": self._trade_type,
            "checks": dict(self._checks),
            "score": score,
            "total": total,
            "earned_points": earned_pts,
            "total_points": total_pts,
            "note": note,
            "comment": "",
        }

        records = load_checklist_records()
        records.insert(0, record)
        save_checklist_records(records)

        self._clear_all()
        self.edit_note.clear()
        self._load_records_table()

        self.lbl_feedback.setText(f"✅ Saved! {earned_pts}/{total_pts} pts ({score}/{total} rules met)")
        self.lbl_feedback.show()
        self._status_msg(f"Checklist saved: {self._trade_type} {earned_pts} pts")

    def _load_records_table(self):
        records = load_checklist_records()
        self.table.setRowCount(len(records))

        for row, r in enumerate(records):
            date_item = QTableWidgetItem(r.get("date", ""))
            time_item = QTableWidgetItem(r.get("time", "")[:5])

            t_type = r.get("trade_type", "PUTS")
            type_item = QTableWidgetItem(t_type)
            if t_type == "PUTS":
                type_item.setForeground(QColor("#f85149"))
            else:
                type_item.setForeground(QColor("#3fb950"))
            type_item.setFont(QFont("Segoe UI", 9, QFont.Bold))

            pts = r.get("earned_points", r.get("score", 0))
            max_p = r.get("total_points", 100)
            score_item = QTableWidgetItem(f"{pts}/{max_p} pts")
            score_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            pct = int((pts / max_p) * 100) if max_p else 0
            if pct >= 80:
                score_item.setForeground(QColor("#3fb950"))
            elif pct >= 50:
                score_item.setForeground(QColor("#ff9800"))
            else:
                score_item.setForeground(QColor("#f85149"))

            checks_str = f"{r.get('score', 0)} / {r.get('total', 7)} rules"
            checks_item = QTableWidgetItem(checks_str)

            note_item = QTableWidgetItem(r.get("note", ""))

            self.table.setItem(row, 0, date_item)
            self.table.setItem(row, 1, time_item)
            self.table.setItem(row, 2, type_item)
            self.table.setItem(row, 3, score_item)
            self.table.setItem(row, 4, checks_item)
            self.table.setItem(row, 5, note_item)
