"""trade_store.py — Trade data persistence, CSV ingestion, and condition analytics.

Stores individual trade records in JSON format with classifications:
  • is_b_trade (bool)
  • is_9_21_cross (bool)
  • early_exit (bool)
  • direction_right (bool)
  • pnl, symbol, side, prices, notes, etc.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import logging
import pathlib
import uuid
from typing import Any

log = logging.getLogger(__name__)

_DATA_DIR = pathlib.Path(__file__).parent / "journal_data"
_TRADES_FILE = _DATA_DIR / "trades.json"


def _ensure_dir():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_all_trades() -> list[dict[str, Any]]:
    """Load all trade records from trades.json."""
    _ensure_dir()
    if not _TRADES_FILE.exists():
        return []
    try:
        with open(_TRADES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return list(data.values())
            return []
    except Exception as e:
        log.error("Failed to read %s: %s", _TRADES_FILE, e)
        return []


def save_all_trades(trades: list[dict[str, Any]]) -> None:
    """Save all trade records to trades.json."""
    _ensure_dir()
    try:
        with open(_TRADES_FILE, "w", encoding="utf-8") as f:
            json.dump(trades, f, indent=2, ensure_ascii=False)
        log.info("Saved %d trades to %s", len(trades), _TRADES_FILE)
    except Exception as e:
        log.error("Failed to write %s: %s", _TRADES_FILE, e)
        raise


def save_or_update_trade(trade: dict[str, Any]) -> dict[str, Any]:
    """Insert or update a single trade record."""
    trades = load_all_trades()
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")

    trade_id = trade.get("id")
    if not trade_id:
        trade_id = f"tr_{uuid.uuid4().hex[:10]}"
        trade["id"] = trade_id
        trade["created_at"] = now_iso

    trade["updated_at"] = now_iso

    # Ensure boolean fields
    trade["is_b_trade"] = bool(trade.get("is_b_trade", False))
    trade["is_9_21_cross"] = bool(trade.get("is_9_21_cross", False))
    trade["early_exit"] = bool(trade.get("early_exit", False))
    trade["direction_right"] = bool(trade.get("direction_right", True))

    # Ensure numeric fields
    trade["pnl"] = float(trade.get("pnl", 0.0))
    trade["trade_cost"] = float(trade.get("trade_cost", 1.0))
    trade["entry_price"] = float(trade.get("entry_price", 0.0))
    trade["exit_price"] = float(trade.get("exit_price", 0.0))
    trade["qty"] = float(trade.get("qty", 1.0))

    # Ensure exit_reason
    exit_r = str(trade.get("exit_reason", "")).upper()
    if exit_r not in ("TARGET", "STOP_LOSS", "EARLY_EXIT", "BREAKEVEN"):
        exit_r = "TARGET" if trade["pnl"] > 0 else ("STOP_LOSS" if trade["pnl"] < 0 else "BREAKEVEN")
    trade["exit_reason"] = exit_r

    # Find existing index
    idx = -1
    for i, t in enumerate(trades):
        if t.get("id") == trade_id:
            idx = i
            break

    if idx >= 0:
        trades[idx] = trade
    else:
        trades.append(trade)

    # Sort trades descending by date and time
    trades.sort(
        key=lambda x: (x.get("date", ""), x.get("time", "")),
        reverse=True,
    )

    save_all_trades(trades)
    return trade


def delete_trade(trade_id: str) -> bool:
    """Delete a trade by its ID."""
    trades = load_all_trades()
    initial_len = len(trades)
    trades = [t for t in trades if t.get("id") != trade_id]
    if len(trades) < initial_len:
        save_all_trades(trades)
        return True
    return False


def get_trades(
    year: int | None = None,
    month: int | None = None,
    date_str: str | None = None,
    search_query: str | None = None,
) -> list[dict[str, Any]]:
    """Filter trades by year, month, date, or text query."""
    trades = load_all_trades()
    results = []

    for t in trades:
        t_date = t.get("date", "")
        if not t_date:
            continue

        try:
            dt = datetime.date.fromisoformat(t_date)
        except ValueError:
            continue

        if year is not None and dt.year != year:
            continue
        if month is not None and dt.month != month:
            continue
        if date_str is not None and t_date != date_str:
            continue

        if search_query:
            q = search_query.strip().lower()
            text_corpus = (
                f"{t.get('symbol', '')} {t.get('side', '')} {t.get('notes', '')} "
                f"{t.get('date', '')} {t.get('tags', '')}"
            ).lower()
            if q not in text_corpus:
                continue

        results.append(t)

    # Sort descending
    results.sort(
        key=lambda x: (x.get("date", ""), x.get("time", "")),
        reverse=True,
    )
    return results


def _calc_stats_for_subset(subset: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate win rate, total Net P&L (after $1 trade cost/trade), gross P&L, total cost, wins, losses."""
    total = len(subset)
    if total == 0:
        return {
            "count": 0,
            "wins": 0,
            "losses": 0,
            "even": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "gross_pnl": 0.0,
            "total_cost": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
        }

    # Net PnL per trade = gross pnl - trade_cost ($1 default)
    net_pnls = [float(t.get("pnl", 0.0)) - float(t.get("trade_cost", 1.0)) for t in subset]
    gross_pnls = [float(t.get("pnl", 0.0)) for t in subset]
    costs = [float(t.get("trade_cost", 1.0)) for t in subset]

    wins = sum(1 for npnl in net_pnls if npnl > 0)
    losses = sum(1 for npnl in net_pnls if npnl < 0)
    even = sum(1 for npnl in net_pnls if npnl == 0)
    win_rate = (wins / total * 100.0) if total > 0 else 0.0
    total_net_pnl = sum(net_pnls)
    total_gross_pnl = sum(gross_pnls)
    total_cost = sum(costs)
    avg_pnl = total_net_pnl / total if total > 0 else 0.0

    gross_profit = sum(npnl for npnl in net_pnls if npnl > 0)
    gross_loss = abs(sum(npnl for npnl in net_pnls if npnl < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0)

    return {
        "count": total,
        "wins": wins,
        "losses": losses,
        "even": even,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_net_pnl, 2),
        "gross_pnl": round(total_gross_pnl, 2),
        "total_cost": round(total_cost, 2),
        "avg_pnl": round(avg_pnl, 2),
        "profit_factor": round(profit_factor, 2),
    }


def get_condition_stats(year: int | None = None, month: int | None = None) -> dict[str, Any]:
    """Compute performance breakdown across trade conditions."""
    trades = get_trades(year=year, month=month)

    all_stats = _calc_stats_for_subset(trades)

    # Condition subsets
    b_trades = [t for t in trades if t.get("is_b_trade", False)]
    non_b_trades = [t for t in trades if not t.get("is_b_trade", False)]

    cross_9_21 = [t for t in trades if t.get("is_9_21_cross", False)]
    non_cross_9_21 = [t for t in trades if not t.get("is_9_21_cross", False)]

    early_exit = [t for t in trades if t.get("early_exit", False)]
    normal_exit = [t for t in trades if not t.get("early_exit", False)]

    dir_right = [t for t in trades if t.get("direction_right", True)]
    dir_wrong = [t for t in trades if not t.get("direction_right", True)]

    return {
        "all": all_stats,
        "b_trade": _calc_stats_for_subset(b_trades),
        "non_b_trade": _calc_stats_for_subset(non_b_trades),
        "cross_9_21": _calc_stats_for_subset(cross_9_21),
        "non_cross_9_21": _calc_stats_for_subset(non_cross_9_21),
        "early_exit": _calc_stats_for_subset(early_exit),
        "normal_exit": _calc_stats_for_subset(normal_exit),
        "direction_right": _calc_stats_for_subset(dir_right),
        "direction_wrong": _calc_stats_for_subset(dir_wrong),
        "total_trades_count": len(trades),
    }


def import_trades_from_csv(file_path: str | pathlib.Path) -> tuple[int, int, list[str]]:
    """Parse and import trades from a CSV file.

    Returns:
        (imported_count, skipped_count, list_of_warnings_or_errors)
    """
    path = pathlib.Path(file_path)
    if not path.exists():
        return 0, 0, [f"File not found: {file_path}"]

    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return 0, 0, [f"Could not read CSV file: {e}"]

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return 0, 0, ["CSV file is empty."]

    header_row_idx = 0
    # Find header row
    headers = [h.strip().lower() for h in rows[0]]
    if not any("date" in h or "pnl" in h or "profit" in h or "symbol" in h for h in headers):
        # Look in next few rows for a header
        for i in range(1, min(5, len(rows))):
            h_candidate = [h.strip().lower() for h in rows[i]]
            if any("date" in h or "pnl" in h or "profit" in h or "symbol" in h for h in h_candidate):
                header_row_idx = i
                headers = h_candidate
                break

    data_rows = rows[header_row_idx + 1 :]

    # Helper to find column index by synonyms
    def find_col(synonyms: list[str]) -> int:
        for syn in synonyms:
            for idx, h in enumerate(headers):
                if syn in h:
                    return idx
        return -1

    date_col = find_col(["date", "time", "timestamp", "datetime", "closed"])
    time_col = find_col(["exec time", "time", "fill time"])
    sym_col = find_col(["symbol", "ticker", "instrument", "contract", "description"])
    side_col = find_col(["side", "action", "type", "buy/sell", "direction"])
    pnl_col = find_col(["pnl", "p&l", "profit", "gain", "net", "amount", "realized"])
    qty_col = find_col(["qty", "quantity", "contracts", "shares", "size"])
    entry_col = find_col(["entry price", "open price", "buy price", "entry", "avg price"])
    exit_col = find_col(["exit price", "close price", "sell price", "exit"])
    cost_col = find_col(["trade cost", "cost", "fee", "commission", "comm", "trade_cost"])
    b_trade_col = find_col(["b_trade", "b trade", "b-trade"])
    cross_col = find_col(["9_21", "9 21", "9/21", "cross"])
    early_col = find_col(["early", "early exit", "early_exit"])
    dir_col = find_col(["dir", "direction", "direction right", "right/wrong"])
    notes_col = find_col(["notes", "comment", "setup", "reason", "tags"])

    imported = 0
    skipped = 0
    messages = []
    existing_trades = load_all_trades()

    for r_idx, row in enumerate(data_rows, start=header_row_idx + 2):
        if not row or all(not cell.strip() for cell in row):
            continue

        def get_val(col_idx: int, default: str = "") -> str:
            if 0 <= col_idx < len(row):
                return row[col_idx].strip()
            return default

        raw_date = get_val(date_col)
        # Parse date and time
        date_str = ""
        time_str = "09:30:00"

        # Try to parse raw_date
        clean_date = raw_date.replace("T", " ").replace("/", "-")
        # Try various formats
        parsed_dt = None
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%m-%d-%Y %H:%M:%S",
            "%m-%d-%Y %H:%M",
            "%m-%d-%Y",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y",
        ):
            try:
                parsed_dt = datetime.datetime.strptime(clean_date.split(".")[0], fmt)
                break
            except ValueError:
                pass

        if parsed_dt:
            date_str = parsed_dt.strftime("%Y-%m-%d")
            time_str = parsed_dt.strftime("%H:%M:%S")
        else:
            # Fallback to today if not parseable
            date_str = datetime.date.today().isoformat()

        if time_col >= 0 and time_col != date_col:
            raw_time = get_val(time_col)
            if raw_time:
                time_str = raw_time

        raw_sym = get_val(sym_col, "SPY").upper() or "SPY"
        raw_side = get_val(side_col, "BUY").upper() or "BUY"

        # PnL parse
        raw_pnl = get_val(pnl_col, "0.0")
        raw_pnl = raw_pnl.replace("$", "").replace(",", "").replace(" ", "").replace("(", "-").replace(")", "")
        try:
            pnl_val = float(raw_pnl)
        except ValueError:
            pnl_val = 0.0

        # Cost parse (defaults to $1.00 per trade)
        raw_cost = get_val(cost_col, "1.0")
        raw_cost = raw_cost.replace("$", "").replace(",", "").replace(" ", "")
        try:
            cost_val = float(raw_cost) if raw_cost else 1.0
        except ValueError:
            cost_val = 1.0

        # Qty
        raw_qty = get_val(qty_col, "1")
        try:
            qty_val = float(raw_qty.replace(",", ""))
        except ValueError:
            qty_val = 1.0

        # Entry & Exit prices
        try:
            entry_price = float(get_val(entry_col, "0").replace("$", "").replace(",", ""))
        except ValueError:
            entry_price = 0.0

        try:
            exit_price = float(get_val(exit_col, "0").replace("$", "").replace(",", ""))
        except ValueError:
            exit_price = 0.0

        # Conditions boolean parsing
        def parse_bool(val: str, default: bool = False) -> bool:
            v = val.lower()
            if v in ("1", "true", "yes", "y", "t", "b", "right", "pass"):
                return True
            if v in ("0", "false", "no", "n", "f", "wrong", "fail"):
                return False
            return default

        is_b = parse_bool(get_val(b_trade_col), False)
        is_cross = parse_bool(get_val(cross_col), False)
        is_early = parse_bool(get_val(early_col), False)
        dir_right = parse_bool(get_val(dir_col), True if pnl_val >= 0 else False)

        notes = get_val(notes_col, "")

        trade_item = {
            "id": f"tr_{uuid.uuid4().hex[:10]}",
            "date": date_str,
            "time": time_str,
            "symbol": raw_sym,
            "side": raw_side,
            "qty": qty_val,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl_val,
            "trade_cost": cost_val,
            "is_b_trade": is_b,
            "is_9_21_cross": is_cross,
            "early_exit": is_early,
            "direction_right": dir_right,
            "notes": notes,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }

        existing_trades.append(trade_item)
        imported += 1

    existing_trades.sort(
        key=lambda x: (x.get("date", ""), x.get("time", "")),
        reverse=True,
    )
    save_all_trades(existing_trades)
    return imported, skipped, messages
