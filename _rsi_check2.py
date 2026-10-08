import pandas as pd
t = pd.read_csv('ema_rsi_trades_7y.csv')
best = (t.cross_n <= 2) & t.qqq_aligned & t.vwap_aligned & (t.range_used >= 0.25)
for lab, f in [('filter + 5m RSI<50', t[best & (t.dir_rsi5 < 50)]), ('filter + 5m RSI>=50', t[best & (t.dir_rsi5 >= 50)])]:
    print('==', lab, 'n', len(f), 'D', round(f.R_D.mean(), 3), 'B', round(f.R_B.mean(), 3))
    print(f.groupby('year').agg(n=('R_D', 'size'), D=('R_D', 'mean'), B=('R_B', 'mean')).round(3).to_string())
f = t[best & (t.dir_rsi5 < 50)]
print('5m RSI<50 bands:')
print(f.groupby(pd.cut(f.dir_rsi5, [0, 30, 40, 45, 50]), observed=True).agg(n=('R_D', 'size'), D=('R_D', 'mean'), B=('R_B', 'mean')).round(3).to_string())
print('signal days/yr', round(f.date.nunique() / 7), 'dir', f.dir.value_counts().to_dict())
print(f.groupby('dir').agg(D=('R_D', 'mean'), B=('R_B', 'mean')).round(3).to_string())
