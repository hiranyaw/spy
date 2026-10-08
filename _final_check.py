import pandas as pd
t = pd.read_csv('final_921_trades.csv')
t['tr'] = pd.to_datetime(t.date) < '2024-01-01'
rsi = t.dir_rsi5 < 50
c = {
    'A: range>=0.40 alone': t.range_used >= 0.40,
    'B: 1st cross + range>=0.40': (t.cross_n == 1) & (t.range_used >= 0.40),
    'C: cross1-2 + range>=0.40': (t.cross_n <= 2) & (t.range_used >= 0.40),
    'D: cross1-2 + range>=0.40 + 5m RSI pullback': (t.cross_n <= 2) & (t.range_used >= 0.40) & rsi,
    'E: range>=0.40 + 1m ST agrees + before 7:30': (t.range_used >= 0.40) & t.st1_ok & (t.mins < 450),
    'F: earlier pick (cross1-2+QQQ+VWAP+range>=0.25+RSI pb)': (t.cross_n <= 2) & t.qqq_aligned & t.vwap_aligned & (t.range_used >= 0.25) & rsi,
    'G: cross1-2 + MACD dot + fast tape': (t.cross_n <= 2) & t.macd_ok & (t.atr_ratio >= 5),
}
print('| setup | trades | signals/yr | R_D train | R_D test | R_B train | R_B test | yrs R_D>0 | stopped |')
for k, m in c.items():
    g = t[m]
    yrs = g[g.year >= 2020].groupby('year').R_D.mean()
    print(f"| {k} | {len(g)} | {g.date.nunique() / 7:.0f} | {g[g.tr].R_D.mean():+.3f} | {g[~g.tr].R_D.mean():+.3f} | "
          f"{g[g.tr].R_B.mean():+.3f} | {g[~g.tr].R_B.mean():+.3f} | {(yrs > 0).sum()}/{len(yrs)} | {(g.res_D == 'stop').mean() * 100:.0f}% |")
print()
print('threshold sensitivity, cross1-2 + range>=X (R_D train / test / n)')
for x in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60]:
    g = t[(t.cross_n <= 2) & (t.range_used >= x)]
    print(f'  >= {x:.2f}: train {g[g.tr].R_D.mean():+.3f}  test {g[~g.tr].R_D.mean():+.3f}  n {len(g)}')
print()
for k in ['B: 1st cross + range>=0.40', 'C: cross1-2 + range>=0.40', 'D: cross1-2 + range>=0.40 + 5m RSI pullback']:
    g = t[c[k]]
    print(k)
    print(g.groupby('year').agg(n=('R_D', 'size'), R_D=('R_D', 'mean'), R_B=('R_B', 'mean')).round(3).T.to_string())
    print('  by dir:', g.groupby('dir').R_D.mean().round(3).to_dict(), ' by time:',
          g.groupby(pd.cut(g.mins, [395, 420, 450, 480], right=False), observed=True).R_D.mean().round(3).to_dict())
    print('  outcomes:', g.res_D.value_counts(normalize=True).round(2).to_dict())
    print('  median stop $:', round(1.5 * g.atr1.median(), 2), ' median daily ATR $:', round(g.datr.median(), 2),
          ' 2026 median daily ATR $:', round(g[g.year == 2026].datr.median(), 2))
