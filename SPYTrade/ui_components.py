from utils import utc_to_local, pct_change
import datetime

# Width of the ASCII ladder in characters
_LADDER_WIDTH = 17


def render_connection_badge(connected: bool, details: str = "") -> str:
    """Return HTML for the connection status badge in header."""
    if connected:
        col = "#00e676"
        bg  = "rgba(0, 230, 118, 0.15)"
        border = "#00e676"
        text = "🟢 TV: CONNECTED"
    else:
        col = "#f44336"
        bg  = "rgba(244, 67, 54, 0.15)"
        border = "#f44336"
        text = "🔴 TV: DISCONNECTED"

    extra = f"<span style='color:#90caf9;font-size:11px;margin-left:4px;font-weight:normal'>({details})</span>" if details else ""

    return (
        f"<span style='display:inline-block;background:{bg};border:1px solid {border};"
        f"border-radius:10px;padding:5px 12px;font-size:12px;font-weight:bold;color:{col}'>"
        f"{text}{extra}</span>"
    )


def render_big_countdown(seconds: int, is_fetching: bool = False) -> str:
    """Return HTML for the BIG countdown counter badge on top."""
    if is_fetching:
        return (
            "<span style='display:inline-block;background:rgba(33,150,243,0.2);border:1.5px solid #2196f3;"
            "border-radius:10px;padding:5px 14px;font-size:13px;font-weight:bold;color:#64b5f6;"
            "font-family:\"Segoe UI\",sans-serif;'>"
            "⌛ <b>UPDATING NOW...</b></span>"
        )

    # Color shifts based on urgency
    if seconds <= 5:
        col = "#00e676"
        bg  = "rgba(0,230,118,0.18)"
        border = "#00e676"
    elif seconds <= 15:
        col = "#ffeb3b"
        bg  = "rgba(255,235,59,0.15)"
        border = "#ffeb3b"
    else:
        col = "#90caf9"
        bg  = "rgba(144,202,249,0.12)"
        border = "#42a5f5"

    return (
        f"<span style='display:inline-block;background:{bg};border:1.5px solid {border};"
        f"border-radius:10px;padding:5px 14px;font-size:13px;font-weight:800;color:{col};"
        f"font-family:\"Courier New\",monospace;letter-spacing:0.5px;'>"
        f"⏳ NEXT UPDATE: <span style='font-size:16px;'>{seconds:02d}s</span></span>"
    )


def render_3_direction_confluence(rec: dict, bar: dict = None) -> str:
    """Render a BIG, PROMINENT 3-Factor Direction Confluence banner on top:

    1. SPY 1-Min Direction
    2. QQQ Tech Direction
    3. NYSE $ADD Market Breadth Direction
    """
    spy_p = rec.get("spy_price") or (bar.get("close") if bar else 0.0)
    qqq_p = rec.get("qqq_price") or 0.0
    add_v = rec.get("add_value")
    add_d = rec.get("add_dir")
    macd_d = rec.get("macd_dir")

    # 1. SPY Direction
    if bar and bar.get("open", 0) > 0 and bar.get("close", 0) > 0:
        spy_bull = bar["close"] >= bar["open"]
        spy_dir_str = "BULLISH ⬆" if spy_bull else "BEARISH ⬇"
        spy_col = "#00e676" if spy_bull else "#f44336"
    elif "BUY" in rec.get("signal", ""):
        spy_bull = True
        spy_dir_str = "BULLISH ⬆"
        spy_col = "#00e676"
    elif "SELL" in rec.get("signal", ""):
        spy_bull = False
        spy_dir_str = "BEARISH ⬇"
        spy_col = "#f44336"
    else:
        spy_bull = None
        spy_dir_str = "NEUTRAL ⚖️"
        spy_col = "#9e9e9e"

    # 2. QQQ Direction (Tech benchmark correlation)
    qqq_dir = rec.get("qqq_dir")
    if qqq_dir == "UP":
        qqq_bull = True
        qqq_dir_str = "BULLISH ⬆"
        qqq_col = "#00e676"
    elif qqq_dir == "DN":
        qqq_bull = False
        qqq_dir_str = "BEARISH ⬇"
        qqq_col = "#f44336"
    else:
        # Fallback to general market bias or MACD
        if macd_d == "UP":
            qqq_bull = True
            qqq_dir_str = "BULLISH ⬆"
            qqq_col = "#00e676"
        elif macd_d == "DN":
            qqq_bull = False
            qqq_dir_str = "BEARISH ⬇"
            qqq_col = "#f44336"
        else:
            qqq_bull = spy_bull
            qqq_dir_str = spy_dir_str
            qqq_col = spy_col

    # 3. NYSE $ADD Direction (Institutional Breadth)
    if isinstance(add_v, (int, float)):
        add_bull = add_v > 0
        add_dir_str = f"BULLISH (+{int(add_v)}) ⬆" if add_bull else f"BEARISH ({int(add_v)}) ⬇"
        add_col = "#00e676" if add_bull else "#f44336"
    elif add_d in ("UP", "DN"):
        add_bull = add_d == "UP"
        add_dir_str = "BULLISH ⬆" if add_bull else "BEARISH ⬇"
        add_col = "#00e676" if add_bull else "#f44336"
    else:
        add_bull = None
        add_dir_str = "NEUTRAL ⚖️"
        add_col = "#9e9e9e"

    # Confluence Score
    bull_count = sum(1 for b in (spy_bull, qqq_bull, add_bull) if b is True)
    bear_count = sum(1 for b in (spy_bull, qqq_bull, add_bull) if b is False)

    if bull_count == 3:
        conf_title = "🔥 3/3 FULL BULLISH CONFLUENCE (HIGH PROBABILITY CALLS)"
        conf_border = "#00e676"
        conf_bg = "rgba(0, 230, 118, 0.14)"
        conf_badge = "3/3 BULL"
        conf_bcol = "#00e676"
    elif bear_count == 3:
        conf_title = "💥 3/3 FULL BEARISH CONFLUENCE (HIGH PROBABILITY PUTS)"
        conf_border = "#f44336"
        conf_bg = "rgba(244, 67, 54, 0.14)"
        conf_badge = "3/3 BEAR"
        conf_bcol = "#f44336"
    elif bull_count == 2:
        conf_title = "⚡ 2/3 MODERATE BULLISH CONFLUENCE (SPY + CORRELATION ALIGNED)"
        conf_border = "#ffeb3b"
        conf_bg = "rgba(255, 235, 59, 0.1)"
        conf_badge = "2/3 BULL"
        conf_bcol = "#ffeb3b"
    elif bear_count == 2:
        conf_title = "⚡ 2/3 MODERATE BEARISH CONFLUENCE (SPY + CORRELATION ALIGNED)"
        conf_border = "#ff9800"
        conf_bg = "rgba(255, 152, 0, 0.1)"
        conf_badge = "2/3 BEAR"
        conf_bcol = "#ff9800"
    else:
        conf_title = "⚖️ 1/3 MIXED CONFLUENCE — WAIT FOR DIRECTIONAL SYNC"
        conf_border = "#78909c"
        conf_bg = "rgba(120, 144, 156, 0.1)"
        conf_badge = "MIXED"
        conf_bcol = "#9e9e9e"

    def _dir_box(label: str, price_str: str, dir_text: str, col: str) -> str:
        return (
            f"<div style='flex:1;min-width:180px;background:#0d1826;border:1.5px solid {col};"
            f"border-radius:8px;padding:8px 12px;margin:2px;'>"
            f"<div style='font-size:12px;color:#90caf9;font-weight:bold;'>{label}</div>"
            f"<div style='font-size:16px;font-weight:900;color:{col};font-family:\"Courier New\",monospace;margin:2px 0;'>"
            f"{dir_text}</div>"
            f"<div style='font-size:12px;color:#cfd8dc;font-family:\"Courier New\",monospace;'>{price_str}</div>"
            f"</div>"
        )

    spy_p_str = f"${spy_p:.2f}" if (isinstance(spy_p, (int, float)) and spy_p > 0) else "—"
    qqq_p_str = f"${qqq_p:.2f}" if (isinstance(qqq_p, (int, float)) and qqq_p > 0) else "—"
    add_val_str = f"Level: {int(add_v)}" if isinstance(add_v, (int, float)) else "Level: —"

    boxes = (
        _dir_box("1️⃣ SPY BENCHMARK", spy_p_str, spy_dir_str, spy_col) +
        _dir_box("2️⃣ QQQ TECH LEADER", qqq_p_str, qqq_dir_str, qqq_col) +
        _dir_box("3️⃣ NYSE $ADD BREADTH", add_val_str, add_dir_str, add_col)
    )

    return (
        f"<div style='background:{conf_bg};border:2px solid {conf_border};border-radius:10px;"
        f"padding:10px 14px;margin:4px 0 8px 0;box-shadow:0 3px 12px rgba(0,0,0,0.3);'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
        f"<span style='font-size:14px;font-weight:900;color:{conf_bcol};letter-spacing:0.5px;'>"
        f"{conf_title}</span>"
        f"<span style='background:{conf_bcol};color:#000000;font-size:12px;font-weight:900;"
        f"padding:3px 10px;border-radius:6px;'>{conf_badge}</span>"
        f"</div>"
        f"<div style='display:flex;flex-wrap:wrap;gap:6px;'>"
        f"{boxes}"
        f"</div>"
        f"</div>"
    )


def render_top_hero_recommendation(rec: dict) -> str:
    """Render a BIG, COLORFUL headline recommendation banner with ENLARGED trade levels."""
    signal     = rec.get("signal", "HOLD")
    confidence = rec.get("confidence", 0)
    emoji      = rec.get("emoji", "⚪")
    color      = rec.get("color", "#9e9e9e")
    entry      = rec.get("entry", 0.0)
    target     = rec.get("target", 0.0)
    stop       = rec.get("stop", 0.0)

    if "STRONG BUY" in signal:
        action_tag = "🚀 BUY CALLS NOW"
        bg_gradient = "linear-gradient(135deg, rgba(0,230,118,0.22) 0%, rgba(13,27,42,0.98) 100%)"
        border_col  = "#00e676"
    elif "BUY" in signal:
        action_tag = "📈 CALLS SETUP"
        bg_gradient = "linear-gradient(135deg, rgba(255,235,59,0.18) 0%, rgba(13,27,42,0.98) 100%)"
        border_col  = "#ffeb3b"
    elif "STRONG SELL" in signal:
        action_tag = "🔻 BUY PUTS NOW"
        bg_gradient = "linear-gradient(135deg, rgba(244,67,54,0.22) 0%, rgba(13,27,42,0.98) 100%)"
        border_col  = "#f44336"
    elif "SELL" in signal:
        action_tag = "📉 PUTS SETUP"
        bg_gradient = "linear-gradient(135deg, rgba(255,152,0,0.18) 0%, rgba(13,27,42,0.98) 100%)"
        border_col  = "#ff9800"
    else:
        action_tag = "⚖️ WAIT / STAY FLAT"
        bg_gradient = "linear-gradient(135deg, rgba(158,158,158,0.14) 0%, rgba(13,27,42,0.98) 100%)"
        border_col  = "#9e9e9e"

    filled  = int(confidence / 10)
    empty   = 10 - filled
    conf_bar = (
        f"<span style='color:{color}'>{'█' * filled}</span>"
        f"<span style='color:#37474f'>{'█' * empty}</span>"
        f"  <b style='font-size:17px'>{confidence}%</b>"
    )

    # Risk / Reward calculations
    if entry > 0 and target > 0 and stop > 0:
        reward = abs(target - entry)
        risk   = abs(entry - stop)
        rr_ratio = (reward / risk) if risk > 0 else 1.5
        reward_pct = (reward / entry) * 100
        risk_pct   = (risk / entry) * 100
        rr_str = f"R:R {rr_ratio:.1f} : 1"
    else:
        reward_pct = 0.15
        risk_pct   = 0.08
        rr_str = "R:R 2.0 : 1"

    return (
        f"<div style='"
        f"border: 2.5px solid {border_col};"
        f"border-radius: 12px;"
        f"padding: 16px 20px;"
        f"margin: 4px 0 8px 0;"
        f"background: {bg_gradient};"
        f"box-shadow: 0 6px 18px rgba(0,0,0,0.5);"
        f"'>"

        # ── Line 1: Big Colorful Recommendation Header ──
        f"<div style='display:flex;align-items:center;justify-content:space-between;'>"
        f"<span style='font-size: 30px; font-weight: 900; color: {color}; letter-spacing: 1.5px;'>"
        f"{emoji} {signal}</span>"
        f"<span style='background: {border_col}; color: #000000; font-size: 16px; font-weight: 900; "
        f"padding: 6px 16px; border-radius: 8px; text-transform: uppercase; letter-spacing: 0.5px;'>"
        f"{action_tag}</span>"
        f"</div>"

        # ── Line 2: Confidence & Reason ──
        f"<div style='margin: 10px 0; font-size: 14px; color: #cfd8dc; font-family: \"Courier New\", monospace;'>"
        f"CONFIDENCE: {conf_bar} &nbsp;|&nbsp; <i style='color:#e2e8f0;font-size:13px;'>{rec.get('reason', '')}</i>"
        f"</div>"

        # ── Line 3: BIG ENLARGED Entry / Target / Stop Loss Cards ──
        f"<div style='display:flex;flex-wrap:wrap;gap:12px;margin-top:12px;font-family:\"Courier New\",monospace;'>"

        # Entry Card
        f"<div style='flex:1;min-width:160px;background:#0d2238;border:2px solid #388bfd;border-radius:8px;padding:10px 14px;'>"
        f"<div style='font-size:12px;font-weight:bold;color:#90caf9;text-transform:uppercase;'>🎯 ENTRY PRICE</div>"
        f"<div style='font-size:24px;font-weight:900;color:#ffffff;margin-top:2px;'>${entry:.2f}</div>"
        f"<div style='font-size:11px;color:#90caf9;'>SPY Execution Level</div>"
        f"</div>"

        # Target Card
        f"<div style='flex:1;min-width:160px;background:#062b18;border:2px solid #00e676;border-radius:8px;padding:10px 14px;'>"
        f"<div style='font-size:12px;font-weight:bold;color:#00e676;text-transform:uppercase;'>💰 PROFIT TARGET</div>"
        f"<div style='font-size:24px;font-weight:900;color:#00e676;margin-top:2px;'>${target:.2f}</div>"
        f"<div style='font-size:11px;color:#69f0ae;'>+{reward_pct:.2f}% Expected Move</div>"
        f"</div>"

        # Stop Loss Card
        f"<div style='flex:1;min-width:160px;background:#310b11;border:2px solid #ff5252;border-radius:8px;padding:10px 14px;'>"
        f"<div style='font-size:12px;font-weight:bold;color:#ff5252;text-transform:uppercase;'>🛑 STOP LOSS</div>"
        f"<div style='font-size:24px;font-weight:900;color:#ff5252;margin-top:2px;'>${stop:.2f}</div>"
        f"<div style='font-size:11px;color:#ff8a80;'>-{risk_pct:.2f}% Max Risk ({rr_str})</div>"
        f"</div>"

        f"</div>"

        f"</div>"
    )


def render_conditions_and_last_rec(rec: dict, last_actionable_rec: dict = None) -> str:
    """Render the enlarged 'Waiting for Condition' and 'Last Confirmed Recommendation' block."""
    conditions = rec.get("conditions", [])
    waiting_for = rec.get("waiting_for", [])
    signal = rec.get("signal", "HOLD")

    # Waiting for list HTML
    if "STRONG" in signal:
        wait_title = "⚡ ALL PRIMARY CONDITIONS ALIGNED"
        wait_title_col = "#00e676"
    elif "BUY" in signal or "SELL" in signal:
        wait_title = "⏳ SETUP DEVELOPING — CONFIRMING REMAINING CONDITIONS"
        wait_title_col = "#ffeb3b"
    else:
        wait_title = "⏳ WAITING FOR ENTRY CONDITIONS"
        wait_title_col = "#ff9800"

    wait_items_html = "".join([f"<li style='margin-bottom:3px;font-size:13px;color:#f1f5f9;'><b>•</b> {w}</li>" for w in waiting_for]) if waiting_for else "<li>Awaiting market momentum</li>"

    # Big condition badges table
    cond_cells = ""
    for c in conditions:
        met = c.get("met", False)
        icon = "✅" if met else "⏳"
        bg   = "rgba(0,230,118,0.12)" if met else "rgba(255,152,0,0.1)"
        col  = "#00e676" if met else "#ffb74d"
        bcol = "#00e676" if met else "#ff9800"

        cond_cells += (
            f"<div style='flex:1;min-width:160px;background:{bg};border:1.5px solid {bcol};border-radius:8px;"
            f"padding:8px 10px;margin:2px;'>"
            f"<div style='font-size:12px;color:#cbd5e1;font-weight:bold;'>{icon} {c['name']}</div>"
            f"<div style='font-size:14px;font-weight:bold;color:{col};font-family:\"Courier New\",monospace;margin-top:3px;'>{c['detail']}</div>"
            f"</div>"
        )

    # Last actionable recommendation info
    if last_actionable_rec and last_actionable_rec.get("signal") not in ("HOLD", None):
        last_sig  = last_actionable_rec.get("signal", "—")
        last_col  = last_actionable_rec.get("color", "#90caf9")
        last_ent  = last_actionable_rec.get("entry", 0.0)
        last_time = last_actionable_rec.get("time_str", "Earlier")
        last_rec_html = (
            f"<span style='color:{last_col};font-size:14px;font-weight:900;'>{last_sig}</span> @ "
            f"<span style='color:#ffffff;font-size:14px;font-weight:900;'>${last_ent:.2f}</span> "
            f"<span style='color:#94a3b8;font-size:12px;'>[🕒 {last_time}]</span>"
        )
    else:
        last_rec_html = "<span style='color:#78909c;'>No previous trade signal recorded in this session</span>"

    return (
        f"<div style='background:#0b1320;border:1.5px solid #1e3a5f;border-radius:10px;padding:12px 16px;margin:4px 0 8px 0;'>"

        # ── Waiting For Header & Checklist ──
        f"<div style='font-size:14px;font-weight:bold;color:{wait_title_col};margin-bottom:6px;'>"
        f"{wait_title}</div>"

        f"<div style='background:#060b13;border-left:3px solid {wait_title_col};padding:8px 12px;border-radius:4px;margin-bottom:10px;'>"
        f"<ul style='list-style:none;padding:0;margin:0;line-height:1.6;'>"
        f"{wait_items_html}</ul>"
        f"</div>"

        # ── Condition badges grid ──
        f"<div style='display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px;'>"
        f"{cond_cells}</div>"

        # ── Last Recommendation footer ──
        f"<div style='border-top:1px solid #1e293b;padding-top:8px;font-size:13px;color:#94a3b8;'>"
        f"<b>⏮️ LAST CONFIRMED TRADE RECOMMENDATION:</b> &nbsp; {last_rec_html}</div>"

        f"</div>"
    )


def render_indicator_panel(rec: dict, current_time_str: str = "") -> str:
    """Render a comprehensive grid of live TradingView indicators WITH EXACT TIMESTAMPS."""
    spy   = rec.get("spy_price")
    qqq   = rec.get("qqq_price")
    adx   = rec.get("adx")
    macd  = rec.get("macd_dir")
    tv_s  = rec.get("tv_signal", "N/A")
    tv_c  = rec.get("tv_conf", "N/A")
    add_d = rec.get("add_dir")
    add_v = rec.get("add_value")
    tlb   = rec.get("tl_break")
    stf   = rec.get("st_flip", "--")

    t_str = current_time_str or datetime.datetime.now().strftime("%H:%M:%S PT")

    spy_val = f"${spy:.2f}" if (isinstance(spy, (int, float)) and spy > 0) else "—"
    qqq_val = f"${qqq:.2f}" if (isinstance(qqq, (int, float)) and qqq > 0) else "—"

    if isinstance(add_v, (int, float)):
        add_str = f"{int(add_v)}"
        add_col = "#00e676" if add_v > 0 else "#f44336"
        add_sub = "Positive Breadth" if add_v > 0 else "Negative Breadth"
    else:
        add_str = "—"
        add_col = "#78909c"
        add_sub = add_d or "Breadth"

    if isinstance(adx, (int, float)):
        adx_str = f"{adx:.1f}"
        if adx >= 25:
            adx_col = "#00e676"
            adx_sub = "Strong Trend"
        elif adx < 18:
            adx_col = "#ff9800"
            adx_sub = "Ranging / Chop"
        else:
            adx_col = "#90caf9"
            adx_sub = "Moderate Trend"
    else:
        adx_str = "—"
        adx_col = "#78909c"
        adx_sub = "Trend Strength"

    # MACD
    if macd == "UP":
        macd_str = "BULLISH (UP)"
        macd_col = "#00e676"
    elif macd == "DN":
        macd_str = "BEARISH (DN)"
        macd_col = "#f44336"
    else:
        macd_str = "—"
        macd_col = "#78909c"

    # TV Signal
    if tv_s in ("BUY", "STRONG BUY"):
        tv_str = f"{tv_s} ({tv_c})"
        tv_col = "#00e676"
    elif tv_s in ("SELL", "STRONG SELL"):
        tv_str = f"{tv_s} ({tv_c})"
        tv_col = "#f44336"
    else:
        tv_str = f"{tv_s} ({tv_c})" if tv_s != "N/A" else "—"
        tv_col = "#78909c"

    # Trendline break
    if tlb == "UP":
        tl_str = "BREAKOUT UP ⬆"
        tl_col = "#00e676"
    elif tlb == "DN":
        tl_str = "BREAKDOWN DN ⬇"
        tl_col = "#f44336"
    else:
        tl_str = "—"
        tl_col = "#78909c"

    # Supertrend
    if "UP" in str(stf):
        st_str = str(stf)
        st_col = "#00e676"
    elif "DN" in str(stf):
        st_str = str(stf)
        st_col = "#f44336"
    else:
        st_str = str(stf) if stf != "--" else "—"
        st_col = "#78909c"

    def _card(title: str, val: str, sub: str, col: str, card_time: str) -> str:
        return (
            f"<div style='flex:1;min-width:145px;background:#111d2e;border:1px solid #1e3a5f;"
            f"border-top:3px solid {col};border-radius:6px;padding:8px 10px;margin:3px;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<span style='font-size:11px;color:#78909c;font-weight:bold;text-transform:uppercase;'>{title}</span>"
            f"<span style='font-size:10px;color:#546e7a;font-family:\"Courier New\",monospace;'>🕒 {card_time}</span>"
            f"</div>"
            f"<div style='font-size:16px;font-weight:bold;color:{col};font-family:\"Courier New\",monospace;margin:3px 0;'>{val}</div>"
            f"<div style='font-size:11px;color:#90a4ae;'>{sub}</div>"
            f"</div>"
        )

    cards_html = (
        f"<div style='display:flex;flex-wrap:wrap;gap:4px;margin:4px 0;'>"
        + _card("SPY (Live)", spy_val, "US Benchmark", "#90caf9", t_str)
        + _card("QQQ (Live)", qqq_val, "Tech Leader", "#90caf9", t_str)
        + _card("NYSE $ADD", add_str, add_sub, add_col, t_str)
        + _card("ADX Strength", adx_str, adx_sub, adx_col, t_str)
        + _card("AK MACD BB", macd_str, "Momentum", macd_col, t_str)
        + _card("TV Signal", tv_str, "Confluence", tv_col, t_str)
        + _card("TL Break", tl_str, "Structure", tl_col, t_str)
        + _card("Supertrend", st_str, "Trend State", st_col, t_str)
        + f"</div>"
    )

    return (
        "<div style='background:#0a121c;border-radius:8px;border:1px solid #162a45;padding:10px 12px;margin:6px 0;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>"
        f"<span style='font-size:13px;font-weight:bold;color:#90caf9;'>📡 Live TradingView Indicators & Market Stream</span>"
        f"<span style='font-size:11px;color:#78909c;font-family:\"Courier New\",monospace;'>Latest Stream Time: {t_str}</span>"
        f"</div>"
        + cards_html +
        "</div>"
    )


def render_status_block(bar: dict, actual_price: float = None) -> str:
    """Return HTML for the price action direction banner."""
    price_to_use = actual_price if (actual_price and actual_price > 100) else bar.get("close", 0)
    open_price = bar.get("open", price_to_use)
    
    pct = pct_change(open_price, price_to_use) if open_price > 0 else 0.0
    direction = "BULLISH 📈" if pct > 0 else ("BEARISH 📉" if pct < 0 else "FLAT ⚖️")
    color = "#00e676" if pct > 0 else ("#f44336" if pct < 0 else "#9e9e9e")
    sign = "+" if pct > 0 else ""

    price_str = f" @ ${price_to_use:.2f}" if price_to_use > 0 else ""

    text = (
        f"<span style='color:{color};font-weight:bold;font-size:15px'>"
        f"SPY 1‑MIN CANDLE: {direction}{price_str}"
        f"</span>"
        f"<span style='color:{color};font-size:13px'>"
        f"  ({sign}{pct:.2f}%)"
        f"</span>"
    )
    return f"<div style='margin-bottom:4px'>{text}</div>"


def render_ascii_ladder(bar: dict) -> str:
    """Create an ASCII ladder showing high, close, and low proportionally."""
    high  = bar.get("high", 0)
    low   = bar.get("low", 0)
    close = bar.get("close", 0)

    rows = 7
    range_ = high - low

    if range_ > 0:
        close_row = int(round((high - close) / range_ * (rows - 1)))
        close_row = max(0, min(rows - 1, close_row))
    else:
        close_row = rows // 2

    border = "─" * _LADDER_WIDTH
    inner_space = " " * (_LADDER_WIDTH - 2)

    lines = [f"{border}  High: ${high:.2f}"]
    for r in range(rows):
        if r == close_row:
            marker = inner_space[: len(inner_space) // 2] + "•" + inner_space[len(inner_space) // 2 + 1 :]
            lines.append(f"│{marker}│  ← ${close:.2f}")
        else:
            lines.append(f"│{inner_space}│")
    lines.append(f"{border}  Low:  ${low:.2f}")

    body = "\n".join(lines)
    return (
        f"<pre style='font-family:\"Courier New\",monospace;"
        f"background:#1a1a2e;color:#a0cfff;padding:8px;"
        f"border-radius:6px;line-height:1.4;margin:4px 0'>{body}</pre>"
    )


def render_bullet_points(bar: dict, rec: dict = None, time_str: str = "") -> str:
    """Return HTML bullet list with detailed bar values and timestamps."""
    ts_raw = bar.get("timestamp", "")
    try:
        ts_local = utc_to_local(ts_raw)
    except Exception:
        ts_local = ts_raw or time_str

    open_p  = bar.get("open", 0)
    close_p = bar.get("close", 0)
    pct = pct_change(open_p, close_p) if open_p > 0 else 0.0
    sign = "+" if pct > 0 else ""
    pct_color = "#00e676" if pct >= 0 else "#f44336"

    def _cell(label: str, value: str, ts: str = "") -> str:
        t_tag = f" <span style='color:#64748b;font-size:11px;'>[🕒 {ts}]</span>" if ts else ""
        return f"<li><b>{label}:</b> {value}{t_tag}</li>"

    rows = [
        _cell("SPY Close", f"${close_p:.2f}", ts_local),
        _cell("SPY Open", f"${open_p:.2f}", ts_local),
        _cell("SPY High", f"${bar.get('high', 0):.2f}", ts_local),
        _cell("SPY Low", f"${bar.get('low', 0):.2f}", ts_local),
        _cell("1-Min % Change", f"<span style='color:{pct_color}'>{sign}{pct:.2f}%</span>"),
    ]

    if rec and rec.get("qqq_price"):
        rows.append(_cell("QQQ Price", f"${rec['qqq_price']:.2f}", time_str or ts_local))
    if rec and rec.get("add_value") is not None:
        rows.append(_cell("NYSE $ADD Breadth", f"{int(rec['add_value'])}", time_str or ts_local))

    return f"<ul style='line-height:1.8;margin-top:4px;color:#cfd8dc'>{''.join(rows)}</ul>"


def render_bar_history(bars: list) -> str:
    """Return an HTML table of recent bars."""
    if not bars:
        return (
            "<div style='color:#555;font-size:12px;font-style:italic;margin-top:6px'>"
            "Bar history will populate as live bars arrive…"
            "</div>"
        )

    display_bars = bars[-5:]

    header = (
        "<div style='font-size:13px;font-weight:bold;color:#90caf9;"
        "margin-top:8px;margin-bottom:4px'>📋 Recent Bar History</div>"
        "<table style='border-collapse:collapse;font-size:12px;"
        "font-family:\"Courier New\",monospace;width:100%'>"
        "<tr style='color:#546e7a;border-bottom:1px solid #333'>"
        "<th style='text-align:left;padding:2px 8px'>Time (PT)</th>"
        "<th style='text-align:right;padding:2px 8px'>Open</th>"
        "<th style='text-align:right;padding:2px 8px'>High</th>"
        "<th style='text-align:right;padding:2px 8px'>Low</th>"
        "<th style='text-align:right;padding:2px 8px'>Close</th>"
        "<th style='text-align:right;padding:2px 8px'>Chg%</th>"
        "<th style='text-align:center;padding:2px 8px'>Dir</th>"
        "</tr>"
    )

    rows_html = ""
    for bar in display_bars:
        pct   = pct_change(bar.get("open", 0), bar.get("close", 0))
        sign  = "+" if pct >= 0 else ""
        color = "#00e676" if pct >= 0 else "#f44336"
        arrow = "▲" if pct >= 0 else "▼"

        try:
            ts = utc_to_local(bar.get("timestamp", ""))[-8:]
        except Exception:
            ts = str(bar.get("timestamp", ""))[-8:]

        rows_html += (
            f"<tr style='border-bottom:1px solid #1e1e1e'>"
            f"<td style='padding:3px 8px;color:#78909c'>{ts}</td>"
            f"<td style='text-align:right;padding:3px 8px;color:#b0bec5'>${bar.get('open',0):.2f}</td>"
            f"<td style='text-align:right;padding:3px 8px;color:#b0bec5'>${bar.get('high',0):.2f}</td>"
            f"<td style='text-align:right;padding:3px 8px;color:#b0bec5'>${bar.get('low',0):.2f}</td>"
            f"<td style='text-align:right;padding:3px 8px;color:#e0e0e0;font-weight:bold'>"
            f"${bar.get('close',0):.2f}</td>"
            f"<td style='text-align:right;padding:3px 8px;color:{color}'>"
            f"{sign}{pct:.2f}%</td>"
            f"<td style='text-align:center;padding:3px 8px;color:{color}'>{arrow}</td>"
            f"</tr>"
        )

    footer = "</table>"
    return header + rows_html + footer
