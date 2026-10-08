# SPY 9/21 EMA Cross Playbook (saved 2026-10-03)

Based on 7 years of SPY 1-min data (Sep 2019 - Oct 2026), crosses 6:35-8:00 AM PT.
Filters picked on 2019-23, checked on 2024-26. Not financial advice. PAPER TRADE FIRST.

## Key findings
- Plain 9/21 cross = coin flip (~-0.02R). 96% of days cross, avg 3.7 crosses/morning, 50% of days 4+.
- Chop can NOT be predicted pre-open (VIX, gap, prior day, premarket all ~0 correlation).
- What works: the day is ALREADY moving (range since 6:30 vs daily ATR), early cross, 1st/2nd cross only.
- More confirmation = worse (AK MACD 4/4, 5m Supertrend/RSI confirmed = late entry).
- Only ~half of best-looking filter combos held up out-of-sample -> real edge is small (+0.1 to +0.25R).

## Before the open (6:00-6:30 PT)
1. Check news / econ calendar. Big data (CPI, jobs, Fed) -> wait 5-10 min after release.
2. Daily ATR(14):  Line A = ATR x 0.25 (~$2 now)   Line B = ATR x 0.40 (~$3.20 now)
3. Mark yesterday H/L/C and premarket H/L. No trades 6:30-6:35.

## At every 9/21 cross (6:35-7:50)
| Step | Question | If NO |
|---|---|---|
| 1 | Range since 6:30 (high-low) > Line A? | skip |
| 2 | 1st or 2nd cross of the morning? | done for the day |
| 3a | A+: before 7:00, range > Line B, VWAP on trade side? | check 3b |
| 3b | Normal: QQQ 9/21 agrees + VWAP agrees + 5-min RSI NOT confirmed yet (<50 for call, >50 for put)? | skip |

Backtest: A+ ~13/yr, +0.36R (2019-23) / +0.22R (2024-26), 6/7 yrs positive.
          Normal ~51/yr, +0.11R / +0.24R (2.5R target +0.33R test), 6/7 yrs positive.

## Entry / exit
- Option: 0DTE, $1-3 ITM, delta 0.60-0.70, bid/ask $0.01-0.03, limit order.
  ($2 ITM moves ~$0.60-0.65 per $1 SPY in the morning; theta ~$10/contract per 30 min.)
- Enter at close of the cross candle.
- Stop: 1.5 x 1-min ATR on SPY (~$0.50 -> ~-$30/contract).
- TP1: +1.5R (~+$0.75 SPY) sell half, stop to breakeven.
- TP2: +2.5R (~+$1.25 SPY) or 1-min close back through 9 EMA.
- Time stop 60 min. Flat by 8:00.

## Risk rules
- 1 trade/day (2 max if first won). Daily loss limit 2R.
- ~50-55% of trades stop out - that is normal.
- Size by risk: e.g. $150 risk / $30 per contract = 5 contracts.

## Rollout
1. Weekend: chart (1m SPY: 9/21 EMA, VWAP, ATR14; 5m RSI14; QQQ 1m 9/21; daily ATR), journal in R.
2. Paper trade 4-6 weeks / 30+ signals. Go live only if avg > ~+0.1R after costs.
3. Live with 1-2 contracts for first 20 trades, then scale slowly.

## Second setup (tested): 5-min ORB
- OR = 6:30-6:35 high/low. Width 0.12-0.30% of price (~$0.90-2.30).
- First 1m close beyond OR, only if 9/21 + QQQ (also broke its OR) + gap direction agree.
- Stop = other side of OR, target 2x. Positive 7 of 8 years, ~1/week.

## Next steps / ideas (not done yet)
- Build live bot alerts: cross counter, range vs ATR, QQQ/VWAP, 5m RSI -> auto paper trades.
- Test $ADD (need 1-min $ADD export from TOS/TradingView).
- Paper-test debit spreads on A+ days (untested).
- Check big-data days (CPI/jobs/Fed) separately against the 7-year data.
- Build one-page printable checklist.

## Files (C:\Users\Hiranya\spy)
- data_cache\SPY_1m_7y.csv, QQQ_1m_7y.csv  (cached 7y 1-min data, Alpaca)
- ema_cross_backtest.py      basic cross test (--years, --pct)
- ema_regime_analysis.py     why chop vs trend
- orb_backtest.py            5-min ORB test
- ema_atr_backtest.py        ATR exits + filters
- ema_rsi_check.py, ema_akmacd_check.py   RSI / AK MACD tests
- final_921_study.py         train/test filter search -> final_921_report.md, final_921_trades.csv
