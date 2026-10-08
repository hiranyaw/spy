# 9/21 cross + AK MACD BB v1.19 components (no $ADD) - SPY 1-min, 6:35-8:00 PT, 7 years

D = your exits (1.5xATR stop, half at 1.5R, BE, 2.5R or 9 EMA trail). B = 1.5xATR stop, 2.5R target.

## Each component as a filter on ALL 9/21 crosses
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| ALL crosses | 6546 | 39% | -0.020 | -0.021 | 60% |
| MACD dot agrees (v1.19) | 5855 | 39% | -0.022 | -0.023 | 60% |
| MACD dot disagrees | 691 | 40% | -0.006 | -0.006 | 60% |
| MACD symmetric dot agrees | 5209 | 39% | -0.018 | -0.018 | 60% |
| MACD hist outside its BB | 1653 | 38% | -0.039 | -0.001 | 61% |
| 1m Supertrend agrees | 3522 | 39% | -0.026 | -0.016 | 61% |
| 1m Supertrend against | 3024 | 39% | -0.014 | -0.028 | 60% |
| 5m Supertrend agrees | 2639 | 38% | -0.040 | -0.036 | 61% |
| 5m Supertrend against | 3907 | 40% | -0.007 | -0.011 | 60% |
| QQQ 1m candle agrees | 5295 | 40% | -0.009 | -0.006 | 60% |
| AK 4/4 agree (all but ADD) | 926 | 39% | -0.048 | -0.071 | 61% |

### By AK score (0-4 components agreeing)
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| 0/4 | 60 | 33% | -0.225 | -0.386 | 67% |
| 1/4 | 478 | 40% | +0.005 | -0.066 | 59% |
| 2/4 | 2117 | 39% | -0.016 | -0.014 | 61% |
| 3/4 | 2965 | 39% | -0.015 | +0.003 | 60% |
| 4/4 | 926 | 39% | -0.048 | -0.071 | 61% |

## On top of the ATR 'day in play' filter (cross 1-2 + QQQ + VWAP + range >= 0.25x daily ATR)
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| ATR filter | 718 | 44% | +0.102 | +0.116 | 56% |
| + MACD dot agrees | 657 | 44% | +0.111 | +0.117 | 55% |
| + MACD dot disagrees | 61 | 41% | +0.002 | +0.099 | 59% |
| + MACD hist outside BB | 283 | 43% | +0.073 | +0.112 | 57% |
| + 1m Supertrend agrees | 485 | 45% | +0.116 | +0.127 | 55% |
| + 5m Supertrend agrees | 322 | 43% | +0.057 | +0.035 | 57% |
| + 5m Supertrend against | 396 | 45% | +0.139 | +0.182 | 55% |
| + AK 4/4 | 140 | 42% | +0.021 | -0.008 | 58% |

## ATR filter + 5m RSI < 50 (the pullback setup) + AK components
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| ATR + RSI pullback | 367 | 46% | +0.154 | +0.190 | 54% |
| + MACD dot agrees | 355 | 45% | +0.140 | +0.171 | 55% |
| + 1m Supertrend agrees | 281 | 45% | +0.138 | +0.164 | 55% |
| + 5m Supertrend agrees | 42 | 40% | +0.019 | +0.083 | 60% |
| + 5m Supertrend against | 325 | 46% | +0.172 | +0.204 | 54% |
