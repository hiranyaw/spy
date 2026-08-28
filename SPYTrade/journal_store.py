"""journal_store.py — JSON-based daily trade journal persistence for SPYTrade.

Stores one JSON file per month in a ``journal_data/`` folder beside the app.
Each file maps date strings ("YYYY-MM-DD") to entry dicts.

Usage::

    from journal_store import save_entry, load_entry, load_month, get_monthly_stats

    save_entry("2026-08-27", summary="Great day...", pnl=250.0, ...)
    entry = load_entry("2026-08-27")
    month  = load_month(2026, 8)
    stats  = get_monthly_stats(2026, 8)
"""

from __future__ import annotations

import json
import logging
import pathlib
import datetime
from typing import Any

log = logging.getLogger(__name__)

_DATA_DIR = pathlib.Path(__file__).parent / "journal_data"


def _month_file(year: int, month: int) -> pathlib.Path:
    """Return the path for a given month's JSON file."""
    return _DATA_DIR / f"{year:04d}-{month:02d}.json"


def _read_month_file(year: int, month: int) -> dict[str, dict]:
    """Read and return the contents of a month file, or empty dict."""
    fp = _month_file(year, month)
    if not fp.exists():
        return {}
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning("Failed to read journal file %s: %s", fp, e)
        return {}


def _write_month_file(year: int, month: int, data: dict[str, dict]) -> None:
    """Write data to the month file, creating dirs as needed."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    fp = _month_file(year, month)
    try:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info("Journal saved to %s", fp)
    except Exception as e:
        log.error("Failed to write journal file %s: %s", fp, e)
        raise


# ── Public API ────────────────────────────────────────────────────────────────

def save_entry(
    date_str: str,
    summary: str = "",
    pnl: float = 0.0,
    trades_taken: int = 0,
    win_rate: str = "",
    mood: str = "",
    tags: str = "",
) -> None:
    """Save or update a journal entry for the given date (YYYY-MM-DD)."""
    dt = datetime.date.fromisoformat(date_str)
    data = _read_month_file(dt.year, dt.month)

    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    existing = data.get(date_str)

    entry: dict[str, Any] = {
        "summary": summary,
        "pnl": pnl,
        "trades_taken": trades_taken,
        "win_rate": win_rate,
        "mood": mood,
        "tags": tags,
        "updated_at": now_iso,
    }
    if existing and existing.get("created_at"):
        entry["created_at"] = existing["created_at"]
    else:
        entry["created_at"] = now_iso

    data[date_str] = entry
    _write_month_file(dt.year, dt.month, data)


def load_entry(date_str: str) -> dict | None:
    """Load a single journal entry by date string, or None if not found."""
    dt = datetime.date.fromisoformat(date_str)
    data = _read_month_file(dt.year, dt.month)
    return data.get(date_str)


def load_month(year: int, month: int) -> dict[str, dict]:
    """Return all journal entries for the given month."""
    return _read_month_file(year, month)


def get_monthly_stats(year: int, month: int) -> dict:
    """Compute aggregate statistics for a month.

    Returns a dict with:
        total_pnl, total_trades, days_traded, days_profitable, days_losing,
        best_day, worst_day, avg_daily_pnl, top_tags, mood_counts
    """
    entries = _read_month_file(year, month)
    if not entries:
        return {
            "total_pnl": 0.0,
            "total_trades": 0,
            "days_traded": 0,
            "days_profitable": 0,
            "days_losing": 0,
            "best_day": None,
            "worst_day": None,
            "avg_daily_pnl": 0.0,
            "top_tags": [],
            "mood_counts": {},
        }

    total_pnl = 0.0
    total_trades = 0
    days_traded = 0
    days_profitable = 0
    days_losing = 0
    best_day = None
    best_pnl = float("-inf")
    worst_day = None
    worst_pnl = float("inf")
    tag_counts: dict[str, int] = {}
    mood_counts: dict[str, int] = {}

    for date_str, entry in sorted(entries.items()):
        pnl = entry.get("pnl", 0.0)
        trades = entry.get("trades_taken", 0)

        # Only count days that have some content
        if not entry.get("summary", "").strip() and pnl == 0 and trades == 0:
            continue

        days_traded += 1
        total_pnl += pnl
        total_trades += trades

        if pnl > 0:
            days_profitable += 1
        elif pnl < 0:
            days_losing += 1

        if pnl > best_pnl:
            best_pnl = pnl
            best_day = {"date": date_str, "pnl": pnl}
        if pnl < worst_pnl:
            worst_pnl = pnl
            worst_day = {"date": date_str, "pnl": pnl}

        # Tags
        raw_tags = entry.get("tags", "")
        if raw_tags:
            for tag in raw_tags.split(","):
                tag = tag.strip().lower()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Mood
        mood = entry.get("mood", "").strip()
        if mood:
            mood_counts[mood] = mood_counts.get(mood, 0) + 1

    avg_daily_pnl = total_pnl / days_traded if days_traded > 0 else 0.0
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total_pnl": total_pnl,
        "total_trades": total_trades,
        "days_traded": days_traded,
        "days_profitable": days_profitable,
        "days_losing": days_losing,
        "best_day": best_day,
        "worst_day": worst_day,
        "avg_daily_pnl": avg_daily_pnl,
        "top_tags": top_tags,
        "mood_counts": mood_counts,
    }
