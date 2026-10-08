# Build guide: Hiranya Signal Monitor v1.9 -> v2.0  (saved 2026-10-03)

Script: C:\Users\Hiranya\spy\Hiranya_Signal_Monitor_v2.0.pine  (298 lines, Pine v5)
Status: compiled with TradingView's Pine compiler - 0 errors, 0 warnings. Not yet run on a live chart.
Plan doc: "Hiranya Signal Monitor v2.0 - Improvement Plan" (Claude artifact)
Not financial advice. Paper trade first.

## What changes from v1.9
| v1.9 | v2.0 |
|---|---|
| 70/30 score fires BUY/SELL (~5 per morning) | 4 checks at each 9/21 cross -> A+ / NORMAL / SKIP + reason / DONE |
| ER / ADX / Chop / cross-count RANGE block | Range used vs daily ATR (Line A 0.25x, Line B 0.40x) + 1st/2nd cross only |
| BRK range-break arming | Removed |
| 5m direction weighted in score | Removed from signal (5m RSI used only as "pullback not yet confirmed") |
| 18-row panel | 10-row panel: SIGNAL, WHY, CROSS #, RANGE gauge, QQQ, VWAP, 5m RSI, TIME, PLAN, DAILY ATR |
| No trade plan | Entry / stop / TP1 / TP2 lines + 60-min time-stop marker drawn at the signal |
| Static alerts | alertcondition per setup + JSON alert() for the bot |

v1.9 is NOT edited - v2.0 is a new script, so v1.9 stays as a backup.

## Step 1 - Create the script in TradingView
1. Open TradingView -> any chart -> Pine Editor (bottom panel).
2. Click the script name dropdown -> "Create new" -> "Indicator".
3. Select all (Ctrl+A) and delete the template.
4. Open C:\Users\Hiranya\spy\Hiranya_Signal_Monitor_v2.0.pine in Notepad, Ctrl+A, Ctrl+C, paste into the editor.
5. Click Save -> name it "Hiranya Signal Monitor v2.0".
6. Click "Add to chart". There should be no red errors at the bottom.

## Step 2 - Set up the chart
1. Symbol AMEX:SPY, 1-minute timeframe.
2. Extended hours can be on or off (v2.0 anchors its own VWAP and range at 6:30 PT).
3. Hide v1.9 (eye icon) so the two panels don't overlap. Keep it on the chart if you still want the belts.
4. v2.0 plots its own 9 EMA, 21 EMA and RTH VWAP - hide duplicate EMA/VWAP indicators, or turn these
   off in v2.0 Settings -> Style.
5. Optional: Settings -> Inputs -> "Panel position" / "Panel text size".

## Step 3 - Check the settings (defaults = the backtest)
| Input | Default | Why |
|---|---|---|
| Max crosses per day | 2 | 3rd+ cross days lost ~0.11R per trade |
| Line A / Line B | 0.25 / 0.40 x daily ATR | Below 0.25x the cross lost money; 0.40x+ was the A+ band |
| A+ window ends | 700 | Best results before 7:00 PT |
| Normal window ends | 750 | Late crosses had weakest follow-through |
| Time zone | America/Los_Angeles | All times are PT |
| Stop / TP1 / TP2 | 1.5x 1-min ATR / 1.5R / 2.5R | Your existing exit system |
| One signal per day | on | Discipline rule from the playbook |
| ORB setup | off | Turn on later as an optional second setup |

## Step 4 - Verify against the backtest (do this before paper trading)
Use Bar Replay or scroll back to these dates on the SPY 1-minute chart. v2.0 should show the same label
at (or within 1-2 bars of) the listed time. Times are PT, entry is the cross candle close.

| Date / time PT | Setup | Dir | Entry | Range used | Backtest result (your exits) |
|---|---|---|---|---|---|
| 2026-09-17 07:47 | NORMAL | SHORT | 759.32 | 0.53x | +1.15R |
| 2026-09-16 07:06 | NORMAL | SHORT | 757.56 | 0.28x | -1R |
| 2026-08-27 06:58 | A+ | SHORT | 766.24 | 0.40x | -1R |
| 2026-08-20 06:53 | NORMAL | SHORT | 764.60 | 0.27x | -1R |
| 2026-08-19 07:05 | NORMAL | SHORT | 767.82 | 0.35x | -1R |
| 2026-08-12 07:18 | NORMAL | LONG | 771.04 | 0.37x | -1R |
| 2026-07-23 06:51 | A+ | SHORT | 738.06 | 0.51x | -1R |
| 2026-07-14 07:02 | NORMAL | SHORT | 748.66 | 0.26x | +2R |
| 2026-07-01 06:51 | NORMAL | LONG | 742.55 | 0.27x | +2R |
| 2026-06-29 06:57 | A+ | SHORT | 735.05 | 0.44x | +2R |

Note: 2026 has been a weak year for this setup (several stops in a row above) - the 7-year average is
positive but streaks of 5+ losers happen.

If most dates match -> go to Step 5. If many don't, check in this order:
1. Time zone input = America/Los_Angeles.
2. Small differences are expected because:
   - 5m RSI in v2.0 uses the previous COMPLETED 5-min bar (no repaint); the backtest used the bar
     closing at the cross minute, so RSI can differ on crosses at :X4 / :X9 minutes.
   - EMA warm-up and data vendor differences (TradingView vs Alpaca) can shift a cross by one bar.
   - Daily ATR comes from TradingView daily bars.
3. Send me the dates that don't match and a screenshot of the panel - I'll fix the logic.

## Step 5 - Alerts
1. Chart -> Alert (clock icon) -> Condition: "Hiranya Signal Monitor v2.0".
2. For the bot: choose "Any alert() function call". Message is JSON:
   {"src":"HSM2","setup":"A+","dir":"LONG","entry":...,"stop":...,"tp1":...,"tp2":...}
   Enable Webhook URL -> point to your Flask webhook route (same as the Edge Tracker / Supabase flow).
3. For phone/sound only: create separate alerts on "A+ LONG", "A+ SHORT", "NORMAL LONG", "NORMAL SHORT".
4. Options: "Once per bar close". Expiration: open-ended.

## Step 6 - Paper trade
1. Let the bot paper-trade every JSON alert (Alpaca paper), or log by hand.
2. Journal in R: setup, time, entry, stop, exit, R, panel WHY text on skipped crosses.
3. Minimum 30 signals (~6-8 weeks). Go live only if avg >= +0.10R after option costs,
   stop-out rate 50-56%, and signals ~1 per week.
4. Live: 1-2 contracts for the first 20 trades; $1-3 ITM 0DTE, delta 0.60-0.70.

## Reading the panel
| Row | Meaning |
|---|---|
| SIGNAL | WAITING -> A+ LONG/SHORT, NORMAL LONG/SHORT, ORB..., SKIP, DONE FOR TODAY, CLOSED |
| WHY | Why the last cross was skipped (first failed check) |
| CROSS # | 0/1/2 of 2, then DONE |
| RANGE | Gauge (marks at A and B), range used x daily ATR, $ range since 6:30. Grey < A, orange A-B, lime > B |
| QQQ 9/21 | UP / DOWN |
| VWAP | Above/below the 6:30-anchored VWAP, $ distance |
| 5m RSI | Value + "pullback ok" (not yet confirmed in the 9/21 direction) or "confirmed" |
| TIME | pre / A+ window / Normal window / closed |
| PLAN | Setup, Entry, Stop, T1, T2 of today's signal |
| DAILY ATR | Yesterday's 14-day ATR, Line A $ and Line B $ |

## Troubleshooting
| Symptom | Fix |
|---|---|
| Panel shows NaN for range / ATR | Chart needs daily data - make sure it is SPY (not a custom spread); reload |
| No signals ever | Check time zone input; check you are on 1-minute |
| Signals on every cross | "Max crosses per day" or "One signal per day" changed - reset defaults |
| Too many lines on chart | Lines stay 60 bars; TradingView keeps the last 200 drawings |
| Alerts don't fire | Alert must be created AFTER adding v2.0; use "Once per bar close" |

## Next (after paper trading starts)
- Add $ADD as a test filter once 1-min $ADD history is exported (TOS / TradingView).
- Turn on the ORB setup (input) and paper-trade it separately.
- Re-run the Python backtest quarterly: python final_921_study.py
