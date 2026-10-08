"""
9/21 cross + AK MACD BB v1.19 components (minus $ADD, not in Alpaca data).
Rebuilt from your Pine script:
  MACD 12/26/9 histogram, BB(20, 2.0) on the histogram
    green dot  = (hist > 0 and hist rising) or hist >= upper band     (your v1.19)
    red dot    = not green                                            (your v1.19)
    red_sym    = (hist < 0 and hist falling) or hist <= lower band    (symmetric version, tested too)
  Supertrend(10, 3.0) on SPY 1-min and SPY 5-min
  QQQ 1-min candle up (close > previous close)
Joined onto ema_rsi_trades_7y.csv (raw 9/21 crosses with ATR exits + RSI + ATR filter fields).
Out: ema_akmacd_report_7y.md, ema_akmacd_trades_7y.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PT = "America/Los_Angeles"


def load(sym):
    df = pd.read_csv(HERE / "data_cache" / f"{sym}_1m_7y.csv", parse_dates=["ts"]).set_index("ts")
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(PT)
    m = df.index.hour * 60 + df.index.minute
    return df[(m >= 60) & (m < 1020)].copy()


def supertrend_up(h, l, c, n=10, f=3.0):
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    hl2 = (h + l) / 2
    ub, lb = hl2 + f * atr, hl2 - f * atr
    fu, fl = ub.copy(), lb.copy()
    up = np.zeros(len(c), bool)
    up[0] = True
    for i in range(1, len(c)):
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        if up[i - 1]:
            up[i] = not (c[i] < fl[i])
        else:
            up[i] = c[i] > fu[i]
    return up


spy = load("SPY")
qqq = load("QQQ")
c = spy["c"]
macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
hist = macd - macd.ewm(span=9, adjust=False).mean()
basis = hist.rolling(20).mean()
dev = 2.0 * hist.rolling(20).std(ddof=0)
green = ((hist > 0) & (hist > hist.shift(1))) | (hist >= basis + dev)
red_sym = ((hist < 0) & (hist < hist.shift(1))) | (hist <= basis - dev)
bb_break_up = hist >= basis + dev
bb_break_dn = hist <= basis - dev

st1 = pd.Series(supertrend_up(spy.h, spy.l, spy.c), index=spy.index)
o5 = spy.resample("5min", label="right", closed="left").agg({"h": "max", "l": "min", "c": "last"}).dropna()
st5 = pd.Series(supertrend_up(o5.h, o5.l, o5.c), index=o5.index - pd.Timedelta(minutes=1))
st5 = st5.reindex(spy.index, method="ffill")
qup = (qqq["c"] > qqq["c"].shift(1)).reindex(spy.index).fillna(False)

feat = pd.DataFrame({"green": green, "red_sym": red_sym, "bb_up": bb_break_up, "bb_dn": bb_break_dn,
                     "st1": st1, "st5": st5, "qqq_up1": qup, "hist": hist}, index=spy.index)
feat.index = feat.index.strftime("%Y-%m-%d %H:%M")
feat = feat[~feat.index.duplicated()]

t = pd.read_csv(HERE / "ema_rsi_trades_7y.csv").join(feat, on="time_pt")
L_ = t.dir == "LONG"
t["macd_ok"] = np.where(L_, t.green, ~t.green)                    # your v1.19 definition
t["macd_sym_ok"] = np.where(L_, t.green, t.red_sym)               # symmetric red dot
t["macd_bb_break"] = np.where(L_, t.bb_up, t.bb_dn)               # histogram outside its BB
t["st1_ok"] = np.where(L_, t.st1, ~t.st1.astype(bool))
t["st5_ok"] = np.where(L_, t.st5, ~t.st5.astype(bool))
t["qqq1_ok"] = np.where(L_, t.qqq_up1, ~t.qqq_up1.astype(bool))
for col in ["macd_ok", "macd_sym_ok", "macd_bb_break", "st1_ok", "st5_ok", "qqq1_ok"]:
    t[col] = t[col].astype(bool)
t["ak4"] = t.macd_ok & t.st1_ok & t.st5_ok & t.qqq1_ok
t["ak_score"] = t[["macd_ok", "st1_ok", "st5_ok", "qqq1_ok"]].sum(axis=1)
atrf = (t.cross_n <= 2) & t.qqq_aligned & t.vwap_aligned & (t.range_used >= 0.25)
rsi_pb = t.dir_rsi5 < 50


def row(lab, g):
    if len(g) < 25:
        return None
    return (f"| {lab} | {len(g)} | {(g.res_A == 'target').mean() * 100:.0f}% | {g.R_D.mean():+.3f} | "
            f"{g.R_B.mean():+.3f} | {(g.res_D == 'stop').mean() * 100:.0f}% |")


def tab(groups):
    out = ["| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |", "|---|---|---|---|---|---|"]
    return "\n".join(out + [r for r in (row(k, g) for k, g in groups) if r])


S = ["# 9/21 cross + AK MACD BB v1.19 components (no $ADD) - SPY 1-min, 6:35-8:00 PT, 7 years", "",
     "D = your exits (1.5xATR stop, half at 1.5R, BE, 2.5R or 9 EMA trail). B = 1.5xATR stop, 2.5R target.", "",
     "## Each component as a filter on ALL 9/21 crosses",
     tab([("ALL crosses", t),
          ("MACD dot agrees (v1.19)", t[t.macd_ok]), ("MACD dot disagrees", t[~t.macd_ok]),
          ("MACD symmetric dot agrees", t[t.macd_sym_ok]),
          ("MACD hist outside its BB", t[t.macd_bb_break]),
          ("1m Supertrend agrees", t[t.st1_ok]), ("1m Supertrend against", t[~t.st1_ok]),
          ("5m Supertrend agrees", t[t.st5_ok]), ("5m Supertrend against", t[~t.st5_ok]),
          ("QQQ 1m candle agrees", t[t.qqq1_ok]),
          ("AK 4/4 agree (all but ADD)", t[t.ak4])]), "",
     "### By AK score (0-4 components agreeing)",
     tab([(f"{k}/4", g) for k, g in t.groupby("ak_score")]), "",
     "## On top of the ATR 'day in play' filter (cross 1-2 + QQQ + VWAP + range >= 0.25x daily ATR)",
     tab([("ATR filter", t[atrf]),
          ("+ MACD dot agrees", t[atrf & t.macd_ok]), ("+ MACD dot disagrees", t[atrf & ~t.macd_ok]),
          ("+ MACD hist outside BB", t[atrf & t.macd_bb_break]),
          ("+ 1m Supertrend agrees", t[atrf & t.st1_ok]),
          ("+ 5m Supertrend agrees", t[atrf & t.st5_ok]), ("+ 5m Supertrend against", t[atrf & ~t.st5_ok]),
          ("+ AK 4/4", t[atrf & t.ak4])]), "",
     "## ATR filter + 5m RSI < 50 (the pullback setup) + AK components",
     tab([("ATR + RSI pullback", t[atrf & rsi_pb]),
          ("+ MACD dot agrees", t[atrf & rsi_pb & t.macd_ok]),
          ("+ MACD dot disagrees", t[atrf & rsi_pb & ~t.macd_ok]),
          ("+ 1m Supertrend agrees", t[atrf & rsi_pb & t.st1_ok]),
          ("+ 5m Supertrend agrees", t[atrf & rsi_pb & t.st5_ok]),
          ("+ 5m Supertrend against", t[atrf & rsi_pb & ~t.st5_ok])]), ""]
rep = "\n".join(S)
print(rep)
(HERE / "ema_akmacd_report_7y.md").write_text(rep, encoding="utf-8")
t.to_csv(HERE / "ema_akmacd_trades_7y.csv", index=False)
