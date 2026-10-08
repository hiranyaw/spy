"""
SPY 9/21 EMA cross backtest — 1-minute bars, 6:35–8:00 AM PT, last 3 years.

What it answers:
  * How many trading days had a 9/21 cross in the 6:35–8:00 PT window
  * How many crosses per day (chop vs clean days)
  * Did the cross follow through? (target vs stop, MFE/MAE, 15/30-min move, whipsaw)
  * Does it work better as the FIRST cross of the day, with VWAP aligned, with QQQ aligned?

Data: Alpaca market-data API (free with your Alpaca account; SIP history, 1-min).
Keys are read from env vars or a .env file next to this script:
    APCA_API_KEY_ID / APCA_API_SECRET_KEY   (or ALPACA_API_KEY / ALPACA_SECRET_KEY)

Run (from C:\\Users\\Hiranya\\spy):
    python ema_cross_backtest.py
Options:
    --years 3 --target 1.00 --stop 0.50 --hold 30 --whipsaw 5 --session ext
Outputs:
    ema_cross_trades.csv   one row per cross with all metrics
    ema_cross_days.csv     one row per trading day
    ema_cross_report.md    the summary (also printed)
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "data_cache"
PT = "America/Los_Angeles"


# ---------------------------------------------------------------- keys / data
def load_keys():
    env_file = HERE / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    key = os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_API_KEY") or os.getenv("ALPACA_KEY")
    sec = os.getenv("APCA_API_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_SECRET")
    if not key or not sec:
        sys.exit("Alpaca keys not found. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY "
                 "(env vars or a .env file next to this script).")
    return key, sec


def fetch_bars(symbol, start, end, key, sec, feed="sip"):
    import requests
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}
    params = {"timeframe": "1Min", "start": start, "end": end, "limit": 10000,
              "adjustment": "all", "feed": feed, "sort": "asc"}
    rows, page = [], 0
    while True:
        r = requests.get(url, headers=headers, params=params, timeout=60)
        if r.status_code == 403 and feed == "sip":
            print("  SIP feed not allowed on this account, falling back to IEX feed")
            return fetch_bars(symbol, start, end, key, sec, feed="iex")
        if r.status_code == 429:
            time.sleep(3)
            continue
        r.raise_for_status()
        js = r.json()
        rows.extend(js.get("bars") or [])
        page += 1
        if page % 10 == 0:
            print(f"  {symbol}: {len(rows):,} bars so far", flush=True)
        tok = js.get("next_page_token")
        if not tok:
            break
        params["page_token"] = tok
    df = pd.DataFrame(rows).rename(columns={"t": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df[["ts", "o", "h", "l", "c", "v"]].set_index("ts").sort_index()


def get_data(symbol, years, key=None, sec=None):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{symbol}_1m_{years}y.csv"
    if f.exists() and (time.time() - f.stat().st_mtime) < 86400 * 3:
        print(f"Using cached {f.name}")
        df = pd.read_csv(f, parse_dates=["ts"]).set_index("ts")
        df.index = pd.to_datetime(df.index, utc=True)
        return df
    if key is None:
        key, sec = load_keys()
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    start = end - timedelta(days=365 * years + 10)  # +10 days warm-up for EMAs
    print(f"Downloading {symbol} 1-min bars {start.date()} -> {end.date()} ...", flush=True)
    df = fetch_bars(symbol, start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ"), key, sec)
    df.to_csv(f)
    print(f"  saved {len(df):,} bars -> {f.name}", flush=True)
    return df


# ---------------------------------------------------------------- indicators
def prepare(df, session):
    df = df.copy()
    df.index = df.index.tz_convert(PT)
    mins = df.index.hour * 60 + df.index.minute
    if session == "rth":
        df = df[(mins >= 390) & (mins < 780)]          # 6:30–13:00 PT
    else:
        df = df[(mins >= 60) & (mins < 1020)]          # 1:00–17:00 PT (4am–8pm ET)
    df["ema9"] = df["c"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["c"].ewm(span=21, adjust=False).mean()
    df["spread"] = df["ema9"] - df["ema21"]
    df["date"] = df.index.date
    m = df.index.hour * 60 + df.index.minute
    df["mins"] = m
    # RTH-anchored VWAP (resets each day at 6:30 PT)
    rth = m >= 390
    tp = (df["h"] + df["l"] + df["c"]) / 3
    pv = (tp * df["v"]).where(rth, 0.0)
    vv = df["v"].where(rth, 0.0)
    df["vwap"] = pv.groupby(df["date"]).cumsum() / vv.groupby(df["date"]).cumsum().replace(0, np.nan)
    return df


def find_crosses(df):
    s = np.sign(df["spread"])
    prev = s.shift(1)
    return (s != prev) & (s != 0) & (prev != 0) & prev.notna()


# ---------------------------------------------------------------- backtest
def run(args):
    key = sec = None
    if not (CACHE / f"SPY_1m_{args.years}y.csv").exists() or not (CACHE / f"QQQ_1m_{args.years}y.csv").exists():
        key, sec = load_keys()
    spy = prepare(get_data("SPY", args.years, key, sec), args.session)
    qqq = prepare(get_data("QQQ", args.years, key, sec), args.session)
    spy["qqq_sign"] = np.sign(qqq["spread"]).reindex(spy.index).ffill()

    spy["cross"] = find_crosses(spy)
    w_lo, w_hi = 6 * 60 + 35, 8 * 60          # 6:35 <= bar start < 8:00 PT
    cutoff = pd.Timestamp.now(tz=PT).normalize() - pd.DateOffset(years=args.years)
    spy = spy[spy.index >= cutoff]

    idx = spy.index
    c = spy["c"].to_numpy(); h = spy["h"].to_numpy(); l = spy["l"].to_numpy()
    sp = spy["spread"].to_numpy(); dates = spy["date"].to_numpy(); mins = spy["mins"].to_numpy()
    cross_pos = np.flatnonzero(spy["cross"].to_numpy())
    trades = []
    for k, i in enumerate(cross_pos):
        if not (w_lo <= mins[i] < w_hi):
            continue
        d = 1 if sp[i] > 0 else -1
        entry = c[i]
        tgt = entry * args.target / 100 if args.pct else args.target
        stp = entry * args.stop / 100 if args.pct else args.stop
        j_end = i + 1
        while j_end < len(c) and j_end <= i + args.hold and dates[j_end] == dates[i]:
            j_end += 1
        fh, fl, fc = h[i + 1:j_end], l[i + 1:j_end], c[i + 1:j_end]
        if len(fc) == 0:
            continue
        fav = (fh - entry) if d == 1 else (entry - fl)
        adv = (entry - fl) if d == 1 else (fh - entry)
        result, bars_to = "timeout", len(fc)
        for n in range(len(fc)):
            if adv[n] >= stp:                    # stop checked first = conservative
                result, bars_to = "stop", n + 1
                break
            if fav[n] >= tgt:
                result, bars_to = "target", n + 1
                break
        exit_px = (entry + d * tgt if result == "target"
                   else entry - d * stp if result == "stop" else fc[bars_to - 1])

        def move_at(n):
            return d * (fc[min(n, len(fc)) - 1] - entry)
        nxt = cross_pos[k + 1] if k + 1 < len(cross_pos) else None
        bars_to_next = (nxt - i) if (nxt is not None and dates[nxt] == dates[i]) else np.nan
        vwap = spy["vwap"].iat[i]
        trades.append({
            "time_pt": idx[i].strftime("%Y-%m-%d %H:%M"),
            "date": dates[i], "year": idx[i].year, "dir": "LONG" if d == 1 else "SHORT",
            "entry": round(entry, 2),
            "vwap_aligned": bool(np.isfinite(vwap) and d * (entry - vwap) > 0),
            "qqq_aligned": bool(spy["qqq_sign"].iat[i] == d),
            "result": result, "bars_to_result": bars_to,
            "pnl_pts": round(d * (exit_px - entry), 2),
            "pnl_R": round(d * (exit_px - entry) / stp, 2),
            "mfe": round(fav.max(), 2), "mae": round(adv.max(), 2),
            "move_15m": round(move_at(15), 2), "move_30m": round(move_at(30), 2),
            "bars_to_next_cross": bars_to_next,
            "whipsaw": bool(np.isfinite(bars_to_next) and bars_to_next <= args.whipsaw),
            "time_bucket": ("6:35-7:00" if mins[i] < 420 else "7:00-7:30" if mins[i] < 450 else "7:30-8:00"),
        })
    t = pd.DataFrame(trades)
    if t.empty:
        sys.exit("No crosses found - check data.")
    t["nth_cross_today"] = t.groupby("date").cumcount() + 1
    t["crosses_that_day"] = t.groupby("date")["date"].transform("size")
    t["first_cross"] = t["nth_cross_today"] == 1

    rth_days = sorted(set(spy.loc[(spy["mins"] >= w_lo) & (spy["mins"] < w_hi), "date"]))
    days = pd.DataFrame({"date": rth_days})
    cnt = t.groupby("date").size()
    days["crosses"] = days["date"].map(cnt).fillna(0).astype(int)
    first = t[t["first_cross"]].set_index("date")
    days["first_dir"] = days["date"].map(first["dir"])
    days["first_result"] = days["date"].map(first["result"])
    days["first_move_30m"] = days["date"].map(first["move_30m"])

    report = build_report(t, days, args)
    print(report)
    sfx = f"_{args.years}y" + ("_pct" if args.pct else "")
    t.to_csv(HERE / f"ema_cross_trades{sfx}.csv", index=False)
    days.to_csv(HERE / f"ema_cross_days{sfx}.csv", index=False)
    (HERE / f"ema_cross_report{sfx}.md").write_text(report, encoding="utf-8")
    print(f"\nSaved: ema_cross_trades{sfx}.csv, ema_cross_days{sfx}.csv, ema_cross_report{sfx}.md")


def stats(g, args):
    n = len(g)
    if n == 0:
        return None
    win = (g["result"] == "target").mean() * 100
    loss = (g["result"] == "stop").mean() * 100
    return {"crosses": n, "target_hit%": round(win, 1), "stopped%": round(loss, 1),
            "avg_pnl_pts": round(g["pnl_pts"].mean(), 3), "avg_R": round(g["pnl_R"].mean(), 3), "avg_MFE": round(g["mfe"].mean(), 2),
            "avg_MAE": round(g["mae"].mean(), 2), "avg_move_15m": round(g["move_15m"].mean(), 2),
            "avg_move_30m": round(g["move_30m"].mean(), 2), "whipsaw%": round(g["whipsaw"].mean() * 100, 1)}


def table(rows):
    rows = [(k, v) for k, v in rows if v]
    if not rows:
        return ""
    cols = list(rows[0][1].keys())
    out = ["| group | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for k, v in rows:
        out.append(f"| {k} | " + " | ".join(str(v[c]) for c in cols) + " |")
    return "\n".join(out)


def build_report(t, days, args):
    nd = len(days)
    dist = days["crosses"].clip(upper=4).value_counts().sort_index()
    lab = {0: "0 crosses", 1: "1 cross", 2: "2 crosses", 3: "3 crosses", 4: "4+ crosses"}
    be = args.stop / (args.stop + args.target) * 100
    L = [f"# SPY 1-min 9/21 EMA cross - 6:35-8:00 AM PT, last {args.years} years", "",
         (f"Rules: entry at close of cross bar; target +{args.target:.3f}%, stop -{args.stop:.3f}% of price "
          if args.pct else
          f"Rules: entry at close of cross bar; target +${args.target:.2f}, stop -${args.stop:.2f} ") +
         f"(stop checked first if both hit in one bar), max hold {args.hold} min. "
         f"Whipsaw = opposite cross within {args.whipsaw} bars. EMAs on {args.session.upper()} session bars. "
         f"Break-even target-hit rate ~{be:.0f}% (before option costs).", "",
         "## Days", f"Trading days: **{nd}**  |  days with >=1 cross: **{(days['crosses'] > 0).sum()}** "
         f"({(days['crosses'] > 0).mean() * 100:.0f}%)  |  total crosses: **{len(t)}**  |  "
         f"avg crosses/day: {days['crosses'].mean():.2f}", "",
         "| crosses in window | days | % |", "|---|---|---|"]
    for k, v in dist.items():
        L.append(f"| {lab[k]} | {v} | {v / nd * 100:.0f}% |")
    L += ["", "## Follow-through"]
    rows = [("ALL crosses", stats(t, args)),
            ("LONG", stats(t[t.dir == "LONG"], args)), ("SHORT", stats(t[t.dir == "SHORT"], args)),
            ("First cross of day", stats(t[t.first_cross], args)),
            ("2nd+ cross of day", stats(t[~t.first_cross], args)),
            ("Day had only 1 cross", stats(t[t.crosses_that_day == 1], args)),
            ("Day had 3+ crosses", stats(t[t.crosses_that_day >= 3], args)),
            ("VWAP aligned", stats(t[t.vwap_aligned], args)),
            ("VWAP against", stats(t[~t.vwap_aligned], args)),
            ("QQQ aligned", stats(t[t.qqq_aligned], args)),
            ("VWAP + QQQ aligned", stats(t[t.vwap_aligned & t.qqq_aligned], args)),
            ("First + VWAP + QQQ", stats(t[t.first_cross & t.vwap_aligned & t.qqq_aligned], args))]
    L.append(table(rows))
    L += ["", "## By time of cross", table([(b, stats(g, args)) for b, g in t.groupby("time_bucket")])]
    L += ["", "## By year", table([(str(y), stats(g, args)) for y, g in t.groupby("year")])]
    return "\n".join(L)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=int, default=3)
    p.add_argument("--target", type=float, default=1.00, help="$ move in SPY for follow-through")
    p.add_argument("--stop", type=float, default=0.50, help="$ adverse move = failed")
    p.add_argument("--hold", type=int, default=30, help="max minutes to wait")
    p.add_argument("--whipsaw", type=int, default=5, help="opposite cross within N bars")
    p.add_argument("--pct", action="store_true",
                   help="treat --target/--stop as %% of entry price (e.g. --pct --target 0.13 --stop 0.065)")
    p.add_argument("--session", choices=["ext", "rth"], default="ext",
                   help="ext = EMAs include pre-market (like your chart), rth = regular hours only")
    run(p.parse_args())
