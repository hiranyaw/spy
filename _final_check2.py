import pandas as pd
t = pd.read_csv('final_921_trades.csv')
t['tr'] = pd.to_datetime(t.date) < '2024-01-01'
rsi = t.dir_rsi5 < 50
early = t.mins < 420
c = {
    'all crosses before 7:00': early,
    'cross1-2 before 7:00': (t.cross_n <= 2) & early,
    'cross1-2 + range>=0.25 before 7:00': (t.cross_n <= 2) & (t.range_used >= 0.25) & early,
    'cross1-2 + range>=0.40 before 7:00': (t.cross_n <= 2) & (t.range_used >= 0.40) & early,
    'cross1-2 + range>=0.40 + RSI pb before 7:00': (t.cross_n <= 2) & (t.range_used >= 0.40) & rsi & early,
    'cross1-2 + range>=0.40 + QQQ before 7:00': (t.cross_n <= 2) & (t.range_used >= 0.40) & t.qqq_aligned & early,
    'cross1-2 + range>=0.40 + VWAP before 7:00': (t.cross_n <= 2) & (t.range_used >= 0.40) & t.vwap_aligned & early,
    'cross1-2 + range>=0.40 7:00-8:00': (t.cross_n <= 2) & (t.range_used >= 0.40) & ~early,
    'any cross + range>=0.40 before 7:00': (t.range_used >= 0.40) & early,
}
print('| setup | trades | signals/yr | R_D train | R_D test | R_B train | R_B test | yrs R_D>0 (2020-26) |')
for k, m in c.items():
    g = t[m]
    yrs = g[g.year >= 2020].groupby('year').R_D.mean()
    print(f"| {k} | {len(g)} | {g.date.nunique() / 7:.0f} | {g[g.tr].R_D.mean():+.3f} | {g[~g.tr].R_D.mean():+.3f} | "
          f"{g[g.tr].R_B.mean():+.3f} | {g[~g.tr].R_B.mean():+.3f} | {(yrs > 0).sum()}/{len(yrs)} |")
for th in [0.30, 0.35, 0.40, 0.45, 0.50]:
    g = t[(t.cross_n <= 2) & (t.range_used >= th) & early]
    print(f' early cross1-2 range>={th}: train {g[g.tr].R_D.mean():+.3f} test {g[~g.tr].R_D.mean():+.3f} n {len(g)}')
g = t[(t.cross_n <= 2) & (t.range_used >= 0.40) & early]
print(g.groupby('year').agg(n=('R_D', 'size'), R_D=('R_D', 'mean'), R_B=('R_B', 'mean')).round(3).T.to_string())
print('dir:', g.groupby('dir').R_D.mean().round(3).to_dict(), 'cross_n:', g.groupby('cross_n').R_D.mean().round(3).to_dict())
print('outcomes:', g.res_D.value_counts(normalize=True).round(2).to_dict(), ' hit1.5R:', round((g.res_A == 'target').mean(), 2))
print('median minute of signal:', g.mins.median(), ' median range used:', g.range_used.median())
print('pullback-entry version R_D train/test:', round(g[g.tr].pb_R_D.mean(), 3), round(g[~g.tr].pb_R_D.mean(), 3))
# daily P&L sanity: one trade per day (first qualifying)
f = g.sort_values('time_pt').groupby('date').head(1)
print('first-signal-only: n', len(f), 'R_D', round(f.R_D.mean(), 3), 'train', round(f[f.tr].R_D.mean(), 3), 'test', round(f[~f.tr].R_D.mean(), 3))
cum = f.sort_values('time_pt').R_D.cumsum()
print('max drawdown (R):', round((cum.cummax() - cum).max(), 2), ' total R:', round(cum.iloc[-1], 1),
      ' worst losing streak:', int((f.sort_values('time_pt').R_D < 0).astype(int).groupby((f.sort_values('time_pt').R_D >= 0).cumsum()).sum().max()))
