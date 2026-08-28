"""signals.py — Trade signal engine for SPYTrade.

Analyzes the latest 1-minute SPY bar (plus recent history) and returns a
structured trade recommendation:  STRONG BUY, BUY, HOLD, SELL, STRONG SELL.

Also supports indicator-enhanced analysis via analyze_with_indicators()
which incorporates ADX, MACD direction, TV signal/confidence, ADD breadth,
and trendline break signals from the TradingView chart.

Usage::

    from signals import analyze_bar, analyze_with_indicators
    rec = analyze_bar(current_bar, history_bars)
    rec = analyze_with_indicators(current_bar, history_bars, indicators)
    print(rec["signal"], rec["confidence"], rec["reason"])
"""

from __future__ import annotations
import logging

log = logging.getLogger(__name__)

# ── Tunable thresholds ────────────────────────────────────────────────────────
_BODY_STRONG_RATIO   = 0.50   # body/range must exceed this for STRONG signal
_DOJI_RATIO          = 0.10   # body/range below this → HOLD (doji)
_CLOSE_ZONE_TOP      = 0.70   # close must be in top N% of range for bullish zone
_CLOSE_ZONE_BOTTOM   = 0.30   # close must be in bottom N% of range for bearish zone
_ATR_MULT_TARGET     = 0.50   # target = entry + ATR * mult
_ATR_MULT_STOP       = 0.25   # stop   = entry - ATR * mult
_MIN_ATR_FALLBACK    = 0.10   # minimum ATR when range is tiny (avoid div/0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _body_ratio(bar: dict) -> float:
    """Candle body size as a fraction of the high-low range."""
    rng = bar["high"] - bar["low"]
    if rng <= 0:
        return 0.0
    return abs(bar["close"] - bar["open"]) / rng


def _close_position(bar: dict) -> float:
    """Where close sits within high-low range.  0 = at Low, 1 = at High."""
    rng = bar["high"] - bar["low"]
    if rng <= 0:
        return 0.5
    return (bar["close"] - bar["low"]) / rng


def _is_bullish(bar: dict) -> bool:
    return bar["close"] > bar["open"]


def _is_bearish(bar: dict) -> bool:
    return bar["close"] < bar["open"]


def _estimate_atr(bar: dict, history: list[dict]) -> float:
    """Simple ATR estimate: average of the last N bar ranges (including current)."""
    bars = (history + [bar])[-5:]          # up to 5 bars
    ranges = [b["high"] - b["low"] for b in bars if b["high"] > b["low"]]
    if not ranges:
        return _MIN_ATR_FALLBACK
    return max(sum(ranges) / len(ranges), _MIN_ATR_FALLBACK)


def _trend_count(history: list[dict]) -> tuple[int, int]:
    """Return (consecutive_bullish, consecutive_bearish) from newest history bar
    going backwards.  E.g. if last 3 were bullish → (3, 0).
    """
    bull = 0
    bear = 0
    for b in reversed(history):
        if _is_bullish(b):
            if bear > 0:
                break
            bull += 1
        elif _is_bearish(b):
            if bull > 0:
                break
            bear += 1
        else:
            break
    return bull, bear


# ── Main public function ──────────────────────────────────────────────────────

def analyze_bar(bar: dict, history: list[dict]) -> dict:
    """Analyze ``bar`` in context of ``history`` and return a recommendation.

    Parameters
    ----------
    bar:
        Latest 1-min OHLCV bar dict with keys:
        ``open``, ``high``, ``low``, ``close``, ``volume``, ``timestamp``.
    history:
        List of previous bars (oldest first, newest last).
        May be empty when the app first starts.

    Returns
    -------
    dict with keys:
        signal     – "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL"
        confidence – int 0-100
        reason     – human-readable explanation string
        entry      – float, suggested entry price
        target     – float, suggested profit target
        stop       – float, suggested stop-loss
        emoji      – single emoji for the signal color
        color      – CSS hex color for the signal
    """
    body_r  = _body_ratio(bar)
    close_p = _close_position(bar)
    bullish = _is_bullish(bar)
    bearish = _is_bearish(bar)
    atr     = _estimate_atr(bar, history)
    bull_streak, bear_streak = _trend_count(history)

    entry = bar["close"]

    # ── Determine raw signal ────────────────────────────────────────────────
    reasons: list[str] = []

    if body_r < _DOJI_RATIO:
        signal    = "HOLD"
        confidence = 30
        reasons.append("Doji / indecisive candle")

    elif bullish:
        reasons.append(f"Bullish candle ({body_r*100:.0f}% body)")
        if close_p >= _CLOSE_ZONE_TOP and body_r >= _BODY_STRONG_RATIO:
            signal     = "STRONG BUY"
            confidence = int(min(95, body_r * 100 + 20))
            reasons.append("Close in upper zone (strength)")
        else:
            signal     = "BUY"
            confidence = int(min(80, body_r * 100 + 10))
            if close_p >= 0.5:
                reasons.append("Close above midpoint")
            else:
                reasons.append("Close in lower half (weak)")

    elif bearish:
        reasons.append(f"Bearish candle ({body_r*100:.0f}% body)")
        if close_p <= _CLOSE_ZONE_BOTTOM and body_r >= _BODY_STRONG_RATIO:
            signal     = "STRONG SELL"
            confidence = int(min(95, body_r * 100 + 20))
            reasons.append("Close in lower zone (weakness)")
        else:
            signal     = "SELL"
            confidence = int(min(80, body_r * 100 + 10))
            if close_p <= 0.5:
                reasons.append("Close below midpoint")
            else:
                reasons.append("Close in upper half (weak)")

    else:
        signal     = "HOLD"
        confidence = 30
        reasons.append("Flat bar")

    # ── Trend boost / downgrade ─────────────────────────────────────────────
    if signal == "BUY" and bull_streak >= 2:
        signal     = "STRONG BUY"
        confidence = min(95, confidence + 15)
        reasons.append(f"{bull_streak}-bar bullish trend")

    elif signal == "SELL" and bear_streak >= 2:
        signal     = "STRONG SELL"
        confidence = min(95, confidence + 15)
        reasons.append(f"{bear_streak}-bar bearish trend")

    elif signal == "STRONG BUY" and bear_streak >= 1:
        signal     = "BUY"                     # counter-trend bar: downgrade
        confidence = max(0, confidence - 10)
        reasons.append("Counter-trend — downgraded")

    elif signal == "STRONG SELL" and bull_streak >= 1:
        signal     = "SELL"
        confidence = max(0, confidence - 10)
        reasons.append("Counter-trend — downgraded")

    # ── Entry / Target / Stop ───────────────────────────────────────────────
    if signal in ("STRONG BUY", "BUY"):
        target = round(entry + atr * _ATR_MULT_TARGET, 2)
        stop   = round(entry - atr * _ATR_MULT_STOP,   2)
    elif signal in ("STRONG SELL", "SELL"):
        target = round(entry - atr * _ATR_MULT_TARGET, 2)
        stop   = round(entry + atr * _ATR_MULT_STOP,   2)
    else:
        target = round(entry + atr * _ATR_MULT_TARGET * 0.5, 2)
        stop   = round(entry - atr * _ATR_MULT_STOP   * 0.5, 2)

    # ── Emoji / color map ───────────────────────────────────────────────────
    _meta = {
        "STRONG BUY":  ("🟢", "#00e676"),
        "BUY":         ("🟡", "#ffeb3b"),
        "HOLD":        ("⚪", "#9e9e9e"),
        "SELL":        ("🟠", "#ff9800"),
        "STRONG SELL": ("🔴", "#f44336"),
    }
    emoji, color = _meta[signal]

    reason_str = " · ".join(reasons)

    log.info(
        "Signal: %-12s  conf=%3d%%  entry=%.2f  target=%.2f  stop=%.2f  | %s",
        signal, confidence, entry, target, stop, reason_str,
    )

    return {
        "signal":     signal,
        "confidence": confidence,
        "reason":     reason_str,
        "entry":      entry,
        "target":     target,
        "stop":       stop,
        "emoji":      emoji,
        "color":      color,
    }


def analyze_with_indicators(bar: dict, history: list, indicators: dict) -> dict:
    """Enhanced signal analysis using TradingView indicator values.

    Starts with ``analyze_bar`` result and boosts or downgrades confidence
    based on:

    - **ADX** (trend strength): ADX > 25 boosts strong signals; < 15 = choppy,
      downgrades to HOLD if bar signal is weak.
    - **MACD direction** (macd_dir UP/DN): agreement boosts +10%, conflict -10%.
    - **TV signal** (signal_tv BUY/SELL + conf_tv N/5): strong TV confluence
      (4/5 or 5/5) directly overrides bar signal when it disagrees.
    - **ADD breadth** (add_dir UP/DN): market breadth confirmation +5%.
    - **Trendline break** (tl_break UP/DN): structural break boost +8%.
    - **Supertrend flip** (st_flip): FLIPPED UP/DN = strong trend change signal.

    Parameters
    ----------
    bar:        Latest 1-min OHLCV bar dict.
    history:    Previous bars list.
    indicators: Dict from ``tv_scraper.fetch_indicators()``.

    Returns
    -------
    Same structure as ``analyze_bar`` plus extra keys:
        ``adx``, ``tv_signal``, ``tv_conf``, ``macd_dir``, ``add_dir``,
        ``tl_break``, ``st_flip``, ``spy_price``, ``qqq_price``
    """
    # Start with base candle signal
    rec = analyze_bar(bar, history)
    signal     = rec["signal"]
    confidence = rec["confidence"]
    reasons    = list(rec["reason"].split(" · ")) if rec["reason"] else []
    entry      = rec["entry"]

    bullish = _is_bullish(bar)
    bearish = _is_bearish(bar)
    body_r  = _body_ratio(bar)

    ind = indicators or {}

    # ── Use real SPY price if available and bar price looks wrong ──────────
    spy_price = ind.get("spy_price")
    if spy_price and isinstance(spy_price, (int, float)) and spy_price > 100:
        entry = spy_price   # override with real TV price


    # ── ADX — trend strength ────────────────────────────────────────────────
    adx = ind.get("adx_value")
    if adx is not None:
        if adx >= 25:
            if signal in ("STRONG BUY", "STRONG SELL"):
                confidence = min(95, confidence + 8)
                reasons.append(f"ADX={adx:.1f} (strong trend)")
            elif signal in ("BUY", "SELL"):
                confidence = min(90, confidence + 5)
                reasons.append(f"ADX={adx:.1f}")
        elif adx < 15:
            if signal in ("BUY", "SELL"):
                signal     = "HOLD"
                confidence = max(20, confidence - 20)
                reasons.append(f"ADX={adx:.1f} (choppy — downgraded)")
            else:
                reasons.append(f"ADX={adx:.1f} (choppy)")

    # ── MACD direction ──────────────────────────────────────────────────────
    macd_dir = ind.get("macd_dir")
    if macd_dir in ("UP", "DN"):
        macd_bullish = macd_dir == "UP"
        sig_bullish  = "BUY" in signal
        sig_bearish  = "SELL" in signal
        if sig_bullish and macd_bullish:
            confidence = min(95, confidence + 10)
            reasons.append("MACD agrees UP")
        elif sig_bearish and not macd_bullish:
            confidence = min(95, confidence + 10)
            reasons.append("MACD agrees DN")
        elif sig_bullish and not macd_bullish:
            confidence = max(10, confidence - 10)
            reasons.append("MACD conflict DN")
        elif sig_bearish and macd_bullish:
            confidence = max(10, confidence - 10)
            reasons.append("MACD conflict UP")

    # ── TV signal + confluence override ─────────────────────────────────────
    signal_tv = ind.get("signal_tv")
    conf_tv   = ind.get("conf_tv", "N/A")
    try:
        conf_num = int(str(conf_tv).split("/")[0]) if "/" in str(conf_tv) else 0
    except Exception:
        conf_num = 0

    if signal_tv in ("BUY", "SELL") and conf_num >= 4:
        tv_bullish = signal_tv == "BUY"
        sig_bullish = "BUY" in signal
        if tv_bullish and not sig_bullish:
            # Override weak/neutral bar with strong TV confluence
            signal     = "BUY" if conf_num == 4 else "STRONG BUY"
            confidence = min(95, confidence + conf_num * 5)
            reasons.append(f"TV {signal_tv} {conf_tv} (override)")
        elif not tv_bullish and sig_bullish:
            signal     = "SELL" if conf_num == 4 else "STRONG SELL"
            confidence = min(95, confidence + conf_num * 5)
            reasons.append(f"TV {signal_tv} {conf_tv} (override)")
        else:
            # Agree
            confidence = min(95, confidence + conf_num * 3)
            reasons.append(f"TV confirms {signal_tv} {conf_tv}")

    # ── ADD breadth direction ───────────────────────────────────────────────
    add_dir = ind.get("add_dir")
    if add_dir in ("UP", "DN"):
        add_bullish = add_dir == "UP"
        sig_bullish = "BUY" in signal
        if (sig_bullish and add_bullish) or (not sig_bullish and not add_bullish and "SELL" in signal):
            confidence = min(95, confidence + 5)
            reasons.append(f"ADD breadth {add_dir}")
        elif sig_bullish and not add_bullish:
            confidence = max(10, confidence - 5)
            reasons.append(f"ADD breadth {add_dir} (weak)")

    # ── Trendline break ─────────────────────────────────────────────────────
    tl_break = ind.get("tl_break")
    if tl_break in ("UP", "DN"):
        tl_bullish  = tl_break == "UP"
        sig_bullish = "BUY" in signal
        if (sig_bullish and tl_bullish) or (not sig_bullish and not tl_bullish):
            confidence = min(95, confidence + 8)
            reasons.append(f"TL break {tl_break}")
        else:
            confidence = max(10, confidence - 8)
            reasons.append(f"TL break {tl_break} (conflict)")

    # ── Supertrend flip ─────────────────────────────────────────────────────
    st_flip = ind.get("st_flip", "--")
    if st_flip in ("FLIPPED UP", "FLIPPED DN"):
        flip_bullish = st_flip == "FLIPPED UP"
        sig_bullish  = "BUY" in signal
        if flip_bullish and sig_bullish:
            signal     = "STRONG BUY"
            confidence = min(95, confidence + 12)
            reasons.append("Supertrend FLIPPED UP")
        elif not flip_bullish and not sig_bullish:
            signal     = "STRONG SELL"
            confidence = min(95, confidence + 12)
            reasons.append("Supertrend FLIPPED DN")
        else:
            reasons.append(f"ST flip {st_flip} (conflict)")

    # ── Recalculate entry/target/stop with real price ───────────────────────
    atr = _estimate_atr(bar, history)
    if signal in ("STRONG BUY", "BUY"):
        target = round(entry + atr * _ATR_MULT_TARGET, 2)
        stop   = round(entry - atr * _ATR_MULT_STOP,   2)
    elif signal in ("STRONG SELL", "SELL"):
        target = round(entry - atr * _ATR_MULT_TARGET, 2)
        stop   = round(entry + atr * _ATR_MULT_STOP,   2)
    else:
        target = round(entry + atr * _ATR_MULT_TARGET * 0.5, 2)
        stop   = round(entry - atr * _ATR_MULT_STOP   * 0.5, 2)

    # ── Condition Checklist & Waiting For ──────────────────────────────────
    conditions_list = []
    waiting_for_list = []

    # 1. Price Momentum
    if bullish:
        conditions_list.append({"name": "Price Momentum", "met": True, "detail": f"Bullish Bar (+{body_r*100:.0f}% body)"})
    elif bearish:
        conditions_list.append({"name": "Price Momentum", "met": "SELL" in signal, "detail": f"Bearish Bar ({body_r*100:.0f}% body)"})
    else:
        conditions_list.append({"name": "Price Momentum", "met": False, "detail": "Doji / Neutral Bar"})
        waiting_for_list.append("Directional breakout candle")

    # 2. ADX Trend Strength
    if adx is not None:
        if adx >= 20:
            conditions_list.append({"name": "ADX Trend Strength", "met": True, "detail": f"ADX {adx:.1f} (Trending)"})
        else:
            conditions_list.append({"name": "ADX Trend Strength", "met": False, "detail": f"ADX {adx:.1f} (Low / Chop)"})
            waiting_for_list.append(f"ADX strength > 20 (currently {adx:.1f})")
    else:
        conditions_list.append({"name": "ADX Trend Strength", "met": False, "detail": "Awaiting ADX"})

    # 3. MACD Alignment
    if macd_dir in ("UP", "DN"):
        macd_matches = (macd_dir == "UP" and "BUY" in signal) or (macd_dir == "DN" and "SELL" in signal)
        conditions_list.append({"name": "AK MACD Momentum", "met": macd_matches, "detail": f"MACD {macd_dir}"})
        if not macd_matches and signal != "HOLD":
            waiting_for_list.append(f"MACD momentum alignment (currently {macd_dir})")
    else:
        conditions_list.append({"name": "AK MACD Momentum", "met": False, "detail": "Neutral / Awaiting"})

    # 4. Market Breadth ($ADD)
    add_val = ind.get("add_value")
    if add_val is not None and isinstance(add_val, (int, float)):
        add_matches = (add_val > 0 and "BUY" in signal) or (add_val < 0 and "SELL" in signal)
        conditions_list.append({"name": "NYSE $ADD Breadth", "met": add_matches, "detail": f"$ADD {int(add_val)}"})
        if not add_matches and signal != "HOLD":
            waiting_for_list.append(f"$ADD breadth confirmation (currently {int(add_val)})")
    else:
        conditions_list.append({"name": "NYSE $ADD Breadth", "met": False, "detail": "Neutral / Awaiting"})

    # 5. Structure / Breaks
    if tl_break in ("UP", "DN") or st_flip in ("FLIPPED UP", "FLIPPED DN"):
        struct_detail = f"TL {tl_break}" if tl_break else f"ST {st_flip}"
        conditions_list.append({"name": "Structure / Flip", "met": True, "detail": struct_detail})
    else:
        conditions_list.append({"name": "Structure / Flip", "met": False, "detail": "No active break"})

    if not waiting_for_list and signal in ("STRONG BUY", "BUY", "STRONG SELL", "SELL"):
        waiting_for_list.append("All primary conditions aligned — ready for execution")
    elif not waiting_for_list:
        waiting_for_list.append("Waiting for clear trend confirmation")

    _meta = {
        "STRONG BUY":  ("🟢", "#00e676"),
        "BUY":         ("🟡", "#ffeb3b"),
        "HOLD":        ("⚪", "#9e9e9e"),
        "SELL":        ("🟠", "#ff9800"),
        "STRONG SELL": ("🔴", "#f44336"),
    }
    emoji, color = _meta.get(signal, ("⚪", "#9e9e9e"))
    reason_str   = " · ".join(r for r in reasons if r)

    return {
        "signal":          signal,
        "confidence":      confidence,
        "reason":          reason_str,
        "entry":           entry,
        "target":          target,
        "stop":            stop,
        "emoji":           emoji,
        "color":           color,
        "conditions":      conditions_list,
        "waiting_for":     waiting_for_list,

        # Indicator extras for UI display
        "adx":             adx,
        "tv_signal":       signal_tv,
        "tv_conf":         conf_tv,
        "macd_dir":        macd_dir,
        "add_dir":         add_dir,
        "tl_break":        tl_break,
        "st_flip":         st_flip,
        "spy_price":       ind.get("spy_price"),
        "qqq_price":       ind.get("qqq_price"),
        "add_value":       ind.get("add_value"),
    }
