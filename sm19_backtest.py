"""
Backtest of Hiranya Signal Monitor v1.9 (TradingView) on 7 years of SPY 1-min data.
Rebuilt from the Pine source (score, range filter, arm/break state machine, buyFlip/sellFlip, brkUp/brkDn).
$ADD has no history here -> treated as a missing feed (dropped from score + normaliser), exactly as v1.9 does.
Signals counted when they fire 6:35-8:00 PT. Exits = same ATR exits as the other studies:
  D = 1.5x 1-min ATR stop, half at 1.5R, BE, rest 2.5R or 1-min close through 9 EMA
  B = 1.5x 1-min ATR stop, 2.5R target. Max hold 60 min.
Out: sm19_report.md, sm19_signals.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd
import ema_atr_backtest as eab

HERE = Path(__file__).resolve().parent
PT = "America/Los_Angeles"


def rma(s, n):
    return s.ewm(alpha=1 / n, adjust=False).mean()


spy = eab.load("SPY", 7)
qqq = eab.load("QQQ", 7)
c, h, l, o, v = spy.c, spy.h, spy.l, spy.o, spy.v
ef = c.ewm(span=9, adjust=False).mean()
es = c.ewm(span=21, adjust=False).mean()
et = c.ewm(span=50, adjust=False).mean()
d = c.diff()
rsi = 100 - 100 / (1 + rma(d.clip(lower=0), 14) / rma((-d).clip(lower=0), 14).replace(0, np.nan))
macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
hist = macd - macd.ewm(span=9, adjust=False).mean()
vavg = v.rolling(20).mean()
tp = (h + l + c) / 3
vwap = (tp * v).groupby(spy.date).cumsum() / v.groupby(spy.date).cumsum()   # session VWAP from 1:00 PT (ext hours chart)

# range measures
er = (c - c.shift(20)).abs() / c.diff().abs().rolling(20).sum()
pc = c.shift(1)
tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
up, dn = h.diff(), -l.diff()
pdm = np.where((up > dn) & (up > 0), up, 0.0)
mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
atr14 = rma(tr, 14)
pdi = 100 * rma(pd.Series(pdm, index=c.index), 14) / atr14
mdi = 100 * rma(pd.Series(mdm, index=c.index), 14) / atr14
adx = rma(100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan), 14)
trs = tr.rolling(14).sum()
rng14 = h.rolling(14).max() - l.rolling(14).min()
chop = 100 * np.log10(trs / rng14) / np.log10(14)
sp = ef - es
crossbar = (np.sign(sp) != np.sign(sp.shift(1))) & sp.shift(1).notna()
xcount = crossbar.astype(float).rolling(30).sum()

# confirmation feeds (3-bar change)
qchg = (qqq.c - qqq.c.shift(3)).reindex(c.index).ffill()
m1chg = c - c.shift(3)
c5 = c.resample("5min", label="right", closed="left").last().dropna()
m5 = (c5 - c5.shift(3))
m5.index = m5.index - pd.Timedelta(minutes=1)
m5chg = m5.reindex(c.index, method="ffill")

W = dict(cross=21, m5=9, m1=6, qqq=8, trend=7, vwap=5, macd=4, rsi=2, vol=2)
sgn = lambda x, w: np.where(x > 0, w, np.where(x < 0, -w, 0))
raw = (np.where(ef > es, W["cross"], -W["cross"]) + np.where(c > et, W["trend"], -W["trend"])
       + np.where(c > vwap, W["vwap"], -W["vwap"]) + np.where(hist > 0, W["macd"], -W["macd"])
       + np.where(rsi > 55, W["rsi"], np.where(rsi < 45, -W["rsi"], 0))
       + np.where(v > vavg, np.where(c > o, W["vol"], -W["vol"]), 0)
       + sgn(qchg.fillna(0).to_numpy(), W["qqq"]) + sgn(m5chg.fillna(0).to_numpy(), W["m5"])
       + sgn(m1chg.fillna(0).to_numpy(), W["m1"]))
maxsum = sum(W.values())
score = np.clip(50 + 50 * raw / maxsum, 0, 100)

votes = ((er < 0.30).astype(int) + (adx < 20).astype(int) + (chop > 61.8).astype(int) + (xcount >= 3).astype(int)).to_numpy()
isRange = votes >= 2

# state machine (brkOn, armHolds, brkAgree = true; minRngBars 8, armBars 15, holdBars 3)
n = len(c)
H, Lo, C = h.to_numpy(), l.to_numpy(), c.to_numpy()
rec = np.zeros(n, np.int8)       # 0 WAIT 1 BUY -1 SELL 2 NO TRADE 3 ARMED 4 BRK UP -4 BRK DN
brk = np.zeros(n, np.int8)
rngHi = rngLo = np.nan; rngLen = 0; armed = False; armLeft = 0; brkBar = -999; brkBull = False
prevRange = False
for i in range(n):
    if isRange[i]:
        if not prevRange:
            rngHi, rngLo, rngLen = H[i], Lo[i], 1
        else:
            rngHi = max(rngHi if rngHi == rngHi else H[i], H[i]); rngLo = min(rngLo if rngLo == rngLo else Lo[i], Lo[i]); rngLen += 1
        armed, armLeft = False, 0
    else:
        if prevRange and rngLen >= 8:
            armed, armLeft = True, 15
        elif armed:
            armLeft -= 1
            if armLeft <= 0:
                armed = False
    bu = armed and rngHi == rngHi and C[i] > rngHi and score[i] >= 50
    bd = armed and rngLo == rngLo and C[i] < rngLo and score[i] <= 50
    if bu or bd:
        brkBar, brkBull, armed, armLeft = i, bu, False, 0
        brk[i] = 1 if bu else -1
    live = i - brkBar < 3
    if isRange[i]:
        rec[i] = 2
    elif live:
        rec[i] = 4 if brkBull else -4
    elif armed:
        rec[i] = 3
    elif score[i] >= 70:
        rec[i] = 1
    elif score[i] <= 30:
        rec[i] = -1
    prevRange = isRange[i]

prev = np.r_[0, rec[:-1]]
buyFlip = (rec == 1) & (prev != 1)
sellFlip = (rec == -1) & (prev != -1)

cutoff = pd.Timestamp.now(tz=PT).normalize() - pd.DateOffset(years=7)
mins = spy.m.to_numpy(); dates = spy.date.to_numpy()
win = (mins >= 395) & (mins < 480) & (spy.index >= cutoff)
e9 = spy.ema9.to_numpy(); atr1 = spy.atr1.to_numpy(); datr = spy.datr.to_numpy()
dh, dl = spy.day_hi.to_numpy(), spy.day_lo.to_numpy()

rows = []
for kind, mask, dirv in [("BUY", buyFlip, 1), ("SELL", sellFlip, -1), ("BRK UP", brk == 1, 1), ("BRK DN", brk == -1, -1)]:
    for i in np.flatnonzero(mask & win):
        end = i + 1
        while end < n and end <= i + 60 and dates[end] == dates[i]:
            end += 1
        if end == i + 1:
            continue
        risk = 1.5 * atr1[i]
        rb_res, rb, _ = eab.sim_fixed(dirv, C[i], risk, 2.5, H[i + 1:end], Lo[i + 1:end])
        if rb is None:
            rb = dirv * (C[end - 1] - C[i]) / risk
        rd_res, rd = eab.sim_managed(dirv, C[i], risk, H[i + 1:end], Lo[i + 1:end], C[i + 1:end], e9[i + 1:end])
        rows.append({"time_pt": spy.index[i].strftime("%Y-%m-%d %H:%M"), "date": dates[i], "year": spy.index[i].year,
                     "kind": kind, "group": "SCORE" if kind in ("BUY", "SELL") else "BREAK", "mins": int(mins[i]),
                     "score": round(float(score[i]), 1), "votes": int(votes[i]),
                     "range_used": round((dh[i] - dl[i]) / datr[i], 3) if datr[i] == datr[i] else np.nan,
                     "R_D": rd, "res_D": rd_res, "R_B": rb, "res_B": rb_res})
t = pd.DataFrame(rows).sort_values("time_pt")
t["nth_today"] = t.groupby(["date", "group"]).cumcount() + 1
t["train"] = pd.to_datetime(t.date) < "2024-01-01"
t.to_csv(HERE / "sm19_signals.csv", index=False)

ndays = len(np.unique(dates[win]))


def row(lab, g):
    if len(g) < 15:
        return f"| {lab} | {len(g)} | - | - | - | - | - | - |"
    yrs = g[g.year >= 2020].groupby("year").R_D.mean()
    return (f"| {lab} | {len(g)} | {g.date.nunique() / 7:.0f} | {(g.res_D == 'stop').mean() * 100:.0f}% | "
            f"{g[g.train].R_D.mean():+.3f} | {g[~g.train].R_D.mean():+.3f} | {g.R_B.mean():+.3f} | {(yrs > 0).sum()}/{len(yrs)} |")


S = t[t.group == "SCORE"]; B = t[t.group == "BREAK"]
L = ["# Hiranya Signal Monitor v1.9 - 7-year backtest (SPY 1-min, signals 6:35-8:00 PT, no $ADD)", "",
     f"{ndays} trading days. R_D = your exits. Train = 2019-23, Test = 2024-26. 'stopped' = full 1R loss.", "",
     "| signal | trades | days/yr | stopped | R_D 2019-23 | R_D 2024-26 | R_B all | yrs R_D>0 |", "|---|---|---|---|---|---|---|---|",
     row("All BUY/SELL flips", S), row("BUY", S[S.kind == "BUY"]), row("SELL", S[S.kind == "SELL"]),
     row("1st score signal of day", S[S.nth_today == 1]), row("2nd+ score signal", S[S.nth_today > 1]),
     row("All BRK (range break)", B), row("BRK UP", B[B.kind == "BRK UP"]), row("BRK DN", B[B.kind == "BRK DN"]),
     "", "## Score signals + playbook filters",
     "| signal | trades | days/yr | stopped | R_D 2019-23 | R_D 2024-26 | R_B all | yrs R_D>0 |", "|---|---|---|---|---|---|---|---|",
     row("flip + range used >= 0.25 ATR", S[S.range_used >= 0.25]),
     row("flip + range used >= 0.40 ATR", S[S.range_used >= 0.40]),
     row("flip + range used < 0.25 ATR", S[S.range_used < 0.25]),
     row("1st flip + range >= 0.25", S[(S.nth_today == 1) & (S.range_used >= 0.25)]),
     row("1st flip + range >= 0.40", S[(S.nth_today == 1) & (S.range_used >= 0.40)]),
     row("flip before 7:00", S[S.mins < 420]), row("flip 7:00-8:00", S[S.mins >= 420]),
     row("1st flip before 7:00 + range >= 0.40", S[(S.nth_today == 1) & (S.mins < 420) & (S.range_used >= 0.40)]),
     "", "## Signals per day", f"Score flips per day (window): mean {len(S) / ndays:.2f}; days with >=1 flip: {S.date.nunique()} of {ndays}",
     f"Range breaks per day: mean {len(B) / ndays:.2f}; days with >=1 break: {B.date.nunique()}",
     f"Share of window bars blocked as RANGE: {isRange[win].mean() * 100:.0f}%"]
rep = "\n".join(L)
print(rep)
(HERE / "sm19_report.md").write_text(rep, encoding="utf-8")

# per-bar export for joining with 9/21 crosses
bars = pd.DataFrame({'time_pt': spy.index.strftime('%Y-%m-%d %H:%M'), 'score': np.round(score, 1), 'votes': votes, 'rec': rec})[win]
bars.to_csv(HERE / 'sm19_bars.csv', index=False)
print('saved sm19_bars.csv', len(bars))
