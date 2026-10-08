"""
Final 9/21 EMA cross study — SPY 1-min, crosses 6:35-8:00 PT, 7 years.
Honest selection: filter combos are ranked on TRAIN (before 2024) only, then shown on TEST (2024+).

Inputs : ema_akmacd_trades_7y.csv (raw crosses + ATR/RSI/AK features), data_cache/SPY_1m_7y.csv
Needs  : ema_atr_backtest.py in the same folder (load + exit simulators)
Out    : final_921_report.md, final_921_trades.csv
"""
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

import ema_atr_backtest as eab

HERE = Path(__file__).resolve().parent
PT = "America/Los_Angeles"
SPLIT = "2024-01-01"


# ------------------------------------------------------------ extra features
spy = eab.load("SPY", 7)
cutoff = pd.Timestamp.now(tz=PT).normalize() - pd.DateOffset(years=7)
spy = spy[spy.index >= cutoff]
key = spy.index.strftime("%Y-%m-%d %H:%M")

c5 = spy["c"].resample("5min", label="right", closed="left").last().dropna()
e5 = (c5.ewm(span=9, adjust=False).mean() - c5.ewm(span=21, adjust=False).mean())
e5.index = e5.index - pd.Timedelta(minutes=1)
spy["ema5_spread"] = e5.reindex(spy.index, method="ffill")

rth = spy[(spy.m >= 390) & (spy.m < 780)]
dly = rth.groupby("date").agg(open=("o", "first"), hi=("h", "max"), lo=("l", "min"), close=("c", "last"))
orb = spy[(spy.m >= 390) & (spy.m < 395)].groupby("date").agg(orh=("h", "max"), orl=("l", "min"))
dly["prev_close"], dly["prev_hi"], dly["prev_lo"] = dly.close.shift(1), dly.hi.shift(1), dly.lo.shift(1)
dly = dly.join(orb)

feat = pd.DataFrame({"ema5_spread": spy["ema5_spread"].values}, index=key)
feat = feat[~feat.index.duplicated()]

t = pd.read_csv(HERE / "ema_akmacd_trades_7y.csv")
t = t.join(feat, on="time_pt")
t["date"] = pd.to_datetime(t["date"]).dt.date
t = t.join(dly, on="date")
d = np.where(t.dir == "LONG", 1, -1)
t["f_ema5"] = d * t.ema5_spread > 0
t["f_dayside"] = d * (t.entry - t.open) > 0
t["f_gap"] = d * (t.open - t.prev_close) > 0
t["f_outOR"] = np.where(d == 1, t.entry > t.orh, t.entry < t.orl)
t["f_prevlvl"] = np.where(d == 1, t.entry > t.prev_hi, t.entry < t.prev_lo)

# ------------------------------------------------------------ pullback-to-9EMA trigger
c = spy.c.to_numpy(); h = spy.h.to_numpy(); l = spy.l.to_numpy()
e9 = spy.ema9.to_numpy(); sp = spy.spread.to_numpy(); atr1 = spy.atr1.to_numpy()
dates = spy.date.to_numpy(); mins = spy.m.to_numpy()
pos = {k: i for i, k in enumerate(key)}
pb = []
for _, r in t.iterrows():
    i = pos.get(r.time_pt)
    if i is None:
        continue
    dd = 1 if r.dir == "LONG" else -1
    j = None
    for k in range(i + 1, min(i + 11, len(c))):
        if dates[k] != dates[i] or np.sign(sp[k]) != dd:
            break
        touched = (l[k] <= e9[k]) if dd == 1 else (h[k] >= e9[k])
        held = (c[k] > e9[k]) if dd == 1 else (c[k] < e9[k])
        if touched and held:
            j = k
            break
    if j is None:
        continue
    end = j + 1
    while end < len(c) and end <= j + 60 and dates[end] == dates[j]:
        end += 1
    fh, fl, fc, fe = h[j + 1:end], l[j + 1:end], c[j + 1:end], e9[j + 1:end]
    if len(fc) == 0:
        continue
    risk = 1.5 * atr1[j]
    res_b, rb, _ = eab.sim_fixed(dd, c[j], risk, 2.5, fh, fl)
    if rb is None:
        rb = dd * (fc[-1] - c[j]) / risk
    res_d, rd = eab.sim_managed(dd, c[j], risk, fh, fl, fc, fe)
    pb.append({"time_pt": r.time_pt, "pb_R_B": rb, "pb_R_D": rd, "pb_res_D": res_d,
               "pb_wait": j - i, "pb_mins": int(mins[j])})
pbd = pd.DataFrame(pb).set_index("time_pt")
t = t.join(pbd, on="time_pt")

# ------------------------------------------------------------ filters
F = {
    "cross1-2": t.cross_n <= 2, "cross1": t.cross_n == 1,
    "QQQ 9/21": t.qqq_aligned.astype(bool), "VWAP": t.vwap_aligned.astype(bool),
    "range>=0.25ATR": t.range_used >= 0.25, "range>=0.40ATR": t.range_used >= 0.40,
    "5m RSI pullback": t.dir_rsi5 < 50, "5m ST not yet": ~t.st5_ok.astype(bool),
    "1m ST agrees": t.st1_ok.astype(bool), "MACD dot": t.macd_ok.astype(bool),
    "5m 9/21 agrees": t.f_ema5, "above/below day open": t.f_dayside, "gap dir": t.f_gap,
    "outside 5m OR": t.f_outOR, "beyond prev-day H/L": t.f_prevlvl,
    "before 7:30": t.mins < 450, "fast tape (ATR ratio>5)": t.atr_ratio >= 5.0,
}
names = list(F)
M = np.vstack([F[n].fillna(False).to_numpy() for n in names])
train = (pd.to_datetime(t.date) < SPLIT).to_numpy()
test = ~train


def ev(mask, col):
    a, b = t[col].to_numpy()[mask & train], t[col].to_numpy()[mask & test]
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    return len(a), (a.mean() if len(a) else np.nan), len(b), (b.mean() if len(b) else np.nan)


def search(col, min_train=150, max_k=3):
    out = []
    for k in range(1, max_k + 1):
        for combo in combinations(range(len(names)), k):
            mask = M[list(combo)].all(axis=0)
            ntr, rtr, nte, rte = ev(mask, col)
            if ntr >= min_train and nte >= 40:
                out.append((" + ".join(names[i] for i in combo), ntr, rtr, nte, rte))
    return pd.DataFrame(out, columns=["filters", "n_train", "R_train", "n_test", "R_test"]).sort_values("R_train", ascending=False)


L = ["# Final 9/21 EMA cross study - SPY 1-min, 6:35-8:00 PT, 7 years", "",
     f"TRAIN = Sep 2019 - Dec 2023, TEST = Jan 2024 - Oct 2026 (never used to pick filters). "
     "R_D = your exits (1.5xATR stop, half at 1.5R, BE, 2.5R / 9 EMA trail). R_B = 1.5xATR stop, 2.5R target.", ""]

L += ["## Baselines", "| entry | trades train | avg R_D train | trades test | avg R_D test | avg R_B test |", "|---|---|---|---|---|---|"]
allm = np.ones(len(t), bool)
for lab, rd, rb in [("enter on cross close", "R_D", "R_B"), ("wait for pullback to 9 EMA", "pb_R_D", "pb_R_B")]:
    a = ev(allm, rd); b = ev(allm, rb)
    L.append(f"| {lab} | {a[0]} | {a[1]:+.3f} | {a[2]} | {a[3]:+.3f} | {b[3]:+.3f} |")

summary = {}
for lab, col in [("cross entry, your exits (R_D)", "R_D"), ("cross entry, 2.5R target (R_B)", "R_B"),
                 ("pullback entry, your exits", "pb_R_D"), ("pullback entry, 2.5R target", "pb_R_B")]:
    s = search(col)
    top = s.head(50)
    summary[lab] = s
    L += ["", f"## {lab}: top 15 filter combos ranked on TRAIN only",
          f"Of the top 50 by train, **{(top.R_test > 0).sum()} / 50** stayed positive on test; "
          f"median test avg R of top 50 = {top.R_test.median():+.3f}.", "",
          "| filters | n train | R train | n test | R test |", "|---|---|---|---|---|"]
    for _, r in s.head(15).iterrows():
        L.append(f"| {r.filters} | {r.n_train} | {r.R_train:+.3f} | {r.n_test} | {r.R_test:+.3f} |")

L += ["", "## Most robust combos (cross entry, R_D): best worst-of(train, test), n_train >= 150",
      "Note: this ranking looks at test too, so it is a robustness view, not out-of-sample."]
s = summary["cross entry, your exits (R_D)"].copy()
s["worst"] = s[["R_train", "R_test"]].min(axis=1)
L += ["| filters | n train | R train | n test | R test |", "|---|---|---|---|---|"]
for _, r in s.sort_values("worst", ascending=False).head(15).iterrows():
    L.append(f"| {r.filters} | {r.n_train} | {r.R_train:+.3f} | {r.n_test} | {r.R_test:+.3f} |")

rep = "\n".join(L)
print(rep)
(HERE / "final_921_report.md").write_text(rep, encoding="utf-8")
t.to_csv(HERE / "final_921_trades.csv", index=False)
for n, (lab, s) in enumerate(summary.items(), 1):
    s.assign(variant=lab).to_csv(HERE / f"final_921_combos_{n}.csv", index=False)
