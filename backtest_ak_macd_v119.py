# -*- coding: utf-8 -*-
"""
Backtest: AK MACD BB + QQQ+ADD 1MIN TREND [Hiranya] v1.19
5-Confluence System:
  1. MACD BB  - (hist>0 & rising) OR hist >= BB upper band
  2. QQQ 1m   - current close > prev close
  3. ADD 1m   - current close > prev close
  4. SPY 5m   - Supertrend direction (ATR=10, factor=3.0)
  5. SPY 1m   - Supertrend direction (ATR=10, factor=3.0)
BUY  = all 5 UP  |  SELL = all 5 DOWN
LA window: 6:30-8:15 AM PT  |  TP: +0.12%  SL: -0.09%
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

pacific = pytz.timezone("US/Pacific")

# ── Fetch helpers ──────────────────────────────────────────────
def fetch(symbol, interval="1m", days=30):
    ticker = yf.Ticker(symbol)
    end = datetime.now()
    chunks = []
    step = 7 if interval == "1m" else 14
    for i in range(0, days, step):
        ce = end - timedelta(days=i)
        cs = end - timedelta(days=i + step)
        try:
            c = ticker.history(start=cs.strftime("%Y-%m-%d"),
                               end=ce.strftime("%Y-%m-%d"), interval=interval)
            if not c.empty:
                chunks.append(c)
        except:
            pass
    if not chunks:
        return None
    df = pd.concat(chunks).sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.index = df.index.tz_convert(pacific)
    return df

print("Fetching data (SPY 1m, QQQ 1m, ADD 1m, SPY 5m)...")
spy1 = fetch("SPY", "1m", 30)
qqq1 = fetch("QQQ", "1m", 30)
spy5 = fetch("SPY", "5m", 60)

# Try ADD - multiple possible tickers
add1 = None
for add_ticker in ["^ADD", "NYADD", "ADD"]:
    try:
        add1 = fetch(add_ticker, "1m", 30)
        if add1 is not None and len(add1) > 100:
            print(f"ADD data loaded via {add_ticker}: {len(add1)} bars")
            break
        add1 = None
    except:
        pass

if add1 is None:
    print("ADD intraday not available via yfinance — using SPY breadth proxy (Close > Open = advancing)")

print(f"SPY 1m: {len(spy1)} bars | QQQ 1m: {len(qqq1)} bars | SPY 5m: {len(spy5)} bars")

# LA window filter
spy1 = spy1.between_time("06:30", "08:15")
qqq1 = qqq1.between_time("06:30", "08:15")
if add1 is not None:
    add1 = add1.between_time("06:30", "08:15")

print(f"After LA filter — SPY 1m: {len(spy1)} bars | Days: {spy1.index.normalize().nunique()}\n")


# ── Indicator functions ────────────────────────────────────────
def compute_macd_bb(close, fast=12, slow=26, sig=9, bb_len=20, bb_mult=2.0):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=sig, adjust=False).mean()
    hist = macd_line - signal_line
    bb_basis = hist.rolling(bb_len).mean()
    bb_std   = hist.rolling(bb_len).std()
    bb_upper = bb_basis + bb_mult * bb_std
    # Green dot: (hist>0 & hist>hist[1]) OR hist >= BB upper
    green = ((hist > 0) & (hist > hist.shift(1))) | (hist >= bb_upper)
    return green  # True=bullish, False=bearish


def compute_supertrend(df, atr_len=10, factor=3.0):
    """Returns direction Series: True=up (bullish), False=down (bearish)"""
    hl2 = (df["High"] + df["Low"]) / 2
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"]  - df["Close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/atr_len, adjust=False).mean()

    upper_band = hl2 + factor * atr
    lower_band = hl2 - factor * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction  = pd.Series(index=df.index, dtype=bool)

    for i in range(1, len(df)):
        # Upper band
        ub = upper_band.iloc[i]
        if upper_band.iloc[i-1] < supertrend.iloc[i-1] or df["Close"].iloc[i-1] > upper_band.iloc[i-1]:
            ub = min(ub, upper_band.iloc[i-1]) if not pd.isna(supertrend.iloc[i-1]) else ub

        # Lower band
        lb = lower_band.iloc[i]
        if lower_band.iloc[i-1] > supertrend.iloc[i-1] or df["Close"].iloc[i-1] < lower_band.iloc[i-1]:
            lb = max(lb, lower_band.iloc[i-1]) if not pd.isna(supertrend.iloc[i-1]) else lb

        close = df["Close"].iloc[i]
        prev_dir = direction.iloc[i-1] if i > 1 else True

        if prev_dir:   # was up
            if close < lb:
                direction.iloc[i] = False
                supertrend.iloc[i] = ub
            else:
                direction.iloc[i] = True
                supertrend.iloc[i] = lb
        else:           # was down
            if close > ub:
                direction.iloc[i] = True
                supertrend.iloc[i] = lb
            else:
                direction.iloc[i] = False
                supertrend.iloc[i] = ub

    return direction


# ── TP/SL exit ─────────────────────────────────────────────────
def tp_sl_exit(d, i, direction, tp_pct=0.12, sl_pct=0.09, max_bars=5):
    entry = d["Close"].iloc[i]
    tp = entry * (1 + tp_pct/100) if direction == "BUY" else entry * (1 - tp_pct/100)
    sl = entry * (1 - sl_pct/100) if direction == "BUY" else entry * (1 + sl_pct/100)
    for j in range(1, max_bars + 1):
        if i + j >= len(d): break
        bar = d.iloc[i + j]
        if direction == "BUY":
            if bar["High"] >= tp: return round(tp - entry, 4), "TP"
            if bar["Low"]  <= sl: return round(sl - entry, 4), "SL"
        else:
            if bar["Low"]  <= tp: return round(entry - tp, 4), "TP"
            if bar["High"] >= sl: return round(entry - sl, 4), "SL"
    ep = d["Close"].iloc[min(i + max_bars, len(d) - 1)]
    return round((ep - entry) if direction == "BUY" else (entry - ep), 4), "TIME"


# ── Main Backtest ──────────────────────────────────────────────
print("Computing indicators...")

# SPY 1m indicators
spy1_macd_green = compute_macd_bb(spy1["Close"])
spy1_st_dir     = compute_supertrend(spy1)

# SPY 5m supertrend (aligned to 1m bars)
spy5_full = fetch("SPY", "5m", 60)
spy5_st_dir = compute_supertrend(spy5_full)
# Forward-fill 5m ST direction onto 1m index
spy5_st_aligned = spy5_st_dir.reindex(spy1.index, method="ffill")

# QQQ 1m direction
qqq1_dir = qqq1["Close"] > qqq1["Close"].shift(1)
qqq1_aligned = qqq1_dir.reindex(spy1.index, method="ffill")

# ADD 1m direction
if add1 is not None:
    add1_dir = add1["Close"] > add1["Close"].shift(1)
    add1_aligned = add1_dir.reindex(spy1.index, method="ffill")
else:
    # Proxy: use SPY's advance-decline proxy (close > open = advancing)
    add1_aligned = (spy1["Close"] > spy1["Open"]).rolling(3).mean() > 0.5

warmup = 60  # bars for indicator warmup

trades = []
for date in spy1.index.normalize().unique():
    date = date.date()
    mask = spy1.index.date == date
    d = spy1[mask]
    if len(d) < warmup + 5: continue

    # Per-day slices
    macd_g  = spy1_macd_green[mask]
    st1_d   = spy1_st_dir[mask]
    st5_d   = spy5_st_aligned[mask]
    qqq_d   = qqq1_aligned[mask]
    add_d   = add1_aligned[mask]

    cooldown = 0
    for i in range(warmup, len(d) - 5):
        if cooldown > 0:
            cooldown -= 1
            continue

        factor1 = bool(macd_g.iloc[i])    # MACD BB green
        factor2 = bool(qqq_d.iloc[i])     # QQQ 1m up
        factor3 = bool(add_d.iloc[i])     # ADD 1m up
        factor4 = bool(st5_d.iloc[i])     # SPY 5m ST up
        factor5 = bool(st1_d.iloc[i])     # SPY 1m ST up

        bull_count = sum([factor1, factor2, factor3, factor4, factor5])
        bear_count = 5 - bull_count

        if bull_count == 5:
            sig = "BUY"
        elif bear_count == 5:
            sig = "SELL"
        else:
            continue

        pnl, reason = tp_sl_exit(d, i, sig, tp_pct=0.12, sl_pct=0.09, max_bars=5)
        trades.append({
            "date":   date,
            "time":   d.index[i].strftime("%H:%M PT"),
            "signal": sig,
            "conf":   "5/5",
            "entry":  round(d["Close"].iloc[i], 3),
            "pnl":    pnl,
            "exit":   reason,
            "win":    pnl > 0,
            "f1_macd": factor1, "f2_qqq": factor2,
            "f3_add":  factor3, "f4_spy5": factor4, "f5_spy1": factor5,
        })
        cooldown = 2

# ── Results ────────────────────────────────────────────────────
if not trades:
    print("No 5/5 signals generated in this period.")
else:
    r = pd.DataFrame(trades)
    t = len(r); w = r["win"].sum(); wr = w/t*100
    gw = r[r["win"]]["pnl"].sum(); gl = abs(r[~r["win"]]["pnl"].sum())
    pf = gw/gl if gl > 0 else 999
    pnl = r["pnl"].sum()
    aw = r[r["win"]]["pnl"].mean()
    al = r[~r["win"]]["pnl"].mean() if (~r["win"]).any() else 0
    bwr = r[r["signal"]=="BUY"]["win"].mean()*100 if (r["signal"]=="BUY").any() else 0
    swr = r[r["signal"]=="SELL"]["win"].mean()*100 if (r["signal"]=="SELL").any() else 0
    days = spy1.index.normalize().nunique()
    avg_day = t / days

    print("=" * 60)
    print("  AK MACD BB v1.19 — 5-Confluence Backtest")
    print("  LA: 6:30-8:15 AM PT  |  TP:+0.12%  SL:-0.09%")
    print("=" * 60)
    print(f"  Total Trades   : {t}  (BUY {(r['signal']=='BUY').sum()}  SELL {(r['signal']=='SELL').sum()})")
    print(f"  Win Rate       : {wr:.1f}%  (BUY {bwr:.1f}%  SELL {swr:.1f}%)")
    print(f"  Profit Factor  : {pf:.2f}")
    print(f"  Avg Win / Loss : +{aw:.4f} / {al:.4f} pts")
    print(f"  Total PnL      : {pnl:.2f} pts")
    print(f"  Avg/day        : {avg_day:.1f}  (over {days} trading days)")
    tp_c = (r["exit"]=="TP").sum(); sl_c = (r["exit"]=="SL").sum(); tm_c = (r["exit"]=="TIME").sum()
    print(f"  Exits          : TP={tp_c}  SL={sl_c}  Time={tm_c}")

    # Daily breakdown
    daily = r.groupby("date").agg(trades=("win","count"), wins=("win","sum"), pnl_d=("pnl","sum"))
    daily["wr"] = (daily["wins"]/daily["trades"]*100).round(1)
    zero_days = days - len(daily)
    print(f"\n  Daily WR  : avg {daily['wr'].mean():.1f}%  best {daily['wr'].max():.0f}%  worst {daily['wr'].min():.0f}%")
    print(f"  Days 0 trades: {zero_days}")

    print()
    print(f"  {'Date':<12} {'Trades':>7} {'Wins':>5} {'WR%':>7} {'PnL':>8}")
    print(f"  {'-'*44}")
    for date, row in daily.iterrows():
        ok = " **" if row["wr"] >= 60 else "   "
        print(f"  {str(date):<12} {int(row['trades']):>7} {int(row['wins']):>5} {row['wr']:>6.1f}%{ok} {row['pnl_d']:>8.3f}")

    r.to_csv("backtest_ak_macd_v119.csv", index=False)
    print(f"\n  Full results saved: backtest_ak_macd_v119.csv")

    # Factor contribution analysis
    print()
    print("  FACTOR ANALYSIS (how often each factor was bullish on signal bars)")
    print(f"  MACD BB  bullish: {r['f1_macd'].sum()}/{t} = {r['f1_macd'].mean()*100:.0f}%")
    print(f"  QQQ 1m   up:      {r['f2_qqq'].sum()}/{t} = {r['f2_qqq'].mean()*100:.0f}%")
    print(f"  ADD 1m   up:      {r['f3_add'].sum()}/{t} = {r['f3_add'].mean()*100:.0f}%")
    print(f"  SPY 5m   up:      {r['f4_spy5'].sum()}/{t} = {r['f4_spy5'].mean()*100:.0f}%")
    print(f"  SPY 1m   up:      {r['f5_spy1'].sum()}/{t} = {r['f5_spy1'].mean()*100:.0f}%")
    print(f"  (all 5/5 BUY signals: 100% by definition, SELL signals: 0%)")

    # Also test 4/5 confluence for comparison
    print()
    print("  BONUS: 4/5 confluence results (for comparison)...")
    trades4 = []
    for date in spy1.index.normalize().unique():
        date = date.date()
        mask = spy1.index.date == date
        d = spy1[mask]
        if len(d) < warmup + 5: continue
        macd_g = spy1_macd_green[mask]; st1_d = spy1_st_dir[mask]
        st5_d = spy5_st_aligned[mask]; qqq_d = qqq1_aligned[mask]; add_d = add1_aligned[mask]
        cooldown = 0
        for i in range(warmup, len(d) - 5):
            if cooldown > 0: cooldown -= 1; continue
            bc = sum([bool(macd_g.iloc[i]), bool(qqq_d.iloc[i]), bool(add_d.iloc[i]),
                      bool(st5_d.iloc[i]), bool(st1_d.iloc[i])])
            if bc == 4:
                sig = "BUY"
            elif bc == 1:
                sig = "SELL"
            else:
                continue
            pnl, reason = tp_sl_exit(d, i, sig, 0.12, 0.09, 5)
            trades4.append({"win": pnl > 0, "pnl": pnl, "signal": sig})
            cooldown = 2

    if trades4:
        r4 = pd.DataFrame(trades4)
        wr4 = r4["win"].mean()*100
        pf4 = r4[r4["win"]]["pnl"].sum() / abs(r4[~r4["win"]]["pnl"].sum()) if (~r4["win"]).any() else 999
        print(f"  4/5 trades: {len(r4)}  WR: {wr4:.1f}%  PF: {pf4:.2f}  Avg/day: {len(r4)/days:.1f}")
