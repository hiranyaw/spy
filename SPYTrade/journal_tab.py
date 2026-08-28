"""journal_tab.py — Trade Journal tab widget for SPYTrade.

Provides:
  • Daily entry form (summary text box, P&L, trades, win rate, mood, tags)
  • Monthly calendar grid to browse past entries
  • Monthly analysis summary panel with aggregate stats
"""

from __future__ import annotations

import calendar
import datetime
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox,
    QDateEdit, QScrollArea, QFrame, QGridLayout, QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QDate

from journal_store import save_entry, load_entry, load_month, get_monthly_stats

log = logging.getLogger(__name__)


class JournalTab(QWidget):
    """Main journal tab containing entry form, monthly calendar, and analysis."""

    def __init__(self, status_callback=None, parent=None):
        super().__init__(parent)
        self._status_cb = status_callback  # optional callback to show status bar msg
        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        # ── Section A: Daily Entry Form ──────────────────────────────────────
        form_frame = QFrame()
        form_frame.setObjectName("journal_section")
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form_layout.setSpacing(8)

        form_title = QLabel("📝 <b>Daily Trade Journal Entry</b>")
        form_title.setObjectName("section_title")
        form_layout.addWidget(form_title)

        # Date selector row
        date_row = QHBoxLayout()
        date_row.setSpacing(8)
        date_lbl = QLabel("<b>Date:</b>")
        date_lbl.setFixedWidth(80)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setFixedWidth(160)
        self.date_edit.setObjectName("journal_input")
        date_row.addWidget(date_lbl)
        date_row.addWidget(self.date_edit)
        date_row.addStretch()

        load_btn = QPushButton("📂 Load Entry")
        load_btn.setObjectName("journal_btn")
        load_btn.setFixedWidth(120)
        load_btn.clicked.connect(self._load_entry)
        date_row.addWidget(load_btn)

        form_layout.addLayout(date_row)

        # Summary text box
        summary_lbl = QLabel("<b>Summary:</b>")
        form_layout.addWidget(summary_lbl)
        self.summary_edit = QTextEdit()
        self.summary_edit.setObjectName("journal_text")
        self.summary_edit.setPlaceholderText(
            "Write your daily trading summary here...\n\n"
            "• What setups did you take?\n"
            "• What worked / didn't work?\n"
            "• Key lessons learned?"
        )
        self.summary_edit.setMinimumHeight(140)
        self.summary_edit.setMaximumHeight(220)
        form_layout.addWidget(self.summary_edit)

        # Inline fields row 1: P&L + Trades Taken + Win Rate
        fields_row1 = QHBoxLayout()
        fields_row1.setSpacing(12)

        # P&L
        pnl_lbl = QLabel("<b>P&L ($):</b>")
        self.pnl_spin = QDoubleSpinBox()
        self.pnl_spin.setObjectName("journal_input")
        self.pnl_spin.setRange(-99999.99, 99999.99)
        self.pnl_spin.setDecimals(2)
        self.pnl_spin.setPrefix("$ ")
        self.pnl_spin.setFixedWidth(140)
        fields_row1.addWidget(pnl_lbl)
        fields_row1.addWidget(self.pnl_spin)

        # Trades Taken
        trades_lbl = QLabel("<b>Trades:</b>")
        self.trades_spin = QSpinBox()
        self.trades_spin.setObjectName("journal_input")
        self.trades_spin.setRange(0, 999)
        self.trades_spin.setFixedWidth(80)
        fields_row1.addWidget(trades_lbl)
        fields_row1.addWidget(self.trades_spin)

        # Win Rate
        wr_lbl = QLabel("<b>Win Rate:</b>")
        self.winrate_edit = QLineEdit()
        self.winrate_edit.setObjectName("journal_input")
        self.winrate_edit.setPlaceholderText("e.g. 3/5 or 60%")
        self.winrate_edit.setFixedWidth(120)
        fields_row1.addWidget(wr_lbl)
        fields_row1.addWidget(self.winrate_edit)

        fields_row1.addStretch()
        form_layout.addLayout(fields_row1)

        # Inline fields row 2: Mood + Tags
        fields_row2 = QHBoxLayout()
        fields_row2.setSpacing(12)

        mood_lbl = QLabel("<b>Mood:</b>")
        self.mood_combo = QComboBox()
        self.mood_combo.setObjectName("journal_input")
        self.mood_combo.addItems([
            "", "confident", "disciplined", "neutral",
            "frustrated", "impulsive", "anxious", "focused",
        ])
        self.mood_combo.setFixedWidth(140)
        fields_row2.addWidget(mood_lbl)
        fields_row2.addWidget(self.mood_combo)

        tags_lbl = QLabel("<b>Tags:</b>")
        self.tags_edit = QLineEdit()
        self.tags_edit.setObjectName("journal_input")
        self.tags_edit.setPlaceholderText("trend-day, gap-fill, reversal")
        self.tags_edit.setMinimumWidth(200)
        fields_row2.addWidget(tags_lbl)
        fields_row2.addWidget(self.tags_edit)

        fields_row2.addStretch()
        form_layout.addLayout(fields_row2)

        # Save button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("💾  Save Entry")
        save_btn.setObjectName("save_btn")
        save_btn.setFixedWidth(160)
        save_btn.clicked.connect(self._save_entry)
        btn_row.addWidget(save_btn)

        clear_btn = QPushButton("🗑  Clear Form")
        clear_btn.setObjectName("journal_btn")
        clear_btn.setFixedWidth(120)
        clear_btn.clicked.connect(self._clear_form)
        btn_row.addWidget(clear_btn)
        form_layout.addLayout(btn_row)

        layout.addWidget(form_frame)

        # ── Section B: Monthly Calendar View ─────────────────────────────────
        cal_frame = QFrame()
        cal_frame.setObjectName("journal_section")
        cal_layout = QVBoxLayout(cal_frame)
        cal_layout.setContentsMargins(16, 14, 16, 14)
        cal_layout.setSpacing(8)

        # Month navigation header
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        cal_title = QLabel("📅 <b>Monthly Journal View</b>")
        cal_title.setObjectName("section_title")
        nav_row.addWidget(cal_title)
        nav_row.addStretch()

        self.prev_btn = QPushButton("◄")
        self.prev_btn.setObjectName("nav_btn")
        self.prev_btn.setFixedSize(36, 30)
        self.prev_btn.clicked.connect(self._prev_month)
        nav_row.addWidget(self.prev_btn)

        today = datetime.date.today()
        self._cal_year = today.year
        self._cal_month = today.month
        self.month_label = QLabel()
        self.month_label.setObjectName("month_label")
        self.month_label.setAlignment(Qt.AlignCenter)
        self.month_label.setFixedWidth(180)
        nav_row.addWidget(self.month_label)

        self.next_btn = QPushButton("►")
        self.next_btn.setObjectName("nav_btn")
        self.next_btn.setFixedSize(36, 30)
        self.next_btn.clicked.connect(self._next_month)
        nav_row.addWidget(self.next_btn)

        cal_layout.addLayout(nav_row)

        # Calendar grid (rendered as HTML label for consistent dark styling)
        self.calendar_label = QLabel()
        self.calendar_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.calendar_label.setWordWrap(True)
        self.calendar_label.setTextFormat(Qt.RichText)
        self.calendar_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.calendar_label.linkActivated.connect(self._on_calendar_click)
        cal_layout.addWidget(self.calendar_label)

        layout.addWidget(cal_frame)

        # ── Section C: Monthly Analysis ──────────────────────────────────────
        analysis_frame = QFrame()
        analysis_frame.setObjectName("journal_section")
        analysis_layout = QVBoxLayout(analysis_frame)
        analysis_layout.setContentsMargins(16, 14, 16, 14)
        analysis_layout.setSpacing(8)

        self.analysis_label = QLabel()
        self.analysis_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.analysis_label.setWordWrap(True)
        self.analysis_label.setTextFormat(Qt.RichText)
        analysis_layout.addWidget(self.analysis_label)

        layout.addWidget(analysis_frame)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

        # Initial render
        self._refresh_calendar()

    # ── Form Actions ──────────────────────────────────────────────────────────

    def _save_entry(self):
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        summary = self.summary_edit.toPlainText().strip()
        pnl = self.pnl_spin.value()
        trades = self.trades_spin.value()
        winrate = self.winrate_edit.text().strip()
        mood = self.mood_combo.currentText()
        tags = self.tags_edit.text().strip()

        if not summary and pnl == 0 and trades == 0:
            QMessageBox.warning(
                self, "Empty Entry",
                "Please write a summary or enter trade data before saving."
            )
            return

        try:
            save_entry(date_str, summary, pnl, trades, winrate, mood, tags)
            if self._status_cb:
                self._status_cb(f"✅ Journal entry saved for {date_str}")
            log.info("Journal entry saved for %s", date_str)

            # Refresh calendar if we're viewing the same month
            dt = datetime.date.fromisoformat(date_str)
            if dt.year == self._cal_year and dt.month == self._cal_month:
                self._refresh_calendar()
        except Exception as e:
            log.exception("Failed to save journal: %s", e)
            QMessageBox.critical(self, "Save Error", f"Failed to save entry:\n{e}")

    def _load_entry(self):
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        entry = load_entry(date_str)
        if entry is None:
            self._clear_form(keep_date=True)
            if self._status_cb:
                self._status_cb(f"No journal entry found for {date_str}")
            return

        self.summary_edit.setPlainText(entry.get("summary", ""))
        self.pnl_spin.setValue(entry.get("pnl", 0.0))
        self.trades_spin.setValue(entry.get("trades_taken", 0))
        self.winrate_edit.setText(entry.get("win_rate", ""))

        mood = entry.get("mood", "")
        idx = self.mood_combo.findText(mood)
        self.mood_combo.setCurrentIndex(max(idx, 0))

        self.tags_edit.setText(entry.get("tags", ""))

        if self._status_cb:
            self._status_cb(f"📂 Loaded journal entry for {date_str}")

    def _clear_form(self, keep_date: bool = False):
        if not keep_date:
            self.date_edit.setDate(QDate.currentDate())
        self.summary_edit.clear()
        self.pnl_spin.setValue(0.0)
        self.trades_spin.setValue(0)
        self.winrate_edit.clear()
        self.mood_combo.setCurrentIndex(0)
        self.tags_edit.clear()

    # ── Calendar Navigation ───────────────────────────────────────────────────

    def _prev_month(self):
        if self._cal_month == 1:
            self._cal_month = 12
            self._cal_year -= 1
        else:
            self._cal_month -= 1
        self._refresh_calendar()

    def _next_month(self):
        if self._cal_month == 12:
            self._cal_month = 1
            self._cal_year += 1
        else:
            self._cal_month += 1
        self._refresh_calendar()

    def _on_calendar_click(self, link: str):
        """Handle clicking a date in the calendar grid."""
        if link.startswith("date:"):
            date_str = link.replace("date:", "")
            qdate = QDate.fromString(date_str, "yyyy-MM-dd")
            if qdate.isValid():
                self.date_edit.setDate(qdate)
                self._load_entry()

    # ── Render Calendar & Analysis ────────────────────────────────────────────

    def _refresh_calendar(self):
        self.month_label.setText(
            f"<b style='color:#90caf9;font-size:15px'>"
            f"{calendar.month_name[self._cal_month]} {self._cal_year}</b>"
        )
        entries = load_month(self._cal_year, self._cal_month)
        self.calendar_label.setText(self._render_calendar_html(entries))
        self.analysis_label.setText(self._render_analysis_html())

    def _render_calendar_html(self, entries: dict) -> str:
        """Build an HTML table calendar for the month with entry summaries."""
        cal = calendar.monthcalendar(self._cal_year, self._cal_month)
        today = datetime.date.today()

        # Header row
        header_cells = ""
        for day_name in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            header_cells += (
                f"<th style='padding:6px 4px;color:#78909c;font-size:11px;"
                f"font-weight:bold;text-align:center;border-bottom:1px solid #1e3a5f;'>"
                f"{day_name}</th>"
            )

        rows_html = ""
        for week in cal:
            cells = ""
            for day in week:
                if day == 0:
                    cells += "<td style='padding:4px;'></td>"
                    continue

                date_str = f"{self._cal_year:04d}-{self._cal_month:02d}-{day:02d}"
                entry = entries.get(date_str)
                is_today = (
                    self._cal_year == today.year
                    and self._cal_month == today.month
                    and day == today.day
                )

                # Cell styling
                if is_today:
                    border = "border:2px solid #1f6feb;"
                    bg = "background:rgba(31,111,235,0.12);"
                else:
                    border = "border:1px solid #1a2740;"
                    bg = "background:#0d1826;"

                if entry:
                    pnl = entry.get("pnl", 0.0)
                    summary = entry.get("summary", "")
                    preview = summary[:45] + "…" if len(summary) > 45 else summary
                    preview = preview.replace("\n", " ")

                    if pnl > 0:
                        pnl_col = "#00e676"
                        pnl_str = f"+${pnl:.0f}"
                    elif pnl < 0:
                        pnl_col = "#f44336"
                        pnl_str = f"-${abs(pnl):.0f}"
                    else:
                        pnl_col = "#78909c"
                        pnl_str = "$0"

                    dot = f"<span style='color:{pnl_col};font-size:10px;'>●</span> "
                    pnl_tag = (
                        f"<div style='font-size:11px;font-weight:bold;color:{pnl_col};"
                        f"font-family:\"Courier New\",monospace;'>{pnl_str}</div>"
                    )
                    preview_tag = (
                        f"<div style='font-size:10px;color:#8b949e;overflow:hidden;"
                        f"white-space:nowrap;text-overflow:ellipsis;max-width:130px;'>"
                        f"{preview}</div>"
                    ) if preview else ""
                else:
                    dot = ""
                    pnl_tag = ""
                    preview_tag = ""

                today_badge = (
                    "<span style='font-size:9px;color:#1f6feb;font-weight:bold;'> TODAY</span>"
                    if is_today else ""
                )

                cells += (
                    f"<td style='{bg}{border}border-radius:6px;padding:6px 5px;"
                    f"vertical-align:top;min-width:100px;max-width:140px;cursor:pointer;'>"
                    f"<a href='date:{date_str}' style='text-decoration:none;display:block;'>"
                    f"<div style='font-size:13px;font-weight:bold;color:#e6edf3;'>"
                    f"{dot}{day}{today_badge}</div>"
                    f"{pnl_tag}{preview_tag}"
                    f"</a></td>"
                )

            rows_html += f"<tr>{cells}</tr>"

        return (
            "<table style='border-collapse:separate;border-spacing:4px;width:100%;'>"
            f"<tr>{header_cells}</tr>"
            f"{rows_html}"
            "</table>"
        )

    def _render_analysis_html(self) -> str:
        """Build an HTML panel with monthly aggregate stats."""
        stats = get_monthly_stats(self._cal_year, self._cal_month)
        month_name = calendar.month_name[self._cal_month]

        total_pnl = stats["total_pnl"]
        pnl_col = "#00e676" if total_pnl >= 0 else "#f44336"
        pnl_sign = "+" if total_pnl >= 0 else ""

        days_traded = stats["days_traded"]
        days_profitable = stats["days_profitable"]
        days_losing = stats["days_losing"]
        days_even = days_traded - days_profitable - days_losing
        win_pct = (days_profitable / days_traded * 100) if days_traded > 0 else 0

        avg_pnl = stats["avg_daily_pnl"]
        avg_col = "#00e676" if avg_pnl >= 0 else "#f44336"
        avg_sign = "+" if avg_pnl >= 0 else ""

        # Best / worst day
        best = stats["best_day"]
        worst = stats["worst_day"]
        if best:
            best_str = (
                f"<span style='color:#00e676;font-weight:bold;'>"
                f"+${best['pnl']:.0f}</span> on {best['date']}"
            )
        else:
            best_str = "—"

        if worst:
            worst_str = (
                f"<span style='color:#f44336;font-weight:bold;'>"
                f"-${abs(worst['pnl']):.0f}</span> on {worst['date']}"
            )
        else:
            worst_str = "—"

        # Top tags
        top_tags = stats["top_tags"]
        if top_tags:
            tags_str = "  ".join(
                f"<span style='background:#1e3a5f;color:#90caf9;padding:2px 8px;"
                f"border-radius:4px;font-size:11px;margin-right:4px;'>"
                f"{tag} ({count})</span>"
                for tag, count in top_tags
            )
        else:
            tags_str = "<span style='color:#546e7a;'>No tags recorded</span>"

        # Mood distribution
        mood_counts = stats["mood_counts"]
        if mood_counts:
            mood_parts = []
            for mood, count in sorted(mood_counts.items(), key=lambda x: x[1], reverse=True):
                mood_parts.append(
                    f"<span style='color:#e0e0e0;'>{mood}</span> "
                    f"<span style='color:#78909c;'>({count})</span>"
                )
            mood_str = " &nbsp;•&nbsp; ".join(mood_parts)
        else:
            mood_str = "<span style='color:#546e7a;'>No mood data</span>"

        def _stat_card(label: str, value: str, color: str) -> str:
            return (
                f"<div style='flex:1;min-width:130px;background:#111d2e;"
                f"border:1px solid #1e3a5f;border-top:3px solid {color};"
                f"border-radius:6px;padding:10px 12px;margin:3px;'>"
                f"<div style='font-size:11px;color:#78909c;font-weight:bold;"
                f"text-transform:uppercase;'>{label}</div>"
                f"<div style='font-size:18px;font-weight:900;color:{color};"
                f"font-family:\"Courier New\",monospace;margin-top:3px;'>{value}</div>"
                f"</div>"
            )

        cards = (
            _stat_card("Total P&L", f"{pnl_sign}${total_pnl:.0f}", pnl_col)
            + _stat_card("Days Traded", str(days_traded), "#90caf9")
            + _stat_card("Win Rate", f"{win_pct:.0f}%", "#00e676" if win_pct >= 50 else "#ff9800")
            + _stat_card("Total Trades", str(stats["total_trades"]), "#90caf9")
            + _stat_card("Avg Daily P&L", f"{avg_sign}${avg_pnl:.0f}", avg_col)
            + _stat_card(
                "W / L / E",
                f"{days_profitable} / {days_losing} / {days_even}",
                "#90caf9",
            )
        )

        return (
            f"<div style='background:#0a121c;border-radius:10px;border:1.5px solid #162a45;"
            f"padding:14px 16px;'>"

            # Title
            f"<div style='font-size:14px;font-weight:bold;color:#90caf9;margin-bottom:10px;'>"
            f"📊 <b>Monthly Analysis — {month_name} {self._cal_year}</b></div>"

            # Stat cards row
            f"<div style='display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px;'>"
            f"{cards}</div>"

            # Best / Worst day
            f"<div style='display:flex;gap:20px;margin-bottom:10px;font-size:13px;'>"
            f"<div><span style='color:#78909c;font-weight:bold;'>🏆 Best Day:</span> {best_str}</div>"
            f"<div><span style='color:#78909c;font-weight:bold;'>💀 Worst Day:</span> {worst_str}</div>"
            f"</div>"

            # Tags
            f"<div style='margin-bottom:8px;'>"
            f"<span style='color:#78909c;font-size:12px;font-weight:bold;'>🏷 Top Tags: </span>"
            f"{tags_str}</div>"

            # Mood
            f"<div>"
            f"<span style='color:#78909c;font-size:12px;font-weight:bold;'>😊 Mood: </span>"
            f"{mood_str}</div>"

            f"</div>"
        )
