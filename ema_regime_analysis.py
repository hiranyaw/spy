"""
Why do some periods have few 9/21 crosses (trend mornings) and others many (chop)?

Joins ema_cross_days_<N>y.csv (from ema_cross_backtest.py) with per-day market conditions
computed from the cached SPY 1-min bars, plus daily VIX from yfinance.

Features per day (PT times):
  known BEFORE the 6:35 window opens (usable as a filter):
    vix_prev       VIX close the day before
    gap_pct        |6:30 open vs prior 13:00 close| in %
    prev_range_pct prior day's 6:30-13:00 high-low range in %
    or5_pct        opening 5-min (6:30-6:35) high-low range in %
    premkt_range   1:00-6:30 pre-market high-low range in %
  measured DURING the window (explains, can't filter on):
    morning_range_pct  6:30-8:00 high-low in %
    efficiency         |8:00 close - 6:30 open| / morning range  (1 = straight line, 0 = round trip)

Run:  python ema_regime_analysis.py --years 7
Out:  ema_regime_report_<N>y.md, ema_regime_days_<N>y.csv
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PT = "America/Los_Angeles"


def day_features(years):
    f = HERE / "data_cache" / f"SPY_1m_{years}y.csv"
    df = pd.read_csv(f, parse_dates=["ts"]).set_index("ts")
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(PT)
    m = df.index.hour * 60 + df.index.minute
    df["date"] = df.index.date
    df["m"] = m

    rth = df[(m >= 390) & (m < 780)]
    pre = df[(m >= 60) & (m < 390)]
    morn = df[(m >= 390) & (m < 480)]
    or5 = df[(m >= 390) & (m < 395)]

    g = rth.groupby("date")
    out = pd.DataFrame({"rth_open": g["o"].first(), "rth_close": g["c"].last(),
                        "rth_high": g["h"].max(), "rth_low": g["l"].min()})
    out["prev_close"] = out["rth_close"].shift(1)
    out["gap_signed_pct"] = (out["rth_open"] / out["prev_close"] - 1) * 100
    out["gap_pct"] = out["gap_signed_pct"].abs()
    out["day_range_pct"] = (out["rth_high"] - out["rth_low"]) / out["rth_open"] * 100
    out["prev_range_pct"] = out["day_range_pct"].shift(1)

    gm = morn.groupby("date")
    mh, ml, mc = gm["h"].max(), gm["l"].min(), gm["c"].last()
    out["morning_range_pct"] = (mh - ml) / out["rth_open"] * 100
    out["morning_net_pct"] = (mc - out["rth_open"]) / out["rth_open"] * 100
    out["efficiency"] = (mc - out["rth_open"]).abs() / (mh - ml)

    go = or5.groupby("date")
    out["or5_pct"] = (go["h"].max() - go["l"].min()) / out["rth_open"] * 100
    gp = pre.groupby("date")
    out["premkt_range_pct"] = (gp["h"].max() - gp["l"].min()) / out["rth_open"] * 100
    out.index = pd.to_datetime(out.index)
    return out


def get_vix(start):
    try:
        import yfinance as yf
        v = yf.download("^VIX", start=start, progress=False, auto_adjust=False)
        if isinstance(v.columns, pd.MultiIndex):
            v.columns = v.columns.get_level_values(0)
        s = v["Close"].copy()
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        return s
    except Exception as e:
        print("VIX download failed:", e)
        return None


def bucket_table(d, col, label, q=5):
    x = d[[col, "crosses"]].dropna()
    if len(x) < 50:
        return ""
    x["b"] = pd.qcut(x[col], q, duplicates="drop")
    rows = ["| " + label + " | days | avg crosses | days with 0-1 cross | days with 4+ |", "|---|---|---|---|---|"]
    for b, g in x.groupby("b", observed=True):
        rows.append(f"| {b.left:.2f} - {b.right:.2f} | {len(g)} | {g.crosses.mean():.2f} | "
                    f"{(g.crosses <= 1).mean() * 100:.0f}% | {(g.crosses >= 4).mean() * 100:.0f}% |")
    return "\n".join(rows)


def main(args):
    days = pd.read_csv(HERE / f"ema_cross_days_{args.years}y.csv", parse_dates=["date"])
    feat = day_features(args.years)
    d = days.merge(feat, left_on="date", right_index=True, how="left")
    vix = get_vix(str((d["date"].min() - pd.Timedelta(days=10)).date()))
    if vix is not None:
        d["vix"] = d["date"].map(vix)
        d["vix_prev"] = d["date"].map(vix.shift(1))
    d["year"] = d.date.dt.year
    d["month"] = d.date.dt.to_period("M")
    d["dow"] = d.date.dt.day_name()

    L = [f"# Why some mornings chop and others trend - SPY 9/21 cross count, 6:35-8:00 PT, last {args.years} years",
         "", f"{len(d)} trading days. Avg crosses per morning: **{d.crosses.mean():.2f}**.", ""]

    feats = [("vix_prev", "VIX (prior close)", True), ("gap_pct", "Overnight gap size %", True),
             ("prev_range_pct", "Prior day range %", True), ("premkt_range_pct", "Pre-market range %", True),
             ("or5_pct", "Opening 5-min range %", True),
             ("morning_range_pct", "6:30-8:00 range %", False), ("efficiency", "Morning trendiness (0-1)", False)]
    L += ["## What moves with the cross count (Spearman correlation)",
          "Negative = more of it means FEWER crosses (cleaner trend). 'Pre-open' = known before 6:35, usable as a filter.",
          "", "| factor | known pre-open? | correlation with crosses |", "|---|---|---|"]
    for col, lab, pre in feats:
        if col in d and d[col].notna().sum() > 50:
            r = d[[col, "crosses"]].corr(method="spearman").iloc[0, 1]
            L.append(f"| {lab} | {'yes' if pre else 'no'} | {r:+.2f} |")

    for col, lab, _ in feats:
        if col in d:
            t = bucket_table(d, col, lab)
            if t:
                L += ["", f"### {lab}", t]

    L += ["", "## By year", "| year | days | avg crosses | 0-1 cross days | 4+ days | avg VIX | avg morning range % | avg trendiness |",
          "|---|---|---|---|---|---|---|---|"]
    for y, g in d.groupby("year"):
        L.append(f"| {y} | {len(g)} | {g.crosses.mean():.2f} | {(g.crosses <= 1).mean() * 100:.0f}% | "
                 f"{(g.crosses >= 4).mean() * 100:.0f}% | {g.get('vix', pd.Series(dtype=float)).mean():.1f} | "
                 f"{g.morning_range_pct.mean():.2f} | {g.efficiency.mean():.2f} |")

    mo = d.groupby("month").agg(days=("crosses", "size"), avg=("crosses", "mean"),
                                vix=("vix", "mean") if "vix" in d else ("crosses", "size"),
                                rng=("morning_range_pct", "mean"), eff=("efficiency", "mean"),
                                gap=("gap_pct", "mean"))
    mo = mo[mo.days >= 10]
    hdr = ["| month | days | avg crosses | avg VIX | avg gap % | morning range % | trendiness |", "|---|---|---|---|---|---|---|"]

    def mrows(x):
        return [f"| {i} | {r.days} | {r.avg:.2f} | {r.vix:.1f} | {r.gap:.2f} | {r.rng:.2f} | {r.eff:.2f} |" for i, r in x.iterrows()]
    L += ["", "## 10 cleanest months (fewest crosses)"] + hdr + mrows(mo.nsmallest(10, "avg"))
    L += ["", "## 10 choppiest months (most crosses)"] + hdr + mrows(mo.nlargest(10, "avg"))

    L += ["", "## By weekday", "| day | days | avg crosses | 0-1 cross days |", "|---|---|---|---|"]
    for dname in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        g = d[d.dow == dname]
        if len(g):
            L.append(f"| {dname} | {len(g)} | {g.crosses.mean():.2f} | {(g.crosses <= 1).mean() * 100:.0f}% |")

    pre_cols = [c for c in ["vix_prev", "gap_pct", "premkt_range_pct", "or5_pct"] if c in d]
    z = d[pre_cols].rank(pct=True)
    d["preopen_score"] = z.mean(axis=1) * 100
    t = bucket_table(d, "preopen_score", "Pre-open volatility score (0-100)")
    L += ["", "## Combined pre-open score (avg percentile of VIX, gap, pre-market range, 5-min opening range)", t]

    report = "\n".join(L)
    print(report)
    (HERE / f"ema_regime_report_{args.years}y.md").write_text(report, encoding="utf-8")
    d.to_csv(HERE / f"ema_regime_days_{args.years}y.csv", index=False)
    print(f"\nSaved ema_regime_report_{args.years}y.md, ema_regime_days_{args.years}y.csv")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=int, default=7)
    main(p.parse_args())
