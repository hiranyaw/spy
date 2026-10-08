"""
SPY 9/21 EMA cross + ATR study — 1-min bars, crosses 6:35-8:00 PT, uses cached data from ema_cross_backtest.py.

ATR measures:
  atr1   1-min ATR(14) (Wilder) at the cross bar         -> stop sizing
  datr   daily ATR(14) from regular-hours bars, prior day -> "normal daily move"
  range_used  (6:30-to-now high - low) / datr             -> how much of a normal day is already done
  ext_atr     (close - EMA21) / atr1 in trade direction   -> how stretched the entry is
  spread_atr  |EMA9 - EMA21| / atr1                       -> strength of the cross

Triggers:
  raw        enter at close of the cross bar
  confirmed  enter at the first close within 5 bars where |EMA9-EMA21| >= --confirm x atr1 (else no trade)

Exit variants (R = initial risk):
  A  stop 1.5xATR1, target 1.5R
  B  stop 1.5xATR1, target 2.5R
  C  stop 1.0xATR1, target 2R
  D  your system: stop 1.5xATR1, half off at 1.5R -> stop to breakeven, rest exits at 2.5R
     or on a 1-min close back through the 9 EMA
Max hold --hold minutes; stop is checked before target inside a bar (conservative).

Run:  python ema_atr_backtest.py --years 7
Out:  ema_atr_report_<N>y.md, ema_atr_trades_<N>y.csv
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "data_cache"
PT = "America/Los_Angeles"
W_LO, W_HI = 6 * 60 + 35, 8 * 60


def load(sym, years):
    df = pd.read_csv(CACHE / f"{sym}_1m_{years}y.csv", parse_dates=["ts"]).set_index("ts")
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(PT)
    m = df.index.hour * 60 + df.index.minute
    df = df[(m >= 60) & (m < 1020)].copy()
    df["m"] = df.index.hour * 60 + df.index.minute
    df["date"] = df.index.date
    df["ema9"] = df["c"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["c"].ewm(span=21, adjust=False).mean()
    df["spread"] = df["ema9"] - df["ema21"]
    pc = df["c"].shift(1)
    tr = pd.concat([df["h"] - df["l"], (df["h"] - pc).abs(), (df["l"] - pc).abs()], axis=1).max(axis=1)
    df["atr1"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    rth = df["m"] >= 390
    tp = (df["h"] + df["l"] + df["c"]) / 3
    pv = (tp * df["v"]).where(rth, 0.0)
    vv = df["v"].where(rth, 0.0)
    df["vwap"] = pv.groupby(df["date"]).cumsum() / vv.groupby(df["date"]).cumsum().replace(0, np.nan)
    df["day_hi"] = df["h"].where(rth).groupby(df["date"]).cummax()
    df["day_lo"] = df["l"].where(rth).groupby(df["date"]).cummin()
    r = df[(df.m >= 390) & (df.m < 780)]
    dly = r.groupby("date").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    dpc = dly["c"].shift(1)
    dtr = pd.concat([dly["h"] - dly["l"], (dly["h"] - dpc).abs(), (dly["l"] - dpc).abs()], axis=1).max(axis=1)
    datr = dtr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    df["datr"] = df["date"].map(datr)
    return df


def sim_fixed(d, entry, risk, mult, h, l):
    for i in range(len(h)):
        adv = (entry - l[i]) if d == 1 else (h[i] - entry)
        fav = (h[i] - entry) if d == 1 else (entry - l[i])
        if adv >= risk:
            return "stop", -1.0, i + 1
        if fav >= mult * risk:
            return "target", float(mult), i + 1
    return "timeout", None, len(h)


def sim_managed(d, entry, risk, h, l, c, e9):
    """Half at 1.5R, stop to BE, remainder to 2.5R or 1-min close through 9 EMA."""
    phase, booked = 1, 0.0
    for i in range(len(h)):
        adv = (entry - l[i]) if d == 1 else (h[i] - entry)
        fav = (h[i] - entry) if d == 1 else (entry - l[i])
        if phase == 1:
            if adv >= risk:
                return "stop", -1.0
            if fav >= 1.5 * risk:
                phase, booked = 2, 0.75
                continue
        else:
            if adv >= 0:
                return "tp1+BE", booked
            if fav >= 2.5 * risk:
                return "tp2", booked + 1.25
            if d * (c[i] - e9[i]) < 0:
                return "tp1+trail", booked + 0.5 * d * (c[i] - entry) / risk
    if len(c) == 0:
        return "skip", np.nan
    if phase == 1:
        return "timeout", d * (c[-1] - entry) / risk
    return "tp1+timeout", booked + 0.5 * d * (c[-1] - entry) / risk


def run(args):
    spy = load("SPY", args.years)
    qqq = load("QQQ", args.years)
    spy["qqq_sign"] = np.sign(qqq["spread"]).reindex(spy.index).ffill()
    cutoff = pd.Timestamp.now(tz=PT).normalize() - pd.DateOffset(years=args.years)
    spy = spy[spy.index >= cutoff]

    s = np.sign(spy["spread"])
    prev = s.shift(1)
    cross = ((s != prev) & (s != 0) & (prev != 0) & prev.notna()).to_numpy()

    c = spy.c.to_numpy(); h = spy.h.to_numpy(); l = spy.l.to_numpy()
    e9 = spy.ema9.to_numpy(); e21 = spy.ema21.to_numpy(); sp = spy.spread.to_numpy()
    atr1 = spy.atr1.to_numpy(); datr = spy.datr.to_numpy(); vwap = spy.vwap.to_numpy()
    dh = spy.day_hi.to_numpy(); dl = spy.day_lo.to_numpy(); qs = spy.qqq_sign.to_numpy()
    mins = spy.m.to_numpy(); dates = spy.date.to_numpy(); idx = spy.index

    rows = []
    cross_n = {}
    for i in np.flatnonzero(cross):
        if not (W_LO <= mins[i] < W_HI) or not np.isfinite(datr[i]):
            continue
        d = 1 if sp[i] > 0 else -1
        cross_n[dates[i]] = cross_n.get(dates[i], 0) + 1
        for trig in ["raw", "confirmed"]:
            j = i
            if trig == "confirmed":
                j = None
                for k in range(i, min(i + 6, len(c))):
                    if dates[k] != dates[i] or np.sign(sp[k]) != d:
                        break
                    if abs(sp[k]) >= args.confirm * atr1[k]:
                        j = k
                        break
                if j is None:
                    continue
            entry = c[j]
            end = j + 1
            while end < len(c) and end <= j + args.hold and dates[end] == dates[j]:
                end += 1
            fh, fl, fc, fe9 = h[j + 1:end], l[j + 1:end], c[j + 1:end], e9[j + 1:end]
            if len(fc) == 0:
                continue
            row = {"time_pt": idx[j].strftime("%Y-%m-%d %H:%M"), "date": dates[j], "year": idx[j].year,
                   "trigger": trig, "dir": "LONG" if d == 1 else "SHORT", "entry": round(entry, 2),
                   "cross_n": cross_n[dates[i]], "mins": int(mins[j]),
                   "atr1": round(atr1[j], 3), "datr": round(datr[j], 2),
                   "datr_pct": round(datr[j] / entry * 100, 3),
                   "atr_ratio": round(atr1[j] / datr[j] * 100, 2),
                   "range_used": round((dh[j] - dl[j]) / datr[j], 3),
                   "ext_atr": round(d * (entry - e21[j]) / atr1[j], 2),
                   "spread_atr": round(abs(sp[j]) / atr1[j], 2),
                   "qqq_aligned": bool(qs[j] == d),
                   "vwap_aligned": bool(np.isfinite(vwap[j]) and d * (entry - vwap[j]) > 0)}
            for name, sl, mult in [("A", 1.5, 1.5), ("B", 1.5, 2.5), ("C", 1.0, 2.0)]:
                risk = sl * atr1[j]
                res, r, n = sim_fixed(d, entry, risk, mult, fh, fl)
                if r is None:
                    r = d * (fc[-1] - entry) / risk
                row[f"res_{name}"], row[f"R_{name}"] = res, round(r, 3)
            res, r = sim_managed(d, entry, 1.5 * atr1[j], fh, fl, fc, fe9)
            row["res_D"], row["R_D"] = res, round(r, 3)
            rows.append(row)

    t = pd.DataFrame(rows)
    t.to_csv(HERE / f"ema_atr_trades_{args.years}y.csv", index=False)
    rep = report(t, args)
    print(rep)
    (HERE / f"ema_atr_report_{args.years}y.md").write_text(rep, encoding="utf-8")
    print(f"\nSaved ema_atr_report_{args.years}y.md, ema_atr_trades_{args.years}y.csv")


def line(lab, g):
    if len(g) < 20:
        return None
    hit = lambda v: (g[f"res_{v}"] == "target").mean() * 100
    tp1 = g["res_D"].str.startswith("tp").mean() * 100
    return (f"| {lab} | {len(g)} | {hit('A'):.0f}% | {g.R_A.mean():+.3f} | {hit('B'):.0f}% | {g.R_B.mean():+.3f} | "
            f"{hit('C'):.0f}% | {g.R_C.mean():+.3f} | {tp1:.0f}% | {g.R_D.mean():+.3f} |")


def table(groups):
    out = ["| group | trades | A win | A avg R | B win | B avg R | C win | C avg R | D TP1 hit | D avg R |",
           "|" + "---|" * 10]
    out += [r for r in (line(k, g) for k, g in groups) if r]
    return "\n".join(out)


def qtable(x, col, label):
    q = pd.qcut(x[col], 5, duplicates="drop")
    return [f"### {label}", table([(f"{b.left:.2f} - {b.right:.2f}", g) for b, g in x.groupby(q, observed=True)]), ""]


def report(t, args):
    L = [f"# SPY 9/21 cross + ATR - 6:35-8:00 PT, last {args.years} years", "",
         "A: 1.5xATR stop, 1.5R target (break-even win 40%) | B: 1.5xATR stop, 2.5R (29%) | "
         "C: 1xATR stop, 2R (33%) | D: your system (half at 1.5R, BE stop, rest 2.5R or 9 EMA trail). "
         f"ATR = 1-min ATR(14). Max hold {args.hold} min. Confirmed = EMA gap >= {args.confirm} x ATR within 5 bars.", ""]
    for trig in ["raw", "confirmed"]:
        x = t[t.trigger == trig]
        L += [f"## Trigger: {trig}  ({len(x)} trades)", "",
              table([("ALL", x), ("1st cross of day", x[x.cross_n == 1]), ("2nd cross", x[x.cross_n == 2]),
                     ("3rd+ cross", x[x.cross_n >= 3]), ("QQQ aligned", x[x.qqq_aligned]),
                     ("VWAP aligned", x[x.vwap_aligned]), ("QQQ + VWAP", x[x.qqq_aligned & x.vwap_aligned]),
                     ("cross 1-2 + QQQ + VWAP", x[(x.cross_n <= 2) & x.qqq_aligned & x.vwap_aligned])]), ""]
        L += qtable(x, "range_used", "Range already used (6:30-now high-low / daily ATR)")
        L += qtable(x, "ext_atr", "Entry stretch from 21 EMA (in 1-min ATRs)")
        L += qtable(x, "spread_atr", "9/21 gap at entry (in 1-min ATRs)")
        L += qtable(x, "atr_ratio", "1-min ATR as % of daily ATR (how fast the tape is)")
        L += qtable(x, "datr_pct", "Daily ATR as % of price (volatility regime)")
    return "\n".join(L)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=int, default=7)
    p.add_argument("--hold", type=int, default=60)
    p.add_argument("--confirm", type=float, default=0.25)
    run(p.parse_args())
