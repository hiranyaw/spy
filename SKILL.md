---
name: hiranya-spy-edge-tracker
description: >
  Complete reference for Hiranya SPY Edge Tracker v1.0 — trendline break
  detection system for SPY 1M 0DTE scalping. Use this skill for anything
  related to: the Pine Script indicator, trendline break detection, ATR
  stop loss, TP1/TP2 targets, corner table, bar outcome labels, exit
  conditions ($ADD / 9 EMA / QQQ), webhook setup, Supabase edge_log table,
  Flask webhook routes, or the spy-dashboard integration. Triggers on:
  "trendline break", "edge tracker", "Pine Script", "SL/TP", "exit signal",
  "webhook", "edge_log", "corner table", "bar label", or any question about
  building or improving this indicator system.
---

# Hiranya SPY Edge Tracker v1.0

## Overview

Built by Hiranya on 2026-06-25 for SPY 1M 0DTE scalping during the
6:25–8:15 AM PT trading window. Detects trendline breaks with 5-indicator
confluence, plots SL/TP levels, shows a corner table, stamps bar outcome
labels, fires 3-signal exits, and logs everything to Supabase via webhook.

---

## System Architecture

```
Pine Script (TradingView)
    ├── Detects trendline break (5/5 confluence)
    ├── Plots ATR SL + TP1 + TP2 lines on chart
    ├── Corner table: count, time, direction, ATR, $ADD
    ├── Bar outcome labels: ✓ WIN / ✗ LOSS (N bars later)
    ├── Exit signals: $ADD + 9 EMA + QQQ (2-of-3 fires)
    └── Alert JSON → webhook on Render

Flask on Render (spy_trader_bot.py)
    ├── POST /webhook/edge  — receives entry signals
    ├── POST /webhook/exit  — receives exit signals
    └── GET  /api/edge/today, /api/edge/stats

Supabase
    └── edge_log table — permanent history

Flask Dashboard (spy-dashboard)
    ├── Daily signal count
    ├── Win % by time of day
    ├── SL hit % / TP1 vs TP2 rate
    └── Full history log table
```

---

## 5-Indicator Confluence

| # | Indicator | Bull condition | Bear condition |
|---|-----------|---------------|----------------|
| 1 | MACD 1M | macdLine > signalLine | macdLine < signalLine |
| 2 | QQQ 1M | QQQ close > QQQ 9 EMA | QQQ close < QQQ 9 EMA |
| 3 | $ADD 1M | ADD > 0 | ADD < 0 |
| 4 | SPY 5M | close > 21 EMA (proxy) | close < 21 EMA |
| 5 | SPY 1M | close > 9 EMA | close < 9 EMA |

Score ≥ 3/5 required to fire a trendline break signal.

---

## Trendline Break Detection

```pine
tl_high    = ta.highest(high, 20)   // 20-bar lookback (adjustable)
tl_low     = ta.lowest(low,  20)

break_long  = ta.crossover(close,  tl_high[1]) and score_long  >= 3
break_short = ta.crossunder(close, tl_low[1])  and score_short >= 3
```

---

## Risk Management

| Level | Formula | Default |
|-------|---------|---------|
| Stop loss | entry ± (ATR × 1.5) | ATR len=14, mult=1.5 |
| TP1 | risk × 1.5 R:R | 1:1.5 |
| TP2 | risk × 2.5 R:R | 1:2.5 |

Position management:
- At TP1 hit → exit 50%, move SL to breakeven
- Trail remaining 50% with 9 EMA
- At TP2 hit → exit remaining 50%
- Hard time stop: 8:10 AM PT regardless of P&L

---

## Exit Conditions (2-of-3 fires = exit)

| # | Signal | Long exit trigger | Short exit trigger |
|---|--------|------------------|--------------------|
| 1 | $ADD | Crosses below 0 OR drops 150+ pts | Crosses above 0 OR rises 150+ pts |
| 2 | 9 EMA 1M | Candle closes below 9 EMA | Candle closes above 9 EMA |
| 3 | QQQ 9 EMA | QQQ closes below its 9 EMA | QQQ closes above its 9 EMA |

No VWAP — removed by design. $ADD is the highest priority signal.

Exit reason logged: `ADD+EMA`, `ADD+QQQ`, or `EMA+QQQ`

---

## Webhook JSON Payloads

### Entry signal (POST /webhook/edge)
```json
{
  "indicator": "Hiranya SPY Edge Tracker v1.0",
  "symbol": "SPY",
  "direction": "LONG",
  "entry": 595.42,
  "sl": 594.87,
  "tp1": 596.24,
  "tp2": 596.79,
  "atr": 0.37,
  "confluence": 4,
  "add_value": 320,
  "time": "06:47 PT"
}
```

### Exit signal (POST /webhook/exit)
```json
{
  "indicator": "Hiranya SPY Edge Tracker v1.0",
  "symbol": "SPY",
  "event": "EXIT_LONG",
  "reason": "ADD+EMA",
  "price": 595.91,
  "time": "06:52 PT"
}
```

---

## Supabase — edge_log Schema

```sql
create table edge_log (
    id            bigserial primary key,
    created_at    timestamptz default now(),
    signal_time   text,
    direction     text,          -- 'LONG' or 'SHORT'
    entry_price   numeric,
    stop_loss     numeric,
    tp1           numeric,
    tp2           numeric,
    confluence    int,           -- 1 to 5
    atr_value     numeric,
    add_value     numeric,
    outcome       text default 'OPEN',  -- 'WIN_TP1','WIN_TP2','LOSS','OPEN'
    exit_reason   text,
    exit_price    numeric,
    symbol        text default 'SPY',
    indicator     text default 'Hiranya SPY Edge Tracker v1.0'
);
```

---

## Flask Routes (add to spy_trader_bot.py)

```python
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
TV_SECRET = os.environ['TV_WEBHOOK_SECRET']

@app.route('/webhook/edge', methods=['POST'])
def edge_webhook():
    if request.args.get('token') != TV_SECRET:
        return jsonify({'error': 'unauthorized'}), 401
    d = request.get_json(force=True)
    sb.table('edge_log').insert({
        'signal_time': d.get('time'),
        'direction':   d.get('direction'),
        'entry_price': d.get('entry'),
        'stop_loss':   d.get('sl'),
        'tp1':         d.get('tp1'),
        'tp2':         d.get('tp2'),
        'confluence':  d.get('confluence'),
        'atr_value':   d.get('atr'),
        'add_value':   d.get('add_value'),
    }).execute()
    return jsonify({'status': 'ok'}), 200

@app.route('/webhook/exit', methods=['POST'])
def exit_webhook():
    if request.args.get('token') != TV_SECRET:
        return jsonify({'error': 'unauthorized'}), 401
    d = request.get_json(force=True)
    direction = 'LONG' if d.get('event') == 'EXIT_LONG' else 'SHORT'
    open_rows = sb.table('edge_log').select('id').eq('outcome','OPEN').eq('direction',direction).order('created_at',desc=True).limit(1).execute()
    if open_rows.data:
        sb.table('edge_log').update({
            'exit_reason': d.get('reason'),
            'exit_price':  d.get('price'),
            'outcome':     'CLOSED',
        }).eq('id', open_rows.data[0]['id']).execute()
    return jsonify({'status': 'ok'}), 200
```

---

## Environment Variables

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your-anon-key
TV_WEBHOOK_SECRET=choose-a-random-string
```

## TradingView Alert URLs
```
Entry: https://your-app.onrender.com/webhook/edge?token=YOUR_SECRET
Exit:  https://your-app.onrender.com/webhook/exit?token=YOUR_SECRET
```

---

## Corner Table Contents

| Row | Value |
|-----|-------|
| Header | HIRANYA SPY EDGE TRACKER v1.0 |
| Signals today | running count |
| Last direction | LONG / SHORT (color coded) |
| Last signal time | HH:MM PT |
| Confluence | X/5 |
| Exits fired | running count |
| ATR | current ATR value |
| $ADD | current ADD value (green/red) |
| Exit signals | which of ADD/EMA/QQQ currently active |

---

## Files in This Project

| File | Purpose |
|------|---------|
| `hiranya_spy_edge_tracker_v1.0.pine` | Complete Pine Script — paste into TradingView |
| `edge_log_schema.sql` | Run in Supabase SQL Editor |
| `webhook_route.py` | Flask routes to add to spy_trader_bot.py |
| `TONIGHT_CHECKLIST.md` | Step-by-step build checklist |
| `SKILL.md` | This file — full project context |

---

## Tonight's Build Order

1. Run `edge_log_schema.sql` in Supabase
2. Add env vars to Render + local `.env`
3. Add Flask routes from `webhook_route.py` to `spy_trader_bot.py`
4. Push to GitLab → Render redeploys
5. Paste Pine Script into TradingView → save → add to chart
6. Create 2 TradingView alerts (entry + exit) pointing to Render URLs
7. Click "Test webhook" → verify row in Supabase
8. Add dashboard widgets (count, win %, SL %, history table)
9. Paper trade session tomorrow 6:25–8:15 AM PT

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-06-25 | Initial build — detection, SL/TP, corner table, bar labels, 3-signal exit, webhook |
