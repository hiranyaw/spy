"""9/21 cross + Signal Monitor v1.9 readings at the cross bar. Joins final_921_trades.csv with sm19_bars.csv."""
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
t = pd.read_csv(HERE / "final_921_trades.csv").join(pd.read_csv(HERE / "sm19_bars.csv").set_index("time_pt"), on="time_pt")
t["train"] = pd.to_datetime(t.date) < "2024-01-01"
d = np.where(t.dir == "LONG", 1, -1)
t["dscore"] = np.where(d == 1, t.score, 100 - t.score)          # score in the trade's direction
t["agree"] = t.dscore > 50
t["strong"] = t.dscore >= 70
t["notrange"] = t.votes < 2
REC = {0: "WAIT", 1: "BUY", -1: "SELL", 2: "NO TRADE", 3: "ARMED", 4: "BRK UP", -4: "BRK DN"}
t["recname"] = t.rec.map(REC)
c12 = t.cross_n <= 2
r25, r40 = t.range_used >= 0.25, t.range_used >= 0.40
early = t.mins < 420
rsi = t.dir_rsi5 < 50
qv = t.qqq_aligned & t.vwap_aligned


def row(lab, m):
    g = t[m]
    if len(g) < 20:
        return f"| {lab} | {len(g)} | - | - | - | - | - |"
    yrs = g[g.year >= 2020].groupby("year").R_D.mean()
    return (f"| {lab} | {len(g)} | {g.date.nunique() / 7:.0f} | {g[g.train].R_D.mean():+.3f} | {g[~g.train].R_D.mean():+.3f} | "
            f"{g[~g.train].R_B.mean():+.3f} | {(yrs > 0).sum()}/{len(yrs)} |")


H = ["| setup | crosses | days/yr | R_D 2019-23 | R_D 2024-26 | R_B 2024-26 | yrs R_D>0 |", "|---|---|---|---|---|---|---|"]
allm = pd.Series(True, index=t.index)
L = ["# 9/21 cross + Signal Monitor v1.9 (7 years)", "", "## v1.9 reading at the cross"] + H + [
    row("all crosses", allm),
    row("v1.9 NOT range (votes 0-1)", t.notrange), row("v1.9 RANGE (votes 2+)", ~t.notrange),
    row("votes = 0", t.votes == 0), row("votes = 1", t.votes == 1), row("votes = 2", t.votes == 2), row("votes 3-4", t.votes >= 3),
    row("score agrees (>50 in trade dir)", t.agree), row("score strong (>=70 in trade dir)", t.strong),
    row("not range + score agrees", t.notrange & t.agree), row("not range + score strong", t.notrange & t.strong)]
L += ["", "### by v1.9 panel state at the cross"] + H + [row(f"panel = {k}", t.recname == k) for k in ["WAIT", "BUY", "SELL", "NO TRADE", "ARMED"]]
L += ["", "## Combined with the playbook"] + H + [
    row("A+ (cross1-2, before 7:00, range>=0.40, VWAP)", c12 & early & r40 & t.vwap_aligned),
    row("A+ + v1.9 not range", c12 & early & r40 & t.vwap_aligned & t.notrange),
    row("A+ + v1.9 score agrees", c12 & early & r40 & t.vwap_aligned & t.agree),
    row("Normal (cross1-2, range>=0.25, QQQ, VWAP, 5m RSI pb)", c12 & r25 & qv & rsi),
    row("Normal + v1.9 not range", c12 & r25 & qv & rsi & t.notrange),
    row("Normal + v1.9 RANGE", c12 & r25 & qv & rsi & ~t.notrange),
    row("Normal + score agrees", c12 & r25 & qv & rsi & t.agree),
    row("cross1-2 + range>=0.40", c12 & r40),
    row("cross1-2 + range>=0.40 + not range", c12 & r40 & t.notrange),
    row("cross1-2 + range>=0.40 + v1.9 RANGE", c12 & r40 & ~t.notrange),
    row("cross1-2 + range>=0.40 + score agrees", c12 & r40 & t.agree),
    row("cross1-2 + not range + score agrees", c12 & t.notrange & t.agree),
    row("1st cross + not range", (t.cross_n == 1) & t.notrange)]
rep = "\n".join(L)
print(rep)
(HERE / "sm19_cross_report.md").write_text(rep, encoding="utf-8")
