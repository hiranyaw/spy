import pandas as pd
a = pd.read_csv('ema_atr_trades_7y.csv')
b = a[(a.trigger == 'raw') & (a.cross_n <= 2) & a.qqq_aligned & a.vwap_aligned]
print('base cross1-2+QQQ+VWAP n', len(b), 'D', round(b.R_D.mean(), 3), 'B', round(b.R_B.mean(), 3))
for lo, hi in [(0, 0.25), (0.25, 0.5), (0.2, 0.5), (0.3, 0.45), (0.25, 0.6), (0.5, 9)]:
    r = b[(b.range_used >= lo) & (b.range_used < hi)]
    print(f'range {lo}-{hi}: n {len(r)} D {r.R_D.mean():+.3f} B {r.R_B.mean():+.3f} A {r.R_A.mean():+.3f} '
          f'winA {(r.res_A == "target").mean() * 100:.0f}% stopA {(r.res_A == "stop").mean() * 100:.0f}%')
r = b[(b.range_used >= 0.25) & (b.range_used < 0.5)]
print('signal days per year:', round(r.date.nunique() / 7), ' by dir:', r.dir.value_counts().to_dict())
print(r.groupby('dir').agg(D=('R_D', 'mean'), B=('R_B', 'mean')).round(3).to_string())
print(r.groupby(pd.cut(r.mins, [395, 410, 430, 450, 480], right=False), observed=True)
      .agg(n=('R_D', 'size'), D=('R_D', 'mean'), B=('R_B', 'mean')).round(3).to_string())
print(r.groupby('year').agg(n=('R_D', 'size'), D=('R_D', 'mean'), B=('R_B', 'mean')).round(3).to_string())
print('D outcomes:', r.res_D.value_counts(normalize=True).round(3).to_dict())
print('median 1m ATR $', r.atr1.median(), ' median stop $ (1.5x)', round(r.atr1.median() * 1.5, 2))
