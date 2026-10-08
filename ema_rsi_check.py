"""
9/21 cross + RSI(14) study. Reuses ema_atr_trades_7y.csv (raw crosses, ATR exits) and adds RSI at the cross bar.
dir_rsi = RSI in the trade's direction (long: RSI, short: 100 - RSI), so >50 = momentum agrees, >70 = stretched.
Exits: D = your system (1.5xATR stop, half at 1.5R, BE, 2.5R / 9 EMA trail), B = 1.5xATR stop, 2.5R target.
Out: ema_rsi_report_7y.md
"""
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PT = "America/Los_Angeles"


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


df = pd.read_csv(HERE / "data_cache" / "SPY_1m_7y.csv", parse_dates=["ts"]).set_index("ts")
df.index = pd.to_datetime(df.index, utc=True).tz_convert(PT)
m = df.index.hour * 60 + df.index.minute
df = df[(m >= 60) & (m < 1020)]
r1 = rsi(df["c"])
c5 = df["c"].resample("5min", label="right", closed="left").last().dropna()
r5 = rsi(c5)
r5.index = r5.index - pd.Timedelta(minutes=1)          # usable at the close of the last 1-min bar in the block
r5 = r5.reindex(df.index, method="ffill")
look = pd.DataFrame({"rsi1": r1.values, "rsi5": r5.values}, index=df.index.strftime("%Y-%m-%d %H:%M"))
look = look[~look.index.duplicated()]

t = pd.read_csv(HERE / "ema_atr_trades_7y.csv")
t = t[t.trigger == "raw"].copy()
t = t.join(look, on="time_pt")
sgn = np.where(t.dir == "LONG", 1, -1)
t["dir_rsi1"] = np.where(sgn == 1, t.rsi1, 100 - t.rsi1)
t["dir_rsi5"] = np.where(sgn == 1, t.rsi5, 100 - t.rsi5)
best = (t.cross_n <= 2) & t.qqq_aligned & t.vwap_aligned & (t.range_used >= 0.25)


def row(lab, g):
    if len(g) < 25:
        return None
    return (f"| {lab} | {len(g)} | {(g.res_A == 'target').mean() * 100:.0f}% | {g.R_D.mean():+.3f} | "
            f"{g.R_B.mean():+.3f} | {(g.res_D == 'stop').mean() * 100:.0f}% |")


def tab(groups):
    out = ["| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |", "|---|---|---|---|---|---|"]
    return "\n".join(out + [r for r in (row(k, g) for k, g in groups) if r])


def bands(x, col, edges):
    return [(f"{lo}-{hi}", x[(x[col] >= lo) & (x[col] < hi)]) for lo, hi in zip(edges[:-1], edges[1:])]


E = [0, 40, 50, 60, 70, 101]
L = ["# 9/21 cross + RSI(14) - SPY 1-min, 6:35-8:00 PT, 7 years", "",
     "RSI is shown in the trade's direction: long = RSI, short = 100 - RSI. "
     "So 60 means 'RSI 60 on a long / RSI 40 on a short'. Break-even: D ~0R, B needs avg R > 0.", "",
     "## All crosses - 1-min RSI at the cross", tab(bands(t, "dir_rsi1", E)), "",
     "## All crosses - 5-min RSI at the cross", tab(bands(t, "dir_rsi5", E)), "",
     "## With the ATR filter (cross 1-2 + QQQ + VWAP + range used >= 0.25x daily ATR)",
     tab([("filter only", t[best])]), "",
     "### ...by 1-min RSI", tab(bands(t[best], "dir_rsi1", E)), "",
     "### ...by 5-min RSI", tab(bands(t[best], "dir_rsi5", E)), "",
     "## Simple RSI rules on all crosses",
     tab([("1m RSI agrees (>50)", t[t.dir_rsi1 > 50]), ("5m RSI agrees (>50)", t[t.dir_rsi5 > 50]),
          ("both agree", t[(t.dir_rsi1 > 50) & (t.dir_rsi5 > 50)]),
          ("5m RSI 50-70 (agrees, not stretched)", t[(t.dir_rsi5 > 50) & (t.dir_rsi5 < 70)]),
          ("5m RSI against (<50)", t[t.dir_rsi5 < 50])]), "",
     "## RSI rules on top of the ATR filter",
     tab([("filter + 5m RSI > 50", t[best & (t.dir_rsi5 > 50)]),
          ("filter + 5m RSI 50-70", t[best & (t.dir_rsi5 > 50) & (t.dir_rsi5 < 70)]),
          ("filter + 5m RSI < 50", t[best & (t.dir_rsi5 < 50)]),
          ("filter + 1m RSI 50-70", t[best & (t.dir_rsi1 > 50) & (t.dir_rsi1 < 70)]),
          ("filter + 1m RSI >= 70", t[best & (t.dir_rsi1 >= 70)])]), ""]
f = t[best & (t.dir_rsi5 > 50) & (t.dir_rsi5 < 70)]
L += ["### filter + 5m RSI 50-70 by year", tab([(str(y), g) for y, g in f.groupby("year")])]
rep = "\n".join(L)
print(rep)
(HERE / "ema_rsi_report_7y.md").write_text(rep, encoding="utf-8")
t.to_csv(HERE / "ema_rsi_trades_7y.csv", index=False)
