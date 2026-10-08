# 9/21 cross + RSI(14) - SPY 1-min, 6:35-8:00 PT, 7 years

RSI is shown in the trade's direction: long = RSI, short = 100 - RSI. So 60 means 'RSI 60 on a long / RSI 40 on a short'. Break-even: D ~0R, B needs avg R > 0.

## All crosses - 1-min RSI at the cross
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| 50-60 | 5179 | 39% | -0.021 | -0.029 | 60% |
| 60-70 | 1317 | 39% | -0.017 | +0.006 | 60% |
| 70-101 | 29 | 38% | +0.019 | +0.207 | 62% |

## All crosses - 5-min RSI at the cross
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| 0-40 | 1262 | 41% | +0.020 | +0.026 | 59% |
| 40-50 | 2606 | 39% | -0.012 | -0.023 | 60% |
| 50-60 | 2089 | 38% | -0.055 | -0.037 | 62% |
| 60-70 | 537 | 38% | -0.055 | -0.093 | 61% |
| 70-101 | 52 | 52% | +0.314 | +0.293 | 48% |

## With the ATR filter (cross 1-2 + QQQ + VWAP + range used >= 0.25x daily ATR)
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| filter only | 718 | 44% | +0.102 | +0.116 | 56% |

### ...by 1-min RSI
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| 50-60 | 439 | 44% | +0.114 | +0.122 | 56% |
| 60-70 | 269 | 43% | +0.049 | +0.057 | 57% |

### ...by 5-min RSI
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| 0-40 | 148 | 45% | +0.105 | +0.221 | 55% |
| 40-50 | 219 | 46% | +0.187 | +0.169 | 54% |
| 50-60 | 243 | 42% | +0.006 | +0.014 | 58% |
| 60-70 | 95 | 42% | +0.064 | +0.000 | 58% |

## Simple RSI rules on all crosses
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| 1m RSI agrees (>50) | 6525 | 39% | -0.020 | -0.021 | 60% |
| 5m RSI agrees (>50) | 2678 | 38% | -0.048 | -0.042 | 61% |
| both agree | 2678 | 38% | -0.048 | -0.042 | 61% |
| 5m RSI 50-70 (agrees, not stretched) | 2626 | 38% | -0.055 | -0.049 | 62% |
| 5m RSI against (<50) | 3868 | 40% | -0.001 | -0.007 | 60% |

## RSI rules on top of the ATR filter
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| filter + 5m RSI > 50 | 351 | 43% | +0.047 | +0.038 | 57% |
| filter + 5m RSI 50-70 | 338 | 42% | +0.022 | +0.010 | 58% |
| filter + 5m RSI < 50 | 367 | 46% | +0.154 | +0.190 | 54% |
| filter + 1m RSI 50-70 | 708 | 44% | +0.090 | +0.097 | 56% |

### filter + 5m RSI 50-70 by year
| group | trades | hit 1.5R | your system (D) avg R | 2.5R (B) avg R | stopped |
|---|---|---|---|---|---|
| 2020 | 34 | 44% | +0.163 | +0.074 | 53% |
| 2021 | 53 | 45% | +0.099 | +0.067 | 55% |
| 2022 | 62 | 47% | +0.157 | +0.096 | 53% |
| 2023 | 54 | 39% | -0.090 | -0.093 | 61% |
| 2024 | 47 | 38% | -0.071 | -0.145 | 62% |
| 2025 | 45 | 42% | +0.028 | +0.151 | 58% |
| 2026 | 32 | 38% | -0.100 | -0.099 | 62% |