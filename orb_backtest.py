"""
SPY 5-minute Opening Range Breakout (ORB) backtest — uses the cached 1-min bars from ema_cross_backtest.py.

Opening range (OR) = high/low of 6:30-6:35 PT (first five 1-min bars).
Breakout = first close beyond the OR between 6:35 and 8:00 PT (one trade per day per trigger).
  trigger "1m": first 1-min candle close beyond OR
  trigger "5m": first 5-min candle close beyond OR (6:40, 6:45, ... closes)
Entry at that candle's close. Exits checked on following 1-min bars, max hold --hold minutes
(stop checked before target inside a bar = conservative).

Exit variants (results in R = multiples of the risk taken):
  OR-1R   stop = other side of OR,  target = 1x risk     (break-even win rate 50%)
  OR-2R   stop = other side of OR,  target = 2x risk     (break-even 33%)
  Mid-2R  stop = OR midpoint,       target = 2x risk     (break-even 33%)
  Pct     stop 0.065%, target 0.13% (same as the 9/21 cross test, break-even 33%)

Filters reported: direction, 9/21 EMA aligned, QQQ also broke its OR same way, VWAP side,
gap direction, breakout time, OR width, year.

Run:  python orb_backtest.py --years 7
Out:  orb_report_<N>y.md, orb_trades_<N>y.csv
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "data_cache"
PT = "America/Los_Angeles"
VARIANTS = ["OR1R", "OR2R", "Mid2R", "Pct"]


def load(sym, years):
    df = pd.read_csv(CACHE / f"{sym}_1m_{years}y.csv", parse_dates=["ts"]).set_index("ts")
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(PT)
    m = df.index.hour * 60 + df.index.minute
    df = df[(m >= 60) & (m < 1020)].copy()
    df["ema9"] = df["c"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["c"].ewm(span=21, adjust=False).mean()
    df["m"] = df.index.hour * 60 + df.index.minute
    df["date"] = df.index.date
    rth = df["m"] >= 390
    tp = (df["h"] + df["l"] + df["c"]) / 3
    pv = (tp * df["v"]).where(rth, 0.0)
    vv = df["v"].where(rth, 0.0)
    df["vwap"] = pv.groupby(df["date"]).cumsum() / vv.groupby(df["date"]).cumsum().replace(0, np.nan)
    return df


def simulate(d, entry, stop, tgt, h, l, c):
    risk = abs(entry - stop)
    if risk <= 0.005:
        return "skip", np.nan
    for i in range(len(c)):
        adv = (entry - l[i]) if d == 1 else (h[i] - entry)
        fav = (h[i] - entry) if d == 1 else (entry - l[i])
        if adv >= risk:
            return "stop", -1.0
        if fav >= abs(tgt - entry):
            return "target", abs(tgt - entry) / risk
    if len(c) == 0:
        return "skip", np.nan
    return "timeout", d * (c[-1] - entry) / risk


def run(args):
    spy = load("SPY", args.years)
    qqq = load("QQQ", args.years)
    cutoff = pd.Timestamp.now(tz=PT).normalize() - pd.DateOffset(years=args.years)

    q_rth = qqq[(qqq.m >= 390) & (qqq.m < 395)]
    q_or = q_rth.groupby("date").agg(qh=("h", "max"), ql=("l", "min"))
    q_close = qqq["c"]

    rth_all = spy[(spy.m >= 390) & (spy.m < 780)]
    prev_close = rth_all.groupby("date")["c"].last().shift(1)

    rows = []
    for date, day in rth_all[rth_all.index >= cutoff].groupby("date"):
        orb = day[day.m < 395]
        if len(orb) < 3:
            continue
        orh, orl = orb.h.max(), orb.l.min()
        mid = (orh + orl) / 2
        open_ = orb.o.iloc[0]
        win = day[(day.m >= 395) & (day.m < 480)]
        if win.empty:
            continue
        broke_up = (win.c > orh).any()
        broke_dn = (win.c < orl).any()
        for trig in ["1m", "5m"]:
            if trig == "1m":
                cand = win
            else:
                cand = win[(win.m - 390) % 5 == 4]
            hit = cand[(cand.c > orh) | (cand.c < orl)]
            if hit.empty:
                continue
            ts = hit.index[0]
            bar = hit.iloc[0]
            d = 1 if bar.c > orh else -1
            entry = bar.c
            fwd = day[(day.index > ts)].iloc[: args.hold]
            h, l, c = fwd.h.to_numpy(), fwd.l.to_numpy(), fwd.c.to_numpy()
            stops = {"OR1R": orl if d == 1 else orh, "OR2R": orl if d == 1 else orh, "Mid2R": mid,
                     "Pct": entry * (1 - d * args.pct_stop / 100)}
            row = {"date": date, "trigger": trig, "time_pt": ts.strftime("%H:%M"), "dir": "LONG" if d == 1 else "SHORT",
                   "entry": round(entry, 2), "or_high": round(orh, 2), "or_low": round(orl, 2),
                   "or_width_pct": round((orh - orl) / open_ * 100, 3),
                   "ema_aligned": bool(np.sign(spy.at[ts, "ema9"] - spy.at[ts, "ema21"]) == d),
                   "vwap_aligned": bool(d * (entry - spy.at[ts, "vwap"]) > 0),
                   "double_break": bool(broke_up and broke_dn),
                   "year": ts.year, "mins": int(bar.m)}
            qc = q_close.get(ts, np.nan)
            if date in q_or.index and np.isfinite(qc):
                qh, ql = q_or.loc[date, "qh"], q_or.loc[date, "ql"]
                row["qqq_confirm"] = bool((qc > qh) if d == 1 else (qc < ql))
            else:
                row["qqq_confirm"] = False
            pc = prev_close.get(date, np.nan)
            row["gap_aligned"] = bool(np.isfinite(pc) and d * (open_ - pc) > 0)
            for v in VARIANTS:
                stop = stops[v]
                risk = abs(entry - stop)
                mult = 1 if v == "OR1R" else 2
                tgt = entry * (1 + d * args.pct_target / 100) if v == "Pct" else entry + d * mult * risk
                res, r = simulate(d, entry, stop, tgt, h, l, c)
                row[f"res_{v}"], row[f"R_{v}"] = res, r
            rows.append(row)

    t = pd.DataFrame(rows)
    t.to_csv(HERE / f"orb_trades_{args.years}y.csv", index=False)
    report = build_report(t, args)
    print(report)
    (HERE / f"orb_report_{args.years}y.md").write_text(report, encoding="utf-8")
    print(f"\nSaved orb_report_{args.years}y.md, orb_trades_{args.years}y.csv")


def stats_row(label, g):
    if len(g) < 15:
        return None
    cells = [label, str(len(g))]
    for v in VARIANTS:
        x = g[g[f"res_{v}"] != "skip"]
        cells.append(f"{(x[f'res_{v}'] == 'target').mean() * 100:.0f}%")
        cells.append(f"{x[f'R_{v}'].mean():+.3f}")
    cells.append(f"{g.double_break.mean() * 100:.0f}%")
    return "| " + " | ".join(cells) + " |"


def table(groups):
    hdr = ("| group | trades | OR-1R win | OR-1R avg R | OR-2R win | OR-2R avg R | Mid-2R win | Mid-2R avg R | "
           "Pct win | Pct avg R | both sides broke |")
    out = [hdr, "|" + "---|" * 11]
    for lab, g in groups:
        r = stats_row(lab, g)
        if r:
            out.append(r)
    return "\n".join(out)


def build_report(t, args):
    L = [f"# SPY 5-min Opening Range Breakout - 6:35-8:00 PT entries, last {args.years} years", "",
         f"OR = 6:30-6:35 PT high/low. One trade per day per trigger, max hold {args.hold} min. "
         "avg R > 0 = profitable before option costs. Break-even win rate: OR-1R 50%, the others 33%.", ""]
    for trig in ["1m", "5m"]:
        x = t[t.trigger == trig]
        L += [f"## Trigger: first {trig} candle close beyond the OR", "",
              f"Days with a breakout: **{len(x)}**  |  median breakout time: {pd.Series(x.mins).median() // 60:.0f}:"
              f"{pd.Series(x.mins).median() % 60:02.0f} PT  |  days both sides broke by 8:00: "
              f"{x.double_break.mean() * 100:.0f}%  |  median OR width: {x.or_width_pct.median():.2f}%", ""]
        groups = [("ALL", x), ("LONG", x[x.dir == "LONG"]), ("SHORT", x[x.dir == "SHORT"]),
                  ("9/21 aligned", x[x.ema_aligned]), ("9/21 against", x[~x.ema_aligned]),
                  ("QQQ also broke out", x[x.qqq_confirm]), ("QQQ did not", x[~x.qqq_confirm]),
                  ("VWAP aligned", x[x.vwap_aligned]),
                  ("With gap direction", x[x.gap_aligned]), ("Against gap", x[~x.gap_aligned]),
                  ("9/21 + QQQ", x[x.ema_aligned & x.qqq_confirm]),
                  ("9/21 + QQQ + VWAP", x[x.ema_aligned & x.qqq_confirm & x.vwap_aligned]),
                  ("9/21 + QQQ + gap", x[x.ema_aligned & x.qqq_confirm & x.gap_aligned]),
                  ("Breakout by 6:45", x[x.mins < 405]), ("6:45-7:15", x[(x.mins >= 405) & (x.mins < 435)]),
                  ("After 7:15", x[x.mins >= 435])]
        L += [table(groups), ""]
        q = pd.qcut(x.or_width_pct, 5, duplicates="drop")
        L += [f"### By OR width ({trig} trigger)",
              table([(f"{b.left:.2f}-{b.right:.2f}%", g) for b, g in x.groupby(q, observed=True)]), ""]
        L += [f"### By year ({trig} trigger)", table([(str(y), g) for y, g in x.groupby("year")]), ""]
    return "\n".join(L)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=int, default=7)
    p.add_argument("--hold", type=int, default=60, help="max minutes in trade")
    p.add_argument("--pct-target", type=float, default=0.13)
    p.add_argument("--pct-stop", type=float, default=0.065)
    run(p.parse_args())
