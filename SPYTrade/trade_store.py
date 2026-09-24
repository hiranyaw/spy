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
    trade["is_jimmy_recommended"] = bool(trade.get("is_jimmy_recommended", False))
    trade["is_b_trade"] = bool(trade.get("is_b_trade", False))
    trade["is_9_21_cross"] = bool(trade.get("is_9_21_cross", False))

    # Followed 9 EMA (up / down) - backwards compatible with fullback_uptrend / downtrend
    is_f9_up = bool(trade.get("is_followed_9_up", False) or trade.get("is_fullback_uptrend", False))
    is_f9_down = bool(trade.get("is_followed_9_down", False) or trade.get("is_fullback_downtrend", False))
    trade["is_followed_9_up"] = is_f9_up
    trade["is_followed_9_down"] = is_f9_down
    trade["is_fullback_uptrend"] = is_f9_up
    trade["is_fullback_downtrend"] = is_f9_down

    trade["is_ak_macd_bb"] = bool(trade.get("is_ak_macd_bb", False))
    trade["is_rsi_trendline"] = bool(trade.get("is_rsi_trendline", False))

    # Hiranya Signal Monitor: Buy or Sell
    hsm_dir = str(trade.get("hiranya_signal_dir", "") or "").upper()
    is_hsm_buy = bool(trade.get("is_hiranya_buy", False) or hsm_dir == "BUY")
    is_hsm_sell = bool(trade.get("is_hiranya_sell", False) or hsm_dir == "SELL")
    trade["is_hiranya_buy"] = is_hsm_buy
    trade["is_hiranya_sell"] = is_hsm_sell
    if is_hsm_buy:
        trade["hiranya_signal_dir"] = "BUY"
    elif is_hsm_sell:
        trade["hiranya_signal_dir"] = "SELL"
    else:
        trade["hiranya_signal_dir"] = ""
    trade["is_hiranya_signal"] = bool(trade.get("is_hiranya_signal", False) or is_hsm_buy or is_hsm_sell)

    # ADD value (NYSE Advance-Decline Breadth reading, e.g. +1250, -850)
    raw_add = trade.get("add_value")
    if raw_add is not None and str(raw_add).strip() != "":
        try:
            trade["add_value"] = float(str(raw_add).replace("+", "").replace(",", "").strip())
        except (ValueError, TypeError):
            trade["add_value"] = None
    else:
        trade["add_value"] = None

    trade["is_vwap_aligned"] = bool(trade.get("is_vwap_aligned", False))
    trade["is_qqq_confluence"] = bool(trade.get("is_qqq_confluence", False))
    trade["is_add_confluence"] = bool(trade.get("is_add_confluence", False) or trade["add_value"] is not None)
    trade["is_other"] = bool(trade.get("is_other", False))
    trade["other_setup"] = str(trade.get("other_setup", "") or "").strip()
    trade["early_exit"] = bool(trade.get("early_exit", False))
    trade["direction_right"] = bool(trade.get("direction_right", True))

    # Ensure numeric fields
    trade["qty"] = float(trade.get("qty", 1.0))
    trade["pnl"] = float(trade.get("pnl", 0.0))
    trade["trade_cost"] = float(trade.get("trade_cost", trade["qty"] * 1.0))
    trade["entry_price"] = float(trade.get("entry_price", 0.0))
    trade["exit_price"] = float(trade.get("exit_price", 0.0))

    # Ensure exit_reason
    exit_r = str(trade.get("exit_reason", "")).upper()
    if exit_r not in ("TARGET", "STOP_LOSS", "EARLY_EXIT", "BREAKEVEN", "VWAP_TOUCH"):
        exit_r = "TARGET" if trade["pnl"] > 0 else ("STOP_LOSS" if trade["pnl"] < 0 else "BREAKEVEN")
    trade["exit_reason"] = exit_r
    trade["is_vwap_touch_exit"] = (exit_r == "VWAP_TOUCH") or bool(trade.get("is_vwap_touch_exit", False))

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

    # Net PnL per trade = gross pnl - trade_cost ($1.00 * qty default)
    def _trade_cost(t: dict[str, Any]) -> float:
        if "trade_cost" in t and t["trade_cost"] is not None:
            return float(t["trade_cost"])
        return float(t.get("qty", 1.0)) * 1.0

    net_pnls = [float(t.get("pnl", 0.0)) - _trade_cost(t) for t in subset]
    gross_pnls = [float(t.get("pnl", 0.0)) for t in subset]
    costs = [_trade_cost(t) for t in subset]

    wins = sum(1 for npnl in net_pnls if npnl > 0)
    losses = sum(1 for npnl in net_pnls if npnl < 0)
    even = sum(1 for npnl in net_pnls if npnl == 0)
    decided = wins + losses
    win_rate = (wins / decided * 100.0) if decided > 0 else 0.0
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

    b_and_cross = [t for t in trades if t.get("is_b_trade", False) and t.get("is_9_21_cross", False)]

    jimmy_rec = [t for t in trades if t.get("is_jimmy_recommended", False)]
    followed_9_up = [t for t in trades if t.get("is_followed_9_up", False) or t.get("is_fullback_uptrend", False)]
    followed_9_down = [t for t in trades if t.get("is_followed_9_down", False) or t.get("is_fullback_downtrend", False)]
    other_setups = [t for t in trades if t.get("is_other", False)]

    # Checklist indicator confluence subsets
    ak_macd_bb = [t for t in trades if t.get("is_ak_macd_bb", False)]
    rsi_trendline = [t for t in trades if t.get("is_rsi_trendline", False)]
    hiranya_signal = [t for t in trades if t.get("is_hiranya_signal", False)]
    hiranya_buy = [t for t in trades if t.get("is_hiranya_buy", False) or str(t.get("hiranya_signal_dir", "")).upper() == "BUY"]
    hiranya_sell = [t for t in trades if t.get("is_hiranya_sell", False) or str(t.get("hiranya_signal_dir", "")).upper() == "SELL"]
    vwap_aligned = [t for t in trades if t.get("is_vwap_aligned", False)]
    qqq_confluence = [t for t in trades if t.get("is_qqq_confluence", False)]
    add_confluence = [t for t in trades if t.get("is_add_confluence", False) or t.get("add_value") is not None]
    add_positive = [t for t in trades if t.get("add_value") is not None and float(t["add_value"]) > 0]
    add_negative = [t for t in trades if t.get("add_value") is not None and float(t["add_value"]) < 0]

    # High Confluence: trades with 4 or more checklist indicator rules confirmed
    def _confluence_score(t: dict[str, Any]) -> int:
        keys = (
            "is_ak_macd_bb", "is_rsi_trendline", "is_hiranya_signal", "is_vwap_aligned",
            "is_qqq_confluence", "is_add_confluence"
        )
        return sum(1 for k in keys if t.get(k, False))

    high_confluence = [t for t in trades if _confluence_score(t) >= 4]

    early_exit = [t for t in trades if t.get("early_exit", False)]
    normal_exit = [t for t in trades if not t.get("early_exit", False)]
    vwap_touch_exit = [t for t in trades if str(t.get("exit_reason", "")).upper() == "VWAP_TOUCH" or t.get("is_vwap_touch_exit", False)]

    dir_right = [t for t in trades if t.get("direction_right", True)]
    dir_wrong = [t for t in trades if not t.get("direction_right", True)]

    return {
        "all": all_stats,
        "jimmy_recommended": _calc_stats_for_subset(jimmy_rec),
        "b_trade": _calc_stats_for_subset(b_trades),
        "non_b_trade": _calc_stats_for_subset(non_b_trades),
        "cross_9_21": _calc_stats_for_subset(cross_9_21),
        "non_cross_9_21": _calc_stats_for_subset(non_cross_9_21),
        "b_and_cross": _calc_stats_for_subset(b_and_cross),
        "followed_9_up": _calc_stats_for_subset(followed_9_up),
        "followed_9_down": _calc_stats_for_subset(followed_9_down),
        "fullback_uptrend": _calc_stats_for_subset(followed_9_up),
        "fullback_downtrend": _calc_stats_for_subset(followed_9_down),
        "other": _calc_stats_for_subset(other_setups),
        "ak_macd_bb": _calc_stats_for_subset(ak_macd_bb),
        "rsi_trendline": _calc_stats_for_subset(rsi_trendline),
        "hiranya_signal": _calc_stats_for_subset(hiranya_signal),
        "hiranya_buy": _calc_stats_for_subset(hiranya_buy),
        "hiranya_sell": _calc_stats_for_subset(hiranya_sell),
        "vwap_aligned": _calc_stats_for_subset(vwap_aligned),
        "qqq_confluence": _calc_stats_for_subset(qqq_confluence),
        "add_confluence": _calc_stats_for_subset(add_confluence),
        "add_positive": _calc_stats_for_subset(add_positive),
        "add_negative": _calc_stats_for_subset(add_negative),
        "high_confluence": _calc_stats_for_subset(high_confluence),
        "early_exit": _calc_stats_for_subset(early_exit),
        "normal_exit": _calc_stats_for_subset(normal_exit),
        "vwap_touch_exit": _calc_stats_for_subset(vwap_touch_exit),
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
    jimmy_col = find_col(["jimmy", "jimmy recommended", "jimmy_recommended", "jimmy rec", "jimmy call"])
    b_trade_col = find_col(["b_trade", "b trade", "b-trade"])
    cross_col = find_col(["9_21", "9 21", "9/21", "cross"])
    fb_up_col = find_col(["full back 9 uptrend", "fullback uptrend", "pullback uptrend", "pull back uptrend", "fb up", "fb_up"])
    fb_down_col = find_col(["full back 9 downtrend", "fullback downtrend", "pullback downtrend", "pull back downtrend", "fb down", "fb_down"])
    follow_9_up_col = find_col(["followed 9 ema up", "followed 9 up", "follow 9 up", "followed 9 (up)", "followed_9_up"])
    follow_9_down_col = find_col(["followed 9 ema down", "followed 9 down", "follow 9 down", "followed 9 (down)", "followed_9_down"])
    ak_macd_col = find_col(["ak_macd_bb", "ak macd bb", "ak macd", "ak_macd", "macd_bb", "macd bb", "macd"])
    rsi_col = find_col(["rsi_trendline", "rsi trend line", "rsi trendline", "rsi cross", "rsi_cross", "rsi"])
    hiranya_col = find_col(["hiranya_signal", "hiranya signal monitor", "hiranya signal", "hiranya_signal_monitor", "hiranya", "signal monitor"])
    hsm_buy_col = find_col(["hiranya buy", "hsm buy", "hiranya_buy", "hsm_buy"])
    hsm_sell_col = find_col(["hiranya sell", "hsm sell", "hiranya_sell", "hsm_sell"])
    hsm_dir_col = find_col(["hiranya signal dir", "hiranya dir", "hsm dir", "hiranya action", "hiranya signal action", "hiranya buy/sell"])
    vwap_col = find_col(["vwap_aligned", "vwap aligned", "vwap cross", "vwap_cross", "vwap"])
    qqq_col = find_col(["qqq_confluence", "qqq confluence", "qqq direction", "qqq_direction", "qqq"])
    add_col = find_col(["add_confluence", "add confluence", "add direction", "add_direction", "nyse add", "add breadth", "add"])
    add_val_col = find_col(["add_value", "add value", "nyse add value", "add reading", "add val", "$add value", "$add", "add level"])
    other_col = find_col(["other setup", "other", "is_other"])
    other_text_col = find_col(["other setup name", "other specify", "other text", "other_setup"])
    early_col = find_col(["early", "early exit", "early_exit"])
    exit_reason_col = find_col(["exit reason", "how trade ended", "exit_reason", "outcome", "exit trigger"])
    vwap_touch_col = find_col(["vwap touch", "vwap_touch", "exit vwap touch", "exit_vwap_touch"])
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

        # Qty
        raw_qty = get_val(qty_col, "1")
        try:
            qty_val = float(raw_qty.replace(",", ""))
        except ValueError:
            qty_val = 1.0

        # Cost parse (defaults to $1.00 * qty)
        raw_cost = get_val(cost_col, "")
        raw_cost = raw_cost.replace("$", "").replace(",", "").replace(" ", "")
        try:
            cost_val = float(raw_cost) if raw_cost else (qty_val * 1.0)
        except ValueError:
            cost_val = qty_val * 1.0

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

        is_jimmy = parse_bool(get_val(jimmy_col), False)
        is_b = parse_bool(get_val(b_trade_col), False)
        is_cross = parse_bool(get_val(cross_col), False)
        is_fb_up = parse_bool(get_val(follow_9_up_col if follow_9_up_col >= 0 else fb_up_col), False)
        is_fb_down = parse_bool(get_val(follow_9_down_col if follow_9_down_col >= 0 else fb_down_col), False)
        is_ak_macd = parse_bool(get_val(ak_macd_col), False)
        is_rsi = parse_bool(get_val(rsi_col), False)

        # Hiranya Buy / Sell
        h_dir_val = get_val(hsm_dir_col).upper()
        is_h_buy = parse_bool(get_val(hsm_buy_col), False) or ("BUY" in h_dir_val)
        is_h_sell = parse_bool(get_val(hsm_sell_col), False) or ("SELL" in h_dir_val)
        is_hiranya = parse_bool(get_val(hiranya_col), False) or is_h_buy or is_h_sell

        is_vwap = parse_bool(get_val(vwap_col), False)
        is_qqq = parse_bool(get_val(qqq_col), False)
        is_add = parse_bool(get_val(add_col), False)
        raw_add_val = get_val(add_val_col, "")
        add_value_parsed = None
        if raw_add_val:
            try:
                add_value_parsed = float(raw_add_val.replace("+", "").replace(",", "").strip())
                is_add = True
            except ValueError:
                add_value_parsed = None

        is_other = parse_bool(get_val(other_col), False)
        other_setup = get_val(other_text_col, "")
        if other_setup and not is_other:
            is_other = True
        is_early = parse_bool(get_val(early_col), False)
        dir_right = parse_bool(get_val(dir_col), True if pnl_val >= 0 else False)

        # Exit Reason / VWAP Touch
        raw_exit_r = get_val(exit_reason_col).upper()
        is_vt = parse_bool(get_val(vwap_touch_col), False)
        if "VWAP" in raw_exit_r or is_vt:
            exit_reason_val = "VWAP_TOUCH"
        elif "STOP" in raw_exit_r:
            exit_reason_val = "STOP_LOSS"
        elif "EARLY" in raw_exit_r or is_early:
            exit_reason_val = "EARLY_EXIT"
        elif "BE" in raw_exit_r or "BREAKEVEN" in raw_exit_r:
            exit_reason_val = "BREAKEVEN"
        elif "TARGET" in raw_exit_r:
            exit_reason_val = "TARGET"
        else:
            exit_reason_val = "TARGET" if pnl_val > 0 else ("STOP_LOSS" if pnl_val < 0 else "BREAKEVEN")

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
            "is_jimmy_recommended": is_jimmy,
            "is_b_trade": is_b,
            "is_9_21_cross": is_cross,
            "is_followed_9_up": is_fb_up,
            "is_followed_9_down": is_fb_down,
            "is_fullback_uptrend": is_fb_up,
            "is_fullback_downtrend": is_fb_down,
            "is_ak_macd_bb": is_ak_macd,
            "is_rsi_trendline": is_rsi,
            "is_hiranya_signal": is_hiranya,
            "is_hiranya_buy": is_h_buy,
            "is_hiranya_sell": is_h_sell,
            "hiranya_signal_dir": "BUY" if is_h_buy else ("SELL" if is_h_sell else ""),
            "is_vwap_aligned": is_vwap,
            "is_qqq_confluence": is_qqq,
            "is_add_confluence": is_add,
            "add_value": add_value_parsed,
            "is_other": is_other,
            "other_setup": other_setup,
            "early_exit": is_early or (exit_reason_val == "EARLY_EXIT"),
            "exit_reason": exit_reason_val,
            "is_vwap_touch_exit": (exit_reason_val == "VWAP_TOUCH"),
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
